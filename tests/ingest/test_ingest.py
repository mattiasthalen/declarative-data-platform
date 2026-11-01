"""Ingest, declared: one dlt pipeline per declared resource, landing Parquet in the lake (story #17).

The seam these tests call: ``ingest.main(argv) -> int``, the ``uv run ingest`` entry point, run
with the working directory set to a folder holding a ``sources/`` tree. A source is a folder
``sources/<source>/`` holding ``_source.yaml`` (the dlt source's configuration: today the
``rest_api`` client) and one YAML file per resource, each one dlt ``rest_api`` resource entry,
verbatim. The resource's name is its file name; its pipeline and lake folder are
``<source>__<resource>``. ``main`` lands under ``$LAKE_ROOT`` in the layout ``harness.write_load``
writes, names each failure on stderr and returns 0 (all landed), 1 (some landed, some failed) or
2 (none landed, nothing declared, or an unknown name).

Test declarations take their ``_source.yaml`` from the repo's own
``sources/adventure_works/_source.yaml``, with its ``base_url`` pointed at a stub feed, so these
tests hold the reader to the shape the repo declares.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import socket
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import duckdb
import pytest
import yaml

from harness import REPO, product

LAYOUT = re.compile(r"^(?P<resource>[^/]+)/date=\d{4}-\d{2}-\d{2}/hour=\d{2}/[^/]+\.parquet$")
REPO_SOURCE = REPO / "sources" / "adventure_works"


class Feed:
    """A stub OData feed: path (with query) -> (status, JSON body[, extra headers]).

    A path not in ``pages`` is answered by ``routes[path without query](query)`` when one is set,
    so a page can depend on its ``$filter``; anything else is a 404.
    """

    def __init__(self, port: int = 0):
        self.pages: dict[str, tuple] = {}
        self.routes: dict[str, Callable[[dict[str, list[str]]], tuple]] = {}
        self.requested: list[str] = []
        feed = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                feed.requested.append(self.path)
                answer = feed.pages.get(self.path)
                if answer is None:
                    parts = urlsplit(self.path)
                    route = feed.routes.get(parts.path)
                    answer = route(parse_qs(parts.query)) if route else (404, {"error": "no such page"})
                status, body, *extra = answer
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

    def paths(self) -> list[str]:
        """Every path requested, without its query."""
        return [urlsplit(p).path for p in self.requested]


@pytest.fixture
def feed():
    f = Feed()
    yield f
    f.server.shutdown()


@pytest.fixture
def other_feed():
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


@pytest.fixture
def work(tmp_path, monkeypatch, lake) -> Path:
    """The working directory ``ingest`` runs in; its ``sources/`` is what is declared."""
    root = tmp_path / "work"
    root.mkdir()
    monkeypatch.chdir(root)
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


def snapshot(lake: Path) -> dict[str, bytes]:
    """Every file in the lake, byte for byte."""
    return {p.relative_to(lake).as_posix(): p.read_bytes() for p in sorted(lake.rglob("*")) if p.is_file()}


# --------------------------------------------------------------------------- declarations


def _walk_replace(node, key: str, value) -> int:
    """Set every ``key`` in a parsed YAML tree to ``value``; return how many were set."""
    count = 0
    if isinstance(node, dict):
        for k in list(node):
            if k == key:
                node[k] = value
                count += 1
            else:
                count += _walk_replace(node[k], key, value)
    elif isinstance(node, list):
        for item in node:
            count += _walk_replace(item, key, value)
    return count


def _rename_strings(node, old: str, new: str) -> tuple[object, int]:
    """``node`` with every key or string value equal to ``old`` renamed ``new``, and how many were."""
    if isinstance(node, dict):
        out, count = {}, 0
        for k, v in node.items():
            v2, n = _rename_strings(v, old, new)
            count += n + (k == old)
            out[new if k == old else k] = v2
        return out, count
    if isinstance(node, list):
        pairs = [_rename_strings(v, old, new) for v in node]
        return [p[0] for p in pairs], sum(p[1] for p in pairs)
    if node == old:
        return new, 1
    return node, 0


def source_config(base_url: str) -> dict:
    """The repo's own ``_source.yaml`` with its base URL pointed at ``base_url``."""
    path = REPO_SOURCE / "_source.yaml"
    assert path.is_file(), f"{path.relative_to(REPO)} is not declared yet"
    config = yaml.safe_load(path.read_text())
    assert _walk_replace(config, "base_url", base_url) == 1, f"one base_url expected in {path}"
    return config


def entry(path: str, **extra) -> dict:
    """A dlt rest_api resource entry for one OData entity set."""
    return {"endpoint": {"path": path, "data_selector": "value", **extra}}


def declare(work: Path, source: str, base_url: str | None, resources: dict[str, dict | str], config=None) -> Path:
    """Declare ``sources/<source>/``: ``_source.yaml`` (unless ``base_url`` and ``config`` are None)
    and one ``<name>.yaml`` per resource, a dict dumped as YAML or a string written as is."""
    folder = work / "sources" / source
    folder.mkdir(parents=True, exist_ok=True)
    if config is None and base_url is not None:
        config = source_config(base_url)
    if config is not None:
        (folder / "_source.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    for name, body in resources.items():
        text = body if isinstance(body, str) else yaml.safe_dump(body, sort_keys=False)
        (folder / f"{name}.yaml").write_text(text)
    return folder


def ingest(*argv: str) -> int:
    import ingest

    return ingest.main(list(argv))


def stderr(capsys) -> str:
    return capsys.readouterr().err


# --------------------------------------------------------------------------- AC1, AC2: the repo's own declarations


def _transaction(ident: int, modified: str, *, kind: str = "S", quantity: int = 1) -> dict:
    return {
        "TransactionId": ident,
        "ProductId": 1,
        "ReferenceOrderId": 50000 + ident,
        "ReferenceOrderLineId": 1,
        "TransactionDate": modified,
        "TransactionType": kind,
        "Quantity": quantity,
        "ActualCost": 10.5,
        "ModifiedDate": modified,
    }


def test_repo_declarations_land_both_resources(feed, work, lake):
    """AC1: the repo's sources/adventure_works/, pointed at a stub feed, lands both resources whole, exit 0."""
    products = [product(1, "RD-0001", "One"), product(2, "RD-0002", "Two")]
    transactions = [_transaction(1, "2013-07-31T00:00:00"), _transaction(2, "2014-08-01T00:00:00", kind="W")]
    feed.routes["/Products"] = lambda query: (200, {"value": products})
    feed.routes["/TransactionHistories"] = lambda query: (200, {"value": transactions})
    shutil.copytree(REPO_SOURCE, work / "sources" / "adventure_works")
    copied = work / "sources" / "adventure_works" / "_source.yaml"
    copied.write_text(yaml.safe_dump(source_config(f"{feed.base}/"), sort_keys=False))

    assert ingest() == 0

    files = landed(lake)
    assert set(files) == {"adventure_works__products", "adventure_works__transaction_histories"}
    assert sorted((r[2] for r in rows(files["adventure_works__products"])), key=str) == sorted(products, key=str)
    got = [r[2] for r in rows(files["adventure_works__transaction_histories"])]
    assert sorted(got, key=str) == sorted(transactions, key=str)
    filters = [
        parse_qs(urlsplit(p).query).get("$filter", [""])[0]
        for p in feed.requested
        if urlsplit(p).path == "/TransactionHistories"
    ]
    assert filters and filters[0].startswith("ModifiedDate ge "), filters


def test_no_resource_named_in_code():
    """AC2: src/ingest names neither products nor transaction histories."""
    named = []
    for path in sorted((REPO / "src" / "ingest").rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if re.search(r"product|transaction", line, re.IGNORECASE):
                named.append(f"{path.relative_to(REPO)}:{number}: {line.strip()}")
    assert named == [], "\n".join(named)


# --------------------------------------------------------------------------- AC3, AC13, EC1, EC5: failures and exit status


def test_failed_resource_does_not_stop_the_rest(feed, work, lake, capsys):
    """AC3: of two resources, one answering 404: the other lands, stderr names the failed one, exit 1."""
    feed.pages["/Good"] = (200, {"value": [product(1, "GD-0001", "Good")]})
    # /Missing is not served: 404.
    declare(work, "shop", f"{feed.base}/", {"broken": entry("Missing"), "good": entry("Good")})

    code = ingest()

    assert code == 1
    files = landed(lake)
    assert set(files) == {"shop__good"}
    assert [r[2]["ProductNumber"] for r in rows(files["shop__good"])] == ["GD-0001"]
    assert "broken" in stderr(capsys)


def test_exit_status_zero_when_every_resource_landed(feed, work, lake):
    """AC13: every resource run landed: exit 0."""
    feed.pages["/One"] = (200, {"value": [product(1, "EX-0001", "One")]})
    feed.pages["/Two"] = (200, {"value": [product(2, "EX-0002", "Two")]})
    declare(work, "shop", f"{feed.base}/", {"one": entry("One"), "two": entry("Two")})

    assert ingest() == 0
    assert set(landed(lake)) == {"shop__one", "shop__two"}


def test_exit_status_two_when_none_landed(feed, work, lake, capsys):
    """AC13: no resource landed: exit 2, each failure named."""
    declare(work, "shop", f"{feed.base}/", {"first": entry("Missing1"), "second": entry("Missing2")})

    assert ingest() == 2
    said = stderr(capsys)
    assert "first" in said and "second" in said
    assert landed(lake) == {}


@pytest.mark.parametrize("name", ["nonesuch", "nonesuch__items"])
def test_exit_status_two_for_unknown_source(feed, work, lake, capsys, name):
    """AC13: a name that is no declared source: exit 2, the message names it, nothing runs."""
    feed.pages["/Items"] = (200, {"value": [product(1, "UK-0001", "One")]})
    declare(work, "shop", f"{feed.base}/", {"items": entry("Items")})

    assert ingest(name) == 2
    assert name.split("__")[0] in stderr(capsys)
    assert feed.requested == []
    assert landed(lake) == {}


def test_exit_status_two_for_unknown_resource_of_known_source(feed, work, lake, capsys):
    """EC7, AC13: SOURCE__RESOURCE where the source exists and the resource does not: exit 2, named, nothing runs."""
    feed.pages["/Items"] = (200, {"value": [product(1, "UK-0001", "One")]})
    declare(work, "shop", f"{feed.base}/", {"items": entry("Items")})

    assert ingest("shop__nonesuch") == 2
    assert "nonesuch" in stderr(capsys)
    assert feed.requested == []
    assert landed(lake) == {}


def test_exit_status_two_for_empty_resource_after_separator(feed, work, lake, capsys):
    """EC7, AC13: ``SOURCE__`` names no resource: exit 2, the source named on stderr, nothing requested
    and nothing landed (it is not taken for the whole source)."""
    feed.pages["/Items"] = (200, {"value": [product(1, "ER-0001", "One")]})
    declare(work, "shop", f"{feed.base}/", {"items": entry("Items")})

    assert ingest("shop__") == 2
    assert "shop" in stderr(capsys)
    assert feed.requested == []
    assert landed(lake) == {}


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_unreachable_feed_changes_nothing(work, lake, capsys):
    """EC1: an unreachable feed fails its resource, named; the lake is byte for byte as before; exit 2."""
    existing = lake / "adventure_works__products" / "date=2024-05-29" / "hour=16" / "1717000000.25.a.parquet"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"PAR1 placeholder")
    before = snapshot(lake)
    declare(work, "adventure_works", f"http://127.0.0.1:{_closed_port()}/", {"products": entry("Products")})

    code = ingest()

    assert code == 2
    assert "products" in stderr(capsys)
    assert snapshot(lake) == before


def test_failure_on_second_page_lands_nothing(feed, work, lake, capsys):
    """EC5: a resource whose second page answers 404 lands nothing; the other resource lands; exit 1."""
    feed.pages["/Paged"] = (
        200,
        {"value": [product(1, "SP-0001", "One")], "@odata.nextLink": f"{feed.base}/Paged?$skiptoken=1"},
    )
    # /Paged?$skiptoken=1 is not served: 404.
    feed.pages["/Other"] = (200, {"value": [product(2, "SP-0002", "Other")]})
    declare(work, "shop", f"{feed.base}/", {"paged": entry("Paged"), "other": entry("Other")})

    assert ingest() == 1

    assert "/Paged?$skiptoken=1" in feed.requested
    files = landed(lake)
    assert set(files) == {"shop__other"}
    assert "paged" in stderr(capsys)


# --------------------------------------------------------------------------- AC5: the lake shape


def test_row_lands_whole_with_nested_fields(feed, work, lake):
    """AC5: a row with a nested object and array lands whole in ``data`` beside _dlt_load_id and _dlt_id;
    no child-table folder appears."""
    nested = {
        "ProductId": 7,
        "Name": "Nested",
        "Tags": ["road", "red"],
        "Spec": {"Weight": 1.5, "Dims": {"H": 10, "W": 2}, "Parts": [{"Id": 1}, {"Id": 2}]},
        "Missing": None,
    }
    feed.pages["/Things"] = (200, {"value": [nested, product(8, "NS-0008", "Flat")]})
    declare(work, "shop", f"{feed.base}/", {"things": entry("Things")})

    assert ingest() == 0

    files = landed(lake)
    assert set(files) == {"shop__things"}
    assert sorted((r[2] for r in rows(files["shop__things"])), key=str) == sorted(
        [nested, product(8, "NS-0008", "Flat")], key=str
    )
    con = duckdb.connect()
    try:
        columns = dict(
            (name, kind)
            for name, kind, *_ in con.execute(
                # The files' own columns: DuckDB would otherwise read date= and hour= off the path.
                "describe select * from read_parquet(?, hive_partitioning = false)",
                [[p.as_posix() for p in files["shop__things"]]],
            ).fetchall()
        )
    finally:
        con.close()
    assert set(columns) == {"data", "_dlt_load_id", "_dlt_id"}, columns
    assert columns["data"] in ("VARCHAR", "JSON"), columns
    folders = {p.name for p in lake.iterdir() if p.is_dir() and not p.name.startswith("_dlt")}
    assert folders == {"shop__things"}, folders
    assert [p for p in lake.rglob("*") if p.is_dir() and "shop__things__" in p.name] == []


def test_next_link_pages_land_in_one_load(feed, work, lake):
    """AC5: a two-page feed via @odata.nextLink lands every row of both pages in one load."""
    first = [product(1, "PG-0001", "One"), product(2, "PG-0002", "Two")]
    second = [product(3, "PG-0003", "Three")]
    feed.pages["/Products"] = (200, {"value": first, "@odata.nextLink": f"{feed.base}/Products?$skiptoken=2"})
    feed.pages["/Products?$skiptoken=2"] = (200, {"value": second})
    declare(work, "adventure_works", f"{feed.base}/", {"products": entry("Products")})

    assert ingest() == 0

    files = landed(lake)
    assert set(files) == {"adventure_works__products"}
    got = rows(files["adventure_works__products"])
    assert sorted(r[2]["ProductNumber"] for r in got) == ["PG-0001", "PG-0002", "PG-0003"]
    assert len({r[0] for r in got}) == 1, "both pages should be one load"
    assert float(got[0][0]) > 0, "the load id is dlt's seconds-since-epoch"
    assert len({r[1] for r in got}) == 3
    assert got[0][2] in first + second, "the row lands whole, as the feed served it"


# --------------------------------------------------------------------------- AC6: next-link and redirect guards


def _products(work: Path, base_url: str) -> None:
    declare(work, "adventure_works", base_url, {"products": entry("Products")})


def test_next_link_to_another_host_is_refused(feed, other_feed, work, lake, capsys):
    """AC6: an @odata.nextLink to a host other than the feed's fails the resource and is never requested."""
    other_feed.pages["/Products?$skiptoken=2"] = (200, {"value": [product(3, "FX-0003", "Foreign")]})
    foreign_link = f"http://localhost:{other_feed.server.server_port}/Products?$skiptoken=2"
    feed.pages["/Products"] = (200, {"value": [product(1, "FX-0001", "Home")], "@odata.nextLink": foreign_link})
    _products(work, f"{feed.base}/")

    code = ingest()

    assert code == 2
    assert other_feed.requested == [], f"the foreign host was asked for {other_feed.requested}"
    assert feed.requested == ["/Products"]
    assert "products" in stderr(capsys)
    assert landed(lake) == {}, "a resource that failed landed rows"


def test_next_link_with_backslash_before_userinfo_is_refused(feed, other_feed, work, lake, capsys):
    """AC6: a next link that parsers read as different hosts (a backslash before the ``@``) fails the
    resource, and the other host is never asked."""
    feed_hostport = feed.base.removeprefix("http://")
    tricky = f"http://localhost:{other_feed.server.server_port}\\@{feed_hostport}/Products?x"
    feed.pages["/Products"] = (200, {"value": [product(1, "BS-0001", "Home")], "@odata.nextLink": tricky})
    feed.pages["/Products?x"] = (200, {"value": [product(2, "BS-0002", "Feed")]})
    _products(work, f"{feed.base}/")

    code = ingest()

    assert code == 2
    assert other_feed.requested == [], f"the other host was asked for {other_feed.requested}"
    assert feed.requested == ["/Products"]
    assert "products" in stderr(capsys)
    assert landed(lake) == {}, "a resource that failed landed rows"


def _two_pages(feed: Feed, next_link: str) -> None:
    feed.pages["/Products"] = (200, {"value": [product(1, "NL-0001", "One")], "@odata.nextLink": next_link})
    feed.pages["/Products?$skiptoken=2"] = (200, {"value": [product(2, "NL-0002", "Two")]})


def _landed_numbers(lake: Path) -> list[str]:
    files = landed(lake)
    assert set(files) == {"adventure_works__products"}, files
    return sorted(r[2]["ProductNumber"] for r in rows(files["adventure_works__products"]))


def test_relative_next_link_is_followed(feed, work, lake):
    """AC6: a relative @odata.nextLink is resolved against the page it came from and followed."""
    _two_pages(feed, "Products?$skiptoken=2")
    _products(work, f"{feed.base}/")

    assert ingest() == 0

    assert feed.requested == ["/Products", "/Products?$skiptoken=2"]
    assert _landed_numbers(lake) == ["NL-0001", "NL-0002"]


def test_next_link_to_same_host_in_upper_case_is_followed(work, lake):
    """AC6: a next link to the feed's own host spelled in upper case is the same host, and is followed."""
    feed = Feed()
    try:
        port = feed.server.server_port
        _two_pages(feed, f"http://LOCALHOST:{port}/Products?$skiptoken=2")
        _products(work, f"http://localhost:{port}/")

        assert ingest() == 0

        assert feed.requested == ["/Products", "/Products?$skiptoken=2"]
        assert _landed_numbers(lake) == ["NL-0001", "NL-0002"]
    finally:
        feed.server.shutdown()


def test_next_link_with_explicit_default_port_is_followed(work, lake):
    """AC6: a next link naming the default port the feed URL leaves implicit is the same port, and is followed."""
    try:
        feed = Feed(port=80)
    except OSError as error:
        pytest.skip(f"cannot serve on port 80 here: {error}")
    try:
        _two_pages(feed, "http://127.0.0.1:80/Products?$skiptoken=2")
        _products(work, "http://127.0.0.1/")

        assert ingest() == 0

        assert feed.requested == ["/Products", "/Products?$skiptoken=2"]
        assert _landed_numbers(lake) == ["NL-0001", "NL-0002"]
    finally:
        feed.server.shutdown()


@pytest.mark.parametrize("redirected", ["/Products", "/Products?$skiptoken=2"])
def test_redirect_to_another_host_fails_the_resource(feed, other_feed, work, lake, capsys, redirected):
    """AC6: no request follows a redirect: a page answering 302 to another host fails the resource,
    that host is never asked, nothing lands."""
    other_feed.pages["/Products"] = (200, {"value": [product(9, "RD-0009", "Foreign")]})
    other_feed.pages["/Products?$skiptoken=2"] = other_feed.pages["/Products"]
    _two_pages(feed, f"{feed.base}/Products?$skiptoken=2")
    location = f"http://localhost:{other_feed.server.server_port}{redirected}"
    feed.pages[redirected] = (302, {}, {"Location": location})
    _products(work, f"{feed.base}/")

    code = ingest()

    assert code == 2
    assert other_feed.requested == [], f"the redirect was followed to {other_feed.requested}"
    assert "products" in stderr(capsys)
    assert landed(lake) == {}, "a resource that failed landed rows"


def _foreign_page(other_feed: Feed) -> None:
    """What the other host would serve, so that a request to it would land rows."""
    page = (200, {"value": [product(9, "FG-0009", "Foreign")]})
    for path in ("/Products", "/Products?page=2"):
        other_feed.pages[path] = page


def _assert_refused_without_asking(code: int, feed: Feed, other_feed: Feed, lake: Path, said: str) -> None:
    assert code == 2, said
    assert other_feed.requested == [], f"the other host was asked for {other_feed.requested}"
    assert "products" in said
    assert landed(lake) == {}, "a resource that failed landed rows"


def test_next_link_guard_holds_for_json_link_paginator(feed, other_feed, work, lake, capsys):
    """AC6, every paginator: a resource declaring a json_link paginator whose ``next`` points at another
    host fails, and that host is never asked."""
    _foreign_page(other_feed)
    foreign = f"http://localhost:{other_feed.server.server_port}/Products?page=2"
    feed.pages["/Products"] = (200, {"value": [product(1, "JL-0001", "Home")], "next": foreign})
    declare(
        work,
        "adventure_works",
        f"{feed.base}/",
        {"products": entry("Products", paginator={"type": "json_link", "next_url_path": "next"})},
    )

    code = ingest()

    _assert_refused_without_asking(code, feed, other_feed, lake, stderr(capsys))
    assert feed.requested == ["/Products"]


def test_next_link_guard_holds_for_header_link_paginator(feed, other_feed, work, lake, capsys):
    """AC6, every paginator: a resource declaring a header_link paginator whose ``Link: rel="next"``
    points at another host fails, and that host is never asked."""
    _foreign_page(other_feed)
    foreign = f"http://localhost:{other_feed.server.server_port}/Products?page=2"
    feed.pages["/Products"] = (
        200,
        {"value": [product(1, "HL-0001", "Home")]},
        {"Link": f'<{foreign}>; rel="next"'},
    )
    declare(work, "adventure_works", f"{feed.base}/", {"products": entry("Products", paginator={"type": "header_link"})})

    code = ingest()

    _assert_refused_without_asking(code, feed, other_feed, lake, stderr(capsys))
    assert feed.requested == ["/Products"]


@pytest.mark.parametrize("hint", ["body", "header"])
def test_next_link_guard_holds_for_auto_detected_paginator(feed, other_feed, work, lake, capsys, hint):
    """AC6, every paginator: with no paginator named in _source.yaml, dlt detects one from the first page;
    a next link it detects to another host fails the resource, and that host is never asked."""
    _foreign_page(other_feed)
    foreign = f"http://localhost:{other_feed.server.server_port}/Products?page=2"
    rows_ = [product(1, "AD-0001", "Home")]
    if hint == "body":
        feed.pages["/Products"] = (200, {"value": rows_, "next": foreign})
    else:
        feed.pages["/Products"] = (200, {"value": rows_}, {"Link": f'<{foreign}>; rel="next"'})
    config = source_config(f"{feed.base}/")
    assert config["rest_api"]["client"].pop("paginator", None) is not None, "the repo's _source.yaml names no paginator"
    declare(work, "adventure_works", None, {"products": entry("Products")}, config=config)

    code = ingest()

    _assert_refused_without_asking(code, feed, other_feed, lake, stderr(capsys))
    assert feed.requested == ["/Products"]


def test_absolute_endpoint_path_to_another_host_is_refused(feed, other_feed, work, lake, capsys):
    """AC6, every request: a resource whose endpoint.path is an absolute URL on another host fails, and
    that host is never asked."""
    _foreign_page(other_feed)
    declare(
        work,
        "adventure_works",
        f"{feed.base}/",
        {"products": entry(f"http://localhost:{other_feed.server.server_port}/Products")},
    )

    code = ingest()

    _assert_refused_without_asking(code, feed, other_feed, lake, stderr(capsys))


API_KEY = "SECRET-KEY-9"
LOCATION_SECRET = "SECRET-LOC-3"


def _keyed_products(work: Path, feed: Feed) -> None:
    """``products``, its client sending an api key in the query string of every request."""
    config = source_config(f"{feed.base}/")
    config["rest_api"]["client"]["auth"] = {"type": "api_key", "location": "query", "name": "key", "api_key": API_KEY}
    declare(work, "adventure_works", None, {"products": entry("Products")}, config=config)


@pytest.mark.parametrize("hop", ["next_link", "redirect"])
def test_origin_refusal_does_not_print_the_request(feed, other_feed, work, lake, capfd, hop):
    """AC6, X3: a hop to another host, refused, fails the resource without printing the request: not
    the api key the client put in its query string, nor a value the redirect's Location carried."""
    _foreign_page(other_feed)
    foreign = f"http://localhost:{other_feed.server.server_port}/Products?page=2&sig={LOCATION_SECRET}"
    home = [product(1, "SK-0001", "Home")]
    if hop == "next_link":
        feed.routes["/Products"] = lambda query: (200, {"value": home, "@odata.nextLink": foreign})
    else:
        feed.routes["/Products"] = lambda query: (302, {}, {"Location": foreign})
    _keyed_products(work, feed)

    code = ingest()

    out = capfd.readouterr()
    _assert_refused_without_asking(code, feed, other_feed, lake, out.err)
    assert feed.requested and all(parse_qs(urlsplit(p).query).get("key") == [API_KEY] for p in feed.requested), (
        f"the declared api key was not sent: {feed.requested}"
    )
    for secret in (API_KEY, LOCATION_SECRET):
        assert secret not in out.out and secret not in out.err, out.err


# --------------------------------------------------------------------------- AC7, AC14, EC3, EC6: declarations checked


def _good_source(work: Path, feed: Feed) -> None:
    feed.pages["/Good"] = (200, {"value": [product(1, "OK-0001", "Good")]})
    declare(work, "good", f"{feed.base}/", {"items": entry("Good")})


def _served(feed: Feed, *paths: str) -> None:
    for i, path in enumerate(paths):
        feed.pages[f"/{path}"] = (200, {"value": [product(100 + i, f"BD-{i:04d}", path)]})


@pytest.mark.parametrize("disposition", ["replace", "merge"])
def test_append_only_refuses_other_dispositions(feed, work, lake, capsys, disposition):
    """AC7: a resource declaring write_disposition replace or merge fails its source, naming the file;
    nothing of that source lands, another source still does (exit 1)."""
    _good_source(work, feed)
    _served(feed, "Fine", "Other")
    declare(
        work,
        "bad",
        f"{feed.base}/",
        {"fine": entry("Fine"), "other": {**entry("Other"), "write_disposition": disposition}},
    )

    code = ingest()

    assert code == 1
    assert "other.yaml" in stderr(capsys)
    assert set(landed(lake)) == {"good__items"}


@pytest.mark.parametrize("disposition", ["replace", "merge"])
def test_append_only_refuses_source_level_dispositions(feed, work, lake, capsys, disposition):
    """AC7: a write_disposition of replace or merge under _source.yaml's rest_api.resource_defaults fails
    its source, naming _source.yaml; nothing of that source lands, another source still does (exit 1)."""
    _good_source(work, feed)
    _served(feed, "Fine", "Other")
    config = source_config(f"{feed.base}/")
    config["rest_api"].setdefault("resource_defaults", {})["write_disposition"] = disposition
    declare(work, "bad", None, {"fine": entry("Fine"), "other": entry("Other")}, config=config)

    code = ingest()

    said = stderr(capsys)
    assert code == 1, said
    assert "_source.yaml" in said
    assert set(landed(lake)) == {"good__items"}


def _bad_paginator(config: dict) -> dict:
    assert _walk_replace(config, "paginator", "nonesuch") >= 1, "the repo's _source.yaml names no paginator"
    return config


def _unknown_kind(config: dict) -> dict:
    renamed, count = _rename_strings(config, "rest_api", "nonesuch_source")
    assert count >= 1, "the repo's _source.yaml does not name its dlt source rest_api"
    return renamed


# (case, how to declare the bad source, any of these names the bad file on stderr)
BAD_DECLARATIONS = {
    "yaml_does_not_parse": (
        lambda work, base: declare(work, "bad", base, {"fine": entry("Fine"), "broken": "endpoint: [path: Other\n  : :"}),
        ["broken.yaml"],
    ),
    "unknown_dlt_source_kind": (
        lambda work, base: declare(work, "bad", None, {"fine": entry("Fine")}, config=_unknown_kind(source_config(base))),
        ["_source.yaml"],
    ),
    "unregistered_paginator": (
        lambda work, base: declare(work, "bad", None, {"fine": entry("Fine")}, config=_bad_paginator(source_config(base))),
        ["_source.yaml"],
    ),
    "name_differs_from_file_name": (
        lambda work, base: declare(work, "bad", base, {"fine": entry("Fine"), "other": {"name": "elsewhere", **entry("Other")}}),
        ["other.yaml"],
    ),
    "resource_without_source_file": (
        lambda work, base: declare(work, "bad", None, {"fine": entry("Fine"), "other": entry("Other")}),
        ["_source.yaml", "fine.yaml", "other.yaml"],
    ),
    "source_file_without_resource": (
        lambda work, base: declare(work, "bad", base, {}),
        ["_source.yaml"],
    ),
    "file_name_not_snake_case_capital": (
        lambda work, base: declare(work, "bad", base, {"fine": entry("Fine"), "Products": entry("Other")}),
        ["Products.yaml"],
    ),
    "file_name_not_snake_case_hyphen": (
        lambda work, base: declare(work, "bad", base, {"fine": entry("Fine"), "product-lines": entry("Other")}),
        ["product-lines.yaml"],
    ),
    # A double underscore separates source from resource in <source>__<resource>.
    "resource_name_with_double_underscore": (
        lambda work, base: declare(work, "bad", base, {"fine": entry("Fine"), "b__c": entry("Other")}),
        ["b__c.yaml"],
    ),
    "resource_name_ending_in_underscore": (
        lambda work, base: declare(work, "bad", base, {"fine": entry("Fine"), "other_": entry("Other")}),
        ["other_.yaml"],
    ),
    "source_name_with_double_underscore": (
        lambda work, base: declare(work, "a__b", base, {"fine": entry("Fine")}),
        ["a__b"],
    ),
    "source_name_ending_in_underscore": (
        lambda work, base: declare(work, "bad_", base, {"fine": entry("Fine")}),
        ["bad_"],
    ),
}


@pytest.mark.parametrize("case", list(BAD_DECLARATIONS))
def test_bad_declaration_fails_only_its_source(feed, work, lake, capsys, case):
    """AC14, EC6: a bad declaration fails its own source, names the file on stderr and lands nothing of
    that source, while another valid source still lands (exit 1)."""
    _good_source(work, feed)
    _served(feed, "Fine", "Other")
    make, names = BAD_DECLARATIONS[case]
    make(work, f"{feed.base}/")

    code = ingest()

    said = stderr(capsys)
    assert code == 1, said
    assert any(name in said for name in names), f"none of {names} named in: {said}"
    assert set(landed(lake)) == {"good__items"}


def test_ignores_other_files(feed, work, lake):
    """EC3: a non-YAML file in a source folder (a README) is ignored; the source runs."""
    feed.pages["/Items"] = (200, {"value": [product(1, "RM-0001", "One")]})
    folder = declare(work, "shop", f"{feed.base}/", {"items": entry("Items")})
    (folder / "README.md").write_text("# shop\n\nNot a resource: notes: [unparsed\n")
    (folder / "items.yml.bak").write_text("endpoint: [broken\n")

    assert ingest() == 0
    assert set(landed(lake)) == {"shop__items"}


SECRET = "s3cret-token"


def test_refusal_does_not_echo_declared_values(feed, work, lake, capsys):
    """AC14, X3: a resource refused for an unknown endpoint key fails its source naming the file, but
    no declared value (a header's token) is printed: a valid source still lands (exit 1)."""
    _good_source(work, feed)
    _served(feed, "Fine", "Other")
    secret = entry("Other", headers={"Authorization": f"Bearer {SECRET}"}, nonsense=1)
    declare(work, "bad", f"{feed.base}/", {"fine": entry("Fine"), "other": secret})

    code = ingest()

    out = capsys.readouterr()
    assert code == 1, out.err
    assert "other.yaml" in out.err
    assert SECRET not in out.out and SECRET not in out.err, out.err
    assert set(landed(lake)) == {"good__items"}
    assert all(urlsplit(p).path != "/Other" for p in feed.requested)


def _scalar_auth(work: Path, base: str) -> None:
    config = source_config(base)
    config["rest_api"]["client"]["auth"] = "SECRET-TOKEN-6"
    declare(work, "bad", None, {"fine": entry("Fine"), "other": entry("Other")}, config=config)


def _numeric_header(work: Path, base: str) -> None:
    declare(work, "bad", base, {"fine": entry("Fine"), "other": entry("Other", headers={"Authorization": 999111222})})


# (case, how to declare the bad source, the file named on stderr, the value that must not be printed)
REJECTED_SCALARS = {
    "client_auth_string": (_scalar_auth, "_source.yaml", "SECRET-TOKEN-6"),
    "header_value_number": (_numeric_header, "other.yaml", "999111222"),
}


@pytest.mark.parametrize("case", list(REJECTED_SCALARS))
def test_rejected_scalar_value_is_not_printed(feed, work, lake, capfd, case):
    """AC14, X3: a declared scalar dlt rejects (an auth given as a bare string, a header value that is
    a number) fails its source naming the file, without printing the value; a valid source still
    lands (exit 1)."""
    _good_source(work, feed)
    _served(feed, "Fine", "Other")
    make, named, value = REJECTED_SCALARS[case]
    make(work, f"{feed.base}/")

    code = ingest()

    out = capfd.readouterr()
    assert code == 1, out.err
    assert named in out.err, out.err
    assert value not in out.out and value not in out.err, out.err
    assert set(landed(lake)) == {"good__items"}


@pytest.mark.parametrize("folder", ["_template", "__pycache__"])
def test_underscore_folder_is_not_a_source(feed, work, lake, capsys, folder):
    """A7: a folder under sources/ whose name starts with ``_`` (a template, ``__pycache__``) is not a
    source, whatever it holds: a valid source beside it lands, exit 0, and --list does not print it."""
    _good_source(work, feed)
    junk = work / "sources" / folder
    junk.mkdir()
    (junk / "_source.yaml").write_text("endpoint: [broken\n")
    (junk / "Not-A-Resource.yaml").write_text("nonsense: 1\n")
    (junk / "ingest.cpython-312.pyc").write_bytes(b"\x00\x01junk")

    code = ingest()

    said = stderr(capsys)
    assert code == 0, said
    assert folder not in said
    assert set(landed(lake)) == {"good__items"}

    assert ingest("--list") == 0
    assert capsys.readouterr().out.splitlines() == ["good"]


# --------------------------------------------------------------------------- AC10, AC11, AC12, EC2: the CLI


def test_list_prints_sources(feed, work, lake, capsys):
    """AC10: --list prints each declared source once per line, sorted, and exits 0, asking no feed."""
    declare(work, "zeta", f"{feed.base}/", {"one": entry("One"), "two": entry("Two")})
    declare(work, "alpha", f"{feed.base}/", {"items": entry("Items")})

    assert ingest("--list") == 0

    assert capsys.readouterr().out.splitlines() == ["alpha", "zeta"]
    assert feed.requested == []
    assert landed(lake) == {}


def test_one_source_runs_only_its_resources(feed, other_feed, work, lake):
    """AC11: ``ingest SOURCE`` runs only that source: another declared source's feed is never requested."""
    feed.pages["/X"] = (200, {"value": [product(1, "OS-0001", "X")]})
    feed.pages["/Y"] = (200, {"value": [product(2, "OS-0002", "Y")]})
    other_feed.pages["/Z"] = (200, {"value": [product(3, "OS-0003", "Z")]})
    declare(work, "a", f"{feed.base}/", {"x": entry("X"), "y": entry("Y")})
    declare(work, "b", f"{other_feed.base}/", {"z": entry("Z")})

    assert ingest("a") == 0

    assert other_feed.requested == []
    assert set(landed(lake)) == {"a__x", "a__y"}


def test_one_resource_runs_alone(feed, work, lake):
    """AC12: ``ingest SOURCE__RESOURCE`` runs only that resource: the source's others are never requested."""
    feed.pages["/X"] = (200, {"value": [product(1, "OR-0001", "X")]})
    feed.pages["/Y"] = (200, {"value": [product(2, "OR-0002", "Y")]})
    declare(work, "a", f"{feed.base}/", {"x": entry("X"), "y": entry("Y")})

    assert ingest("a__x") == 0

    assert "/Y" not in feed.paths()
    assert set(landed(lake)) == {"a__x"}


@pytest.mark.parametrize("sources", ["missing", "empty"])
def test_no_sources_declared(work, lake, capsys, sources):
    """EC2: with no sources/ folder, or one holding no source folder, ingest exits 2 saying no source is
    declared, and --list prints nothing and exits 0."""
    if sources == "empty":
        (work / "sources").mkdir()

    assert ingest() == 2
    assert "source" in stderr(capsys).lower()

    assert ingest("--list") == 0
    assert capsys.readouterr().out == ""
    assert landed(lake) == {}


# --------------------------------------------------------------------------- AC8, AC9, AC17, EC4: incremental


INITIAL = "2013-07-31T00:00:00"


def _moment(text: str) -> datetime:
    """An OData date or datetime literal, naive UTC, for comparing whatever form the cursor is sent in."""
    text = text.strip().strip("'\"")
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment


class Histories:
    """A TransactionHistories entity set answering ``$filter=ModifiedDate ge <value>`` from ``rows``."""

    def __init__(self, feed: Feed, rows: list[dict]):
        self.rows = rows
        self.filters: list[str] = []
        feed.routes["/TransactionHistories"] = self.answer

    def answer(self, query: dict[str, list[str]]) -> tuple:
        text = query.get("$filter", [""])[0]
        self.filters.append(text)
        match = re.fullmatch(r"\s*ModifiedDate\s+ge\s+(.+?)\s*", text)
        if not match:
            return 400, {"error": f"expected $filter=ModifiedDate ge <value>, got {text!r}"}
        since = _moment(match[1])
        return 200, {"value": [r for r in self.rows if _moment(r["ModifiedDate"]) >= since]}

    def asked_from(self, index: int) -> datetime:
        return _moment(re.fullmatch(r"\s*ModifiedDate\s+ge\s+(.+?)\s*", self.filters[index])[1])


def _incremental_source(work: Path, feed: Feed) -> None:
    declare(
        work,
        "adventure_works",
        f"{feed.base}/",
        {
            "transaction_histories": entry(
                "TransactionHistories",
                params={"$filter": "ModifiedDate ge {incremental.start_value}"},
                incremental={"cursor_path": "ModifiedDate", "initial_value": INITIAL},
            )
        },
    )


RESOURCE = "adventure_works__transaction_histories"
FIRST = [
    _transaction(1, "2013-07-31T00:00:00"),
    _transaction(2, "2014-08-01T00:00:00"),  # the largest ModifiedDate, served out of order
    _transaction(3, "2013-09-15T00:00:00"),
]


def _first_run(feed: Feed, work: Path, lake: Path) -> tuple[Histories, dict[Path, bytes]]:
    histories = Histories(feed, copy.deepcopy(FIRST))
    _incremental_source(work, feed)
    assert ingest() == 0
    files = landed(lake)
    assert set(files) == {RESOURCE}
    assert sorted(r[2]["TransactionId"] for r in rows(files[RESOURCE])) == [1, 2, 3]
    return histories, {p: p.read_bytes() for p in files[RESOURCE]}


def _assert_second_load_beside_first(lake: Path, first: dict[Path, bytes]) -> None:
    files = landed(lake)
    assert set(files) == {RESOURCE}
    assert set(first) < set(files[RESOURCE]), "the second load should land new files beside the first's"
    for path, data in first.items():
        assert path.read_bytes() == data, f"{path} changed"
    new = [p for p in files[RESOURCE] if p not in first]
    got = rows(new)
    assert 4 in {r[2]["TransactionId"] for r in got}, "the new row did not land"
    assert {r[2]["TransactionId"] for r in got} <= {2, 4}, "rows before the cursor were fetched again"
    assert not {r[0] for r in got} & {r[0] for r in rows(list(first))}, "the second run is its own load"


def test_incremental_asks_from_last_cursor_inclusive(feed, work, lake):
    """AC8, EC4: the first request asks from the declared initial value, the second from the largest
    ModifiedDate of the first load, inclusive; the second load lands beside the first, unchanged."""
    histories, first = _first_run(feed, work, lake)
    assert histories.asked_from(0) == _moment(INITIAL)

    histories.rows.append(_transaction(4, "2014-08-02T00:00:00"))
    assert ingest() == 0

    assert histories.asked_from(len(histories.filters) - 1) == _moment("2014-08-01T00:00:00")
    _assert_second_load_beside_first(lake, first)


def test_incremental_resumes_from_lake_state(feed, work, lake, tmp_path, monkeypatch):
    """AC9: the second run resumes from the cursor with a fresh, empty dlt data folder: state is read
    back from the lake."""
    histories, first = _first_run(feed, work, lake)

    fresh = tmp_path / "fresh-dlt"
    fresh.mkdir()
    monkeypatch.setenv("DLT_DATA_DIR", str(fresh))
    histories.rows.append(_transaction(4, "2014-08-02T00:00:00"))
    assert ingest() == 0

    assert histories.asked_from(len(histories.filters) - 1) == _moment("2014-08-01T00:00:00")
    _assert_second_load_beside_first(lake, first)


@pytest.mark.parametrize("lake_after", ["deleted", "restored_from_backup"])
def test_incremental_lake_wins_over_local_state(feed, work, lake, tmp_path, lake_after):
    """AC9, A3: the lake holds the cursor, not the local dlt data folder, which is kept throughout.

    deleted: after the first run the lake is deleted whole; the next run asks from the declared
    initial value again and lands every row again.
    restored_from_backup: the lake is backed up after the first run, a second run advances the
    cursor, then the backup is put back; the next run asks from the first run's cursor, which is
    what the lake holds, not from the second's, which only the local folder remembers.
    """
    histories, _ = _first_run(feed, work, lake)
    assert histories.asked_from(0) == _moment(INITIAL)
    if lake_after == "deleted":
        shutil.rmtree(lake)
        expected, ids = INITIAL, {1, 2, 3}
    else:
        backup = tmp_path / "lake-backup"
        shutil.copytree(lake, backup)
        histories.rows.append(_transaction(4, "2014-08-02T00:00:00"))
        assert ingest() == 0
        assert histories.asked_from(len(histories.filters) - 1) == _moment("2014-08-01T00:00:00")
        shutil.rmtree(lake)
        shutil.copytree(backup, lake)
        # The first load's rows, and row 4 again (row 2, at the cursor, may come again or not).
        expected, ids = "2014-08-01T00:00:00", {1, 2, 3, 4}

    asked = len(histories.filters)
    assert ingest() == 0

    assert len(histories.filters) > asked, "the run asked nothing"
    assert histories.asked_from(asked) == _moment(expected)
    files = landed(lake)
    assert set(files) == {RESOURCE}
    assert {r[2]["TransactionId"] for r in rows(files[RESOURCE])} == ids


def test_incremental_no_new_rows_lands_nothing(feed, work, lake):
    """AC17: an incremental run whose feed has no new rows exits 0 and lands no new file."""
    histories, first = _first_run(feed, work, lake)

    histories.rows.clear()
    assert ingest() == 0

    assert set(landed(lake).get(RESOURCE, [])) == set(first)
    for path, data in first.items():
        assert path.read_bytes() == data


def test_interrupted_load_is_not_landed_twice(feed, work, lake, monkeypatch, capsys):
    """A load interrupted after its files are written leaves its package pending in the dlt data
    folder; the next run finishes that load, exit 0, and every row is in the lake exactly once."""
    from dlt.load.load import Load

    served = [product(i, f"IL-{i:04d}", f"Row {i}") for i in (1, 2, 3)]
    feed.pages["/Products"] = (200, {"value": served})
    _products(work, f"{feed.base}/")

    complete_package = Load.complete_package
    interrupted = []

    def interrupt_once(self, load_id, schema, aborted=False):
        if not aborted and not interrupted:
            interrupted.append(load_id)
            raise RuntimeError("interrupted after writing the load's files")
        return complete_package(self, load_id, schema, aborted)

    monkeypatch.setattr(Load, "complete_package", interrupt_once)
    assert ingest() != 0, stderr(capsys)
    assert interrupted, "the load never reached completion: nothing was interrupted"
    written = landed(lake).get("adventure_works__products", [])
    assert written, "the interrupted load wrote no files to the lake: the case is not the one pinned"

    code = ingest()

    assert code == 0, stderr(capsys)
    files = landed(lake)
    assert set(files) == {"adventure_works__products"}
    con = duckdb.connect()
    try:
        numbers = sorted(
            n
            for (n,) in con.execute(
                "select json_extract_string(cast(data as varchar), '$.ProductNumber')"
                " from read_parquet(?, hive_partitioning = false)",
                [[p.as_posix() for p in files["adventure_works__products"]]],
            ).fetchall()
        )
    finally:
        con.close()
    assert numbers == ["IL-0001", "IL-0002", "IL-0003"], f"rows landed {numbers}"


# --------------------------------------------------------------------------- AC16: the tasks


def test_taskfile_ingest_tasks_call_the_cli():
    """AC16: task ingest, ingest:list and ingest:source -- SOURCE call uv run ingest, --list and SOURCE."""
    tasks = yaml.safe_load((REPO / "Taskfile.yml").read_text())["tasks"]

    def cmds(name: str) -> list[str]:
        assert name in tasks, f"no task {name}"
        return [c["cmd"] if isinstance(c, dict) else c for c in tasks[name].get("cmds", [])]

    assert cmds("ingest") == ["uv run ingest"]
    assert cmds("ingest:list") == ["uv run ingest --list"]
    source = cmds("ingest:source")
    assert len(source) == 1 and re.fullmatch(r"uv run ingest \{\{ ?\.CLI_ARGS ?\}\}", source[0]), source


def test_taskfile_ingest_source_requires_a_name():
    """AC16, A6: ``task ingest:source`` with no name must not run every source: the task refuses to
    run unless CLI_ARGS is set."""
    task = yaml.safe_load((REPO / "Taskfile.yml").read_text())["tasks"]["ingest:source"]
    checks = [p["sh"] if isinstance(p, dict) else p for p in task.get("preconditions", [])]
    assert any(
        re.search(r"test\s+-n\s+[\"']?\{\{ ?\.CLI_ARGS ?\}\}", c) for c in checks
    ), f"ingest:source has no precondition on CLI_ARGS: {checks}"
