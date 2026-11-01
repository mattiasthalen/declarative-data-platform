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
    config: dict = field(default_factory=dict)
    resources: dict[str, dict] = field(default_factory=dict)
    problem: str | None = None


def read_sources(root: Path = SOURCES) -> list[Source]:
    """Every source folder under ``root``, sorted, each read and checked; a bad one carries its
    problem and no resources. A folder whose name starts with ``.`` or ``_`` is not a source."""
    if not root.is_dir():
        return []
    sources = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and p.name[0] not in "._"):
        try:
            sources.append(read_source(folder))
        except Refused as error:
            sources.append(Source(folder.name, problem=str(error)))
    return sources


def read_source(folder: Path) -> Source:
    if not NAME.fullmatch(folder.name):
        raise Refused(f"{folder}: a source's name must be snake_case, with no double underscore")
    source_file = folder / SOURCE_FILE
    resource_files = [p for p in sorted(folder.glob("*.yaml")) if p.name != SOURCE_FILE]
    if not source_file.is_file():
        raise Refused(f"{source_file} is missing")
    if not resource_files:
        raise Refused(f"{source_file} has no resource file beside it")

    declared = load_yaml(source_file)
    if not isinstance(declared, dict) or len(declared) != 1:
        raise Refused(f"{source_file} must hold exactly one dlt source kind, such as {KIND}:")
    [(kind, config)] = declared.items()
    if kind != KIND:
        raise Refused(f"{source_file}: unknown dlt source kind {kind!r}; known: {KIND}")
    if not isinstance(config, dict):
        raise Refused(f"{source_file}: {kind} must hold a mapping")
    if "resources" in config:
        raise Refused(f"{source_file}: resources are declared one per file beside it, not here")
    check(source_file, config, {"name": "_check", "endpoint": {"path": ""}})

    source = Source(folder.name, config)
    defaults = config.get("resource_defaults") or {}
    for path in resource_files:
        name = path.stem
        if not NAME.fullmatch(name):
            raise Refused(f"{path}: a resource's file name must be snake_case, with no double underscore")
        entry = load_yaml(path)
        if not isinstance(entry, dict):
            raise Refused(f"{path} must hold a mapping")
        if entry.get("name", name) != name:
            raise Refused(f"{path}: name {entry['name']!r} differs from the file name {name!r}")
        disposition = {**defaults, **entry}.get("write_disposition", "append")
        if isinstance(disposition, dict):
            disposition = disposition.get("disposition")
        if disposition != "append":
            where = path if "write_disposition" in entry else source_file
            raise Refused(f"{where}: write_disposition {disposition!r} refused; every load is appended")
        entry = {**entry, "name": name}
        check(path, config, entry)
        source.resources[name] = entry
    return source


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise Refused(f"{path} is not valid YAML: {error}") from None


def check(path: Path, config: dict, entry: dict) -> None:
    """Refuse, naming ``path``, a declaration dlt would not build."""
    for headers in declared_headers(config, entry):
        for header, value in headers.items():
            # dlt accepts any value here; requests refuses a non-text one only when it sends it,
            # and its message quotes the value.
            if not isinstance(value, str):
                raise Refused(f"{path}: header {header!r} must be text; quote it")
    try:
        build(config, entry)
    except Exception as error:
        raise Refused(f"{path}: {without_values(error)}") from None


def declared_headers(config: dict, entry: dict) -> list[dict]:
    def headers(mapping: Any, *keys: str) -> Any:
        for key in keys:
            mapping = mapping.get(key) if isinstance(mapping, dict) else None
        return mapping

    found = [headers(config, "client", "headers"), headers(config, "resource_defaults", "endpoint", "headers"),
             headers(entry, "endpoint", "headers")]
    return [h for h in found if isinstance(h, dict)]


def without_values(error: Exception) -> str:
    """Where dlt's validation failed, without the value it failed on: dlt quotes values whole,
    which would print a declared header or key, a token included, to the pod's log."""
    from dlt.common.exceptions import DictValidationException

    if not isinstance(error, DictValidationException):
        return str(error)

    def leaves(e: DictValidationException):
        if not e.nested_exceptions:
            yield e
        for nested in e.nested_exceptions or []:
            yield from leaves(nested)

    deepest = max(leaves(error), key=lambda e: e.path.count("/"))
    if deepest.field is None:  # dlt names the unexpected keys, never their values
        return str(deepest)
    return f"Path `{deepest.path}`: field `{deepest.field}` is not valid"


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


def spelled(where: tuple[str, str, int | None]) -> str:
    scheme, host, port = where
    return f"{scheme}://{host}:{port}"


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
        # The messages name origins only: a URL can carry a declared api key by now.
        if origin(request.url) != home:
            raise ValueError(f"a request to {spelled(origin(request.url))} leaves the feed's origin {spelled(home)}")
        kwargs["allow_redirects"] = False
        response = retrying_send(request, **kwargs)
        if response.is_redirect:
            raise ValueError(f"{spelled(home)} answered with a redirect; redirects are not followed")
        return response

    session.send = send
    return session


KIND = "rest_api"


def build(config: dict, entry: dict):
    """The one dlt resource ``entry`` declares under ``config``, dlt's RESTAPIConfig less
    ``resources``; nothing is requested until it is iterated. A resource that names a parent
    resource cannot be built alone, so is refused."""
    from dlt.sources.rest_api import rest_api_resources
    from dlt.sources.rest_api.config_setup import PAGINATOR_MAP, register_paginator

    if "odata" not in PAGINATOR_MAP:
        register_paginator("odata", odata_paginator())
    client = config.get("client") or {}
    if not isinstance(client, dict) or not isinstance(client.get("base_url"), str):
        raise ValueError("client.base_url is required")
    client = {**client, "session": guarded_session(client["base_url"])}
    [resource] = rest_api_resources({**config, "client": client, "resources": [entry]})
    return resource


# --------------------------------------------------------------------------- landing


def as_landed(row: dict) -> dict:
    return {"data": json.dumps(row)}


def land(source: Source, resource_name: str) -> None:
    """Run the one pipeline that lands ``resource_name`` of ``source`` as one load."""
    import dlt

    resource = build(source.config, source.resources[resource_name])
    # Placed after every step dlt put there, its incremental included, so the cursor is read from
    # the row as served. add_map without a position would go before the incremental, which dlt
    # keeps last.
    resource.add_map(as_landed, insert_at=len(resource._pipe))
    resource.apply_hints(write_disposition="append")
    destination = dlt.destinations.filesystem(bucket_url=lake_root().as_uri(), layout=LAYOUT)
    pipeline_name = f"{source.name}__{resource_name}"
    pipeline = dlt.pipeline(pipeline_name=pipeline_name, destination=destination, dataset_name=DATASET)
    # The lake holds the cursor (ADR-0016). Local state left by an earlier run would win over a
    # lake that lost its own, so the pipeline starts from what the lake holds. A package an
    # interrupted run left half loaded is kept: run() finishes it first, rewriting the files it
    # already wrote, where dropping it would leave them to be landed again under a new load id.
    if not pipeline.has_pending_data:
        pipeline = pipeline.drop()
    pipeline.run(resource, table_name=pipeline_name, loader_file_format="parquet")


def without_queries(message: str) -> str:
    """``message`` with each URL's query cut: dlt and requests quote the URL they failed on, and
    its query can carry a declared api key."""
    return re.sub(r"(https?://[^\s?'\"]*)\?[^\s'\"]*", r"\1?…", message)


def run(sources: list[Source], resource: str | None = None) -> int:
    """Land every resource of ``sources``, or only the one named ``resource``; name each failure on
    stderr; return the exit status."""
    landed = failed = 0
    for source in sources:
        if source.problem:
            failed += 1
            print(f"{source.name} not run: {source.problem}", file=sys.stderr)
            continue
        for name in source.resources:
            if resource is not None and name != resource:
                continue
            try:
                land(source, name)
                landed += 1
            except Exception as error:  # one resource's failure must not stop the others
                failed += 1
                print(f"{source.name}__{name} failed: {without_queries(str(error))}", file=sys.stderr)
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

    source_name, separator, resource_name = args.name.partition("__")
    chosen = [s for s in sources if s.name == source_name]
    if not chosen:
        print(f"no source named {source_name!r} is declared", file=sys.stderr)
        return 2
    if not separator:
        return run(chosen)
    if not chosen[0].problem and resource_name not in chosen[0].resources:
        print(f"source {source_name!r} declares no resource {resource_name!r}", file=sys.stderr)
        return 2
    return run(chosen, resource_name)
