"""Land each declared resource in the lake, one dlt pipeline per resource (ADR-0001, ADR-0013).

A source is a folder ``sources/<source>/``: ``_source.yaml`` holds its dlt source's configuration
under the source kind's name (``rest_api:``), less the resources, and every other ``*.yaml`` file
is one resource entry named for the file (ADR-0014). Each resource lands as
``$LAKE_ROOT/<source>__<resource>/date=YYYY-MM-DD/hour=HH/<load_id>.<file_id>.parquet``, every row
whole as the JSON text the feed served in a column named ``data``, beside dlt's ``_dlt_load_id``
and ``_dlt_id``. What a declaration cannot change is applied here: rows land whole, loads are
appended, and no request follows a redirect.

``uv run ingest [--list | SOURCE | SOURCE__RESOURCE]`` exits 0 when every resource it ran landed,
1 when some landed and some failed, 2 when none landed or a name is unknown (ADR-0015).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SOURCES = Path("sources")
SOURCE_FILE = "_source.yaml"
# snake_case without a double underscore, which separates the source from the resource in names
# built from both (ADR-0002, ADR-0014).
NAME = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")

# dlt writes under <bucket>/<dataset>/<layout>. Its own bookkeeping lands in the dataset folder,
# $LAKE_ROOT/_dlt/; the layout steps out of it so each resource sits directly under $LAKE_ROOT.
DATASET = "_dlt"
LAYOUT = "../{table_name}/date={YYYY}-{MM}-{DD}/hour={HH}/{load_id}.{file_id}.{ext}"

DEFAULT_PORTS = {"http": 80, "https": 443}


def lake_root() -> Path:
    import os

    return Path(os.environ.get("LAKE_ROOT", "lake")).resolve()


# --------------------------------------------------------------------------- declarations


class Refused(Exception):
    """A declaration ingest will not run; the message names the file."""


@dataclass
class Source:
    name: str
    kind: str = ""
    config: dict = field(default_factory=dict)
    resources: dict[str, dict] = field(default_factory=dict)
    problem: str | None = None


def read_sources(root: Path = SOURCES) -> list[Source]:
    """Every folder under ``root``, sorted, each read and checked; a bad one carries its problem."""
    if not root.is_dir():
        return []
    sources = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        source = Source(folder.name)
        try:
            read_source(folder, source)
        except Refused as error:
            source.problem = str(error)
        sources.append(source)
    return sources


def read_source(folder: Path, source: Source) -> None:
    if not NAME.fullmatch(source.name):
        raise Refused(f"{folder}: a source's name must be snake_case, with no double underscore")
    files = sorted(folder.glob("*.yaml"))
    resource_files = [p for p in files if p.name != SOURCE_FILE]
    if not (folder / SOURCE_FILE).is_file():
        raise Refused(f"{folder / SOURCE_FILE} is missing")
    if not resource_files:
        raise Refused(f"{folder / SOURCE_FILE} has no resource file beside it")

    declared = load_yaml(folder / SOURCE_FILE)
    if not isinstance(declared, dict) or len(declared) != 1:
        raise Refused(f"{folder / SOURCE_FILE} must hold exactly one dlt source kind, such as rest_api:")
    [(source.kind, source.config)] = declared.items()
    if source.kind not in KINDS:
        raise Refused(f"{folder / SOURCE_FILE}: unknown dlt source kind {source.kind!r}; known: {', '.join(KINDS)}")
    if not isinstance(source.config, dict):
        raise Refused(f"{folder / SOURCE_FILE}: {source.kind} must hold a mapping")
    KINDS[source.kind].check_source(folder / SOURCE_FILE, source.config)

    for path in resource_files:
        name = path.stem
        if not NAME.fullmatch(name):
            raise Refused(f"{path}: a resource's file name must be snake_case, with no double underscore")
        entry = load_yaml(path)
        if not isinstance(entry, dict):
            raise Refused(f"{path} must hold a mapping")
        if entry.get("name", name) != name:
            raise Refused(f"{path}: name {entry['name']!r} differs from the file name {name!r}")
        defaults = source.config.get("resource_defaults") or {}
        disposition = {**defaults, **entry}.get("write_disposition", "append")
        if isinstance(disposition, dict):
            disposition = disposition.get("disposition")
        if disposition != "append":
            where = path if "write_disposition" in entry else folder / SOURCE_FILE
            raise Refused(f"{where}: write_disposition {disposition!r} refused; every load is appended")
        entry = {**entry, "name": name}
        KINDS[source.kind].check_resource(path, source.config, entry)
        source.resources[name] = entry


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise Refused(f"{path} is not valid YAML: {error}") from None


# --------------------------------------------------------------------------- rest_api


def origin(url: str) -> tuple[str, str, int | None]:
    """The scheme, host and port a URL reaches, the port spelled out when it is the default.

    Read the way urllib3 reads it, since urllib3 sends the request; a backslash, which parsers
    split differently, is refused outright.
    """
    from urllib3.util import parse_url

    if "\\" in url:
        raise ValueError(f"{url} holds a backslash")
    parts = parse_url(url)
    scheme = (parts.scheme or "").lower()
    return scheme, (parts.host or "").lower(), parts.port or DEFAULT_PORTS.get(scheme)


def odata_paginator():
    """The ``odata`` paginator: follows ``@odata.nextLink``, resolved against the page it came from.
    Where it may lead is the session's to refuse, not the paginator's."""
    from dlt.sources.helpers.rest_client.paginators import JSONLinkPaginator

    class ODataPaginator(JSONLinkPaginator):
        def __init__(self) -> None:
            super().__init__(next_url_path="['@odata.nextLink']")

    return ODataPaginator


def guarded_session(base_url: str):
    """dlt's retrying session, made to send nothing beyond ``base_url``'s origin and to answer a
    redirect with an error instead of following it: the feed names where the next request goes
    (a next link, a Location), and must not be able to send it elsewhere. Every request a resource
    makes passes through here, whatever paginator or path its declaration names."""
    from dlt.sources.helpers.requests.retry import Client

    home = origin(base_url)
    session = Client(raise_for_status=False).session
    retrying_send = session.send

    def send(request, **kwargs):
        if origin(request.url) != home:
            raise ValueError(f"{request.url} leaves the feed's origin {home}")
        kwargs["allow_redirects"] = False
        response = retrying_send(request, **kwargs)
        if response.is_redirect:
            raise ValueError(f"{request.url} redirects to {response.headers.get('location')}; redirects are not followed")
        return response

    session.send = send
    return session


class RestApi:
    """The ``rest_api`` kind: ``_source.yaml`` holds dlt's RESTAPIConfig less ``resources``; each
    resource file is one entry of ``resources``."""

    registered = False

    @classmethod
    def register(cls) -> None:
        if not cls.registered:
            from dlt.sources.rest_api.config_setup import register_paginator

            register_paginator("odata", odata_paginator())
            cls.registered = True

    @classmethod
    def build(cls, config: dict, entry: dict):
        """The one dlt resource ``entry`` declares; nothing is requested until it is iterated."""
        from dlt.sources.rest_api import rest_api_resources

        cls.register()
        client = config.get("client") or {}
        if not isinstance(client, dict) or not isinstance(client.get("base_url"), str):
            raise ValueError("client.base_url is required")
        client = {**client, "session": guarded_session(client["base_url"])}
        [resource] = rest_api_resources({**config, "client": client, "resources": [entry]})
        return resource

    @classmethod
    def check_source(cls, path: Path, config: dict) -> None:
        if "resources" in config:
            raise Refused(f"{path}: resources are declared one per file beside it, not here")
        try:
            cls.build(config, {"name": "_check", "endpoint": {"path": ""}})
        except Exception as error:
            raise Refused(f"{path}: {error}") from None

    @classmethod
    def check_resource(cls, path: Path, config: dict, entry: dict) -> None:
        try:
            cls.build(config, entry)
        except Exception as error:
            raise Refused(f"{path}: {error}") from None


KINDS: dict[str, type[RestApi]] = {"rest_api": RestApi}


# --------------------------------------------------------------------------- landing


def as_landed(row: dict) -> dict:
    return {"data": json.dumps(row)}


def land(source: Source, resource_name: str) -> None:
    """Run the one pipeline that lands ``resource_name`` of ``source`` as one load."""
    import dlt

    resource = KINDS[source.kind].build(source.config, source.resources[resource_name])
    # Placed after every step dlt put there, its incremental included, so the cursor is read from
    # the row as served. add_map without a position would go before the incremental, which dlt
    # keeps last.
    resource.add_map(as_landed, insert_at=len(resource._pipe))
    resource.apply_hints(write_disposition="append")
    destination = dlt.destinations.filesystem(bucket_url=lake_root().as_uri(), layout=LAYOUT)
    pipeline_name = f"{source.name}__{resource_name}"
    pipeline = dlt.pipeline(pipeline_name=pipeline_name, destination=destination, dataset_name=DATASET)
    pipeline.run(resource, table_name=pipeline_name, loader_file_format="parquet")


def run(sources: list[Source], only: Callable[[Source, str], bool] = lambda source, name: True) -> int:
    """Land every chosen resource of ``sources``; name each failure on stderr; return the exit status."""
    landed = failed = 0
    for source in sources:
        if source.problem:
            failed += 1
            print(f"{source.name} not run: {source.problem}", file=sys.stderr)
            continue
        for name in source.resources:
            if not only(source, name):
                continue
            try:
                land(source, name)
                landed += 1
            except Exception as error:  # one resource's failure must not stop the others
                failed += 1
                print(f"{source.name}__{name} failed: {error}", file=sys.stderr)
    if failed:
        print(f"{failed} failed, {landed} landed", file=sys.stderr)
    if not landed:
        return 2
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="ingest", description=__doc__.splitlines()[0])
    parser.add_argument("name", nargs="?", help="a source, or SOURCE__RESOURCE; every source when left out")
    parser.add_argument("--list", action="store_true", help="print each declared source's name")
    args = parser.parse_args(argv)

    sources = read_sources()
    if args.list:
        for source in sources:
            print(source.name)
        return 0
    if not sources:
        print(f"no source is declared in {SOURCES}/", file=sys.stderr)
        return 2
    if args.name is None:
        return run(sources)

    source_name, _, resource_name = args.name.partition("__")
    chosen = [s for s in sources if s.name == source_name]
    if not chosen:
        print(f"no source named {source_name!r} is declared", file=sys.stderr)
        return 2
    if resource_name:
        if not chosen[0].problem and resource_name not in chosen[0].resources:
            print(f"source {source_name!r} declares no resource {resource_name!r}", file=sys.stderr)
            return 2
        return run(chosen, lambda source, name: name == resource_name)
    return run(chosen)
