"""Ingest: one dlt pipeline per resource, landing Parquet in the lake (AC21, AC22, EC10).

The seam these tests call: ``ingest.run(resources) -> int``, where ``resources`` maps a resource
name to the first page URL of its OData feed. It lands each resource under ``$LAKE_ROOT`` in the
layout ``harness.write_load`` writes, carries on past a failed resource, names each failure on
stdout, stderr or the log, and returns the process exit status. ``uv run ingest`` is ``run`` over
the declared resources.
"""

from __future__ import annotations

import json
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import duckdb
import pytest

from harness import product

LAYOUT = re.compile(r"^(?P<resource>[^/]+)/date=\d{4}-\d{2}-\d{2}/hour=\d{2}/[^/]+\.parquet$")


class Feed:
    """A stub OData feed: path (with query) -> (status, JSON body[, extra headers])."""

    def __init__(self, port: int = 0):
        self.pages: dict[str, tuple] = {}
        self.requested: list[str] = []
        feed = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                feed.requested.append(self.path)
                status, body, *extra = feed.pages.get(self.path, (404, {"error": "no such page"}))
                payload = json.dumps(body).encode()
                self.send_response(status)
                for name, value in (extra[0] if extra else {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def feed():
    f = Feed()
    yield f
    f.server.shutdown()


@pytest.fixture
def lake(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "lake"
    root.mkdir()
    monkeypatch.setenv("LAKE_ROOT", str(root))
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "dlt"))
    monkeypatch.setenv("RUNTIME__REQUEST_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("RUNTIME__REQUEST_BACKOFF_FACTOR", "0")
    for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    return root


def landed(lake: Path) -> dict[str, list[Path]]:
    """resource -> the Parquet files landed for it; fails on any data file outside the layout.

    dlt's own bookkeeping tables (``_dlt_*``), if it keeps them in the lake, are not data.
    """
    out: dict[str, list[Path]] = {}
    for path in sorted(lake.rglob("*.parquet")):
        rel = path.relative_to(lake).as_posix()
        if any(part.startswith("_dlt") for part in rel.split("/")):
            continue
        match = LAYOUT.match(rel)
        assert match, f"{rel} is not <resource>/date=YYYY-MM-DD/hour=HH/<file>.parquet"
        out.setdefault(match["resource"], []).append(path)
    return out


def rows(files: list[Path]) -> list[tuple[str, str, dict]]:
    """(_dlt_load_id, _dlt_id, the source row) of every landed row."""
    con = duckdb.connect()
    try:
        names = [p.as_posix() for p in files]
        got = con.execute(
            "select _dlt_load_id, _dlt_id, cast(data as varchar) from read_parquet(?)", [names]
        ).fetchall()
    finally:
        con.close()
    return [(load, ident, json.loads(data)) for load, ident, data in got]


def run(resources: dict[str, str]) -> int:
    import ingest

    return ingest.run(resources)


def said(capsys, caplog) -> str:
    out = capsys.readouterr()
    return out.out + out.err + caplog.text


def test_next_link_pages_land_in_one_load(feed, lake):
    """AC22: a two-page feed via @odata.nextLink lands every row of both pages in one load."""
    first = [product(1, "PG-0001", "One"), product(2, "PG-0002", "Two")]
    second = [product(3, "PG-0003", "Three")]
    feed.pages["/Products"] = (200, {"value": first, "@odata.nextLink": f"{feed.base}/Products?$skiptoken=2"})
    feed.pages["/Products?$skiptoken=2"] = (200, {"value": second})

    assert run({"adventure_works__products": f"{feed.base}/Products"}) == 0

    files = landed(lake)
    assert set(files) == {"adventure_works__products"}
    got = rows(files["adventure_works__products"])
    assert sorted(r[2]["ProductNumber"] for r in got) == ["PG-0001", "PG-0002", "PG-0003"]
    assert len({r[0] for r in got}) == 1, "both pages should be one load"
    assert float(got[0][0]) > 0, "the load id is dlt's seconds-since-epoch"
    assert len({r[1] for r in got}) == 3
    assert got[0][2] in first + second, "the row lands whole, as the feed served it"


def test_failed_resource_does_not_stop_the_rest(feed, lake, capsys, caplog):
    """AC21: one failing resource and one good one: the good one lands, the run exits non-zero naming the failure."""
    feed.pages["/Good"] = (200, {"value": [product(1, "GD-0001", "Good")]})
    # /Missing is not served: 404.

    code = run({"broken__resource": f"{feed.base}/Missing", "good__resource": f"{feed.base}/Good"})

    assert code != 0
    files = landed(lake)
    assert set(files) == {"good__resource"}
    assert [r[2]["ProductNumber"] for r in rows(files["good__resource"])] == ["GD-0001"]
    assert "broken__resource" in said(capsys, caplog)


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_unreachable_feed_changes_nothing(lake, capsys, caplog):
    """EC10: an unreachable feed exits non-zero naming the resource and leaves the lake as it was."""
    existing = lake / "adventure_works__products" / "date=2024-05-29" / "hour=16" / "1717000000.25.a.parquet"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"PAR1 placeholder")
    before = sorted(p.relative_to(lake).as_posix() for p in lake.rglob("*"))

    code = run({"adventure_works__products": f"http://127.0.0.1:{_closed_port()}/Products"})

    assert code != 0
    assert "adventure_works__products" in said(capsys, caplog)
    assert sorted(p.relative_to(lake).as_posix() for p in lake.rglob("*")) == before
    assert existing.read_bytes() == b"PAR1 placeholder"


def test_next_link_to_another_host_is_refused(feed, lake, capsys, caplog):
    """F20: an @odata.nextLink to a host other than the feed's fails the resource and is never requested."""
    foreign = Feed()
    try:
        foreign.pages["/Products?$skiptoken=2"] = (200, {"value": [product(3, "FX-0003", "Foreign")]})
        foreign_link = f"http://localhost:{foreign.server.server_port}/Products?$skiptoken=2"
        feed.pages["/Products"] = (
            200,
            {"value": [product(1, "FX-0001", "Home")], "@odata.nextLink": foreign_link},
        )

        code = run({"adventure_works__products": f"{feed.base}/Products"})

        assert code == 1
        assert foreign.requested == [], f"the foreign host was asked for {foreign.requested}"
        assert feed.requested == ["/Products"]
        assert "adventure_works__products" in said(capsys, caplog)
        assert landed(lake) == {}, "a resource that failed landed rows"
    finally:
        foreign.server.shutdown()


def _two_pages(feed: Feed, next_link: str) -> None:
    feed.pages["/Products"] = (
        200,
        {"value": [product(1, "NL-0001", "One")], "@odata.nextLink": next_link},
    )
    feed.pages["/Products?$skiptoken=2"] = (200, {"value": [product(2, "NL-0002", "Two")]})


def _landed_numbers(lake: Path) -> list[str]:
    files = landed(lake)
    assert set(files) == {"adventure_works__products"}, files
    return sorted(r[2]["ProductNumber"] for r in rows(files["adventure_works__products"]))


def test_relative_next_link_is_followed(feed, lake):
    """ADR-0001: a relative @odata.nextLink is resolved against the page it came from and followed."""
    _two_pages(feed, "Products?$skiptoken=2")

    assert run({"adventure_works__products": f"{feed.base}/Products"}) == 0

    assert feed.requested == ["/Products", "/Products?$skiptoken=2"]
    assert _landed_numbers(lake) == ["NL-0001", "NL-0002"]


def test_next_link_to_same_host_in_upper_case_is_followed(lake):
    """ADR-0001: a next link to the feed's own host spelled in upper case is the same host, and is followed."""
    feed = Feed()
    try:
        port = feed.server.server_port
        _two_pages(feed, f"http://LOCALHOST:{port}/Products?$skiptoken=2")

        assert run({"adventure_works__products": f"http://localhost:{port}/Products"}) == 0

        assert feed.requested == ["/Products", "/Products?$skiptoken=2"]
        assert _landed_numbers(lake) == ["NL-0001", "NL-0002"]
    finally:
        feed.server.shutdown()


def test_next_link_with_explicit_default_port_is_followed(lake):
    """ADR-0001: a next link naming the default port the feed URL leaves implicit is the same port, and is followed."""
    try:
        feed = Feed(port=80)
    except OSError as error:
        pytest.skip(f"cannot serve on port 80 here: {error}")
    try:
        _two_pages(feed, "http://127.0.0.1:80/Products?$skiptoken=2")

        assert run({"adventure_works__products": "http://127.0.0.1/Products"}) == 0

        assert feed.requested == ["/Products", "/Products?$skiptoken=2"]
        assert _landed_numbers(lake) == ["NL-0001", "NL-0002"]
    finally:
        feed.server.shutdown()


@pytest.mark.parametrize("redirected", ["/Products", "/Products?$skiptoken=2"])
def test_redirect_to_another_host_fails_the_resource(feed, lake, capsys, caplog, redirected):
    """ADR-0001: no request follows a redirect: a page answering 302 to another host fails the resource, and that host is never asked."""
    foreign = Feed()
    try:
        foreign.pages["/Products"] = (200, {"value": [product(9, "RD-0009", "Foreign")]})
        foreign.pages["/Products?$skiptoken=2"] = foreign.pages["/Products"]
        _two_pages(feed, f"{feed.base}/Products?$skiptoken=2")
        location = f"http://localhost:{foreign.server.server_port}{redirected}"
        feed.pages[redirected] = (302, {}, {"Location": location})

        code = run({"adventure_works__products": f"{feed.base}/Products"})

        assert code != 0
        assert foreign.requested == [], f"the redirect was followed to {foreign.requested}"
        assert "adventure_works__products" in said(capsys, caplog)
        assert landed(lake) == {}, "a resource that failed landed rows"
    finally:
        foreign.server.shutdown()
