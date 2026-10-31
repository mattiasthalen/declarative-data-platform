"""Land each source resource in the lake, one dlt pipeline per resource (ADR-0001).

Each row lands whole, as the JSON text the feed served, in a column named ``data`` beside
dlt's ``_dlt_load_id`` and ``_dlt_id``, at
``$LAKE_ROOT/<resource>/date=YYYY-MM-DD/hour=HH/<load_id>.<file_id>.parquet``.
A resource that fails is named and the rest still run; the exit status says whether all landed.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from urllib.parse import urljoin

FEED = "https://demodata.grapecity.com/adventureworks/odata/v1"

# Declarative ingest is a later story; until then the resources are declared here.
RESOURCES = {
    "adventure_works__products": f"{FEED}/Products",
}

# dlt writes under <bucket>/<dataset>/<layout>. Its own bookkeeping lands in the dataset folder,
# $LAKE_ROOT/_dlt/; the layout steps out of it so each resource sits directly under $LAKE_ROOT.
DATASET = "_dlt"
LAYOUT = "../{table_name}/date={YYYY}-{MM}-{DD}/hour={HH}/{load_id}.{file_id}.{ext}"

log = logging.getLogger("ingest")

DEFAULT_PORTS = {"http": 80, "https": 443}


def lake_root() -> Path:
    return Path(os.environ.get("LAKE_ROOT", "lake")).resolve()


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


def odata_rows(url: str) -> Iterator[dict]:
    """Every row of an OData feed, following ``@odata.nextLink`` page by page.

    A next link, resolved against the page it came from, is followed only to the feed's own
    origin, and no request follows a redirect: the feed names where the next request goes, and
    it must not be able to send that request elsewhere.
    """
    from dlt.sources.helpers import requests

    home = origin(url)
    while url:
        if origin(url) != home:
            raise ValueError(f"next link {url} leaves the feed's origin {home}")
        response = requests.get(url, allow_redirects=False)
        if response.is_redirect:
            raise ValueError(f"{url} redirects to {response.headers.get('location')}; redirects are not followed")
        response.raise_for_status()
        page = response.json()
        for row in page.get("value", []):
            yield {"data": json.dumps(row)}
        next_link = page.get("@odata.nextLink")
        url = urljoin(url, next_link) if next_link else None


def land(name: str, url: str) -> None:
    """Run the one pipeline that lands ``name`` from ``url`` as one load."""
    import dlt

    lake = lake_root()
    resource = dlt.resource(odata_rows(url), name=name, write_disposition="append")
    destination = dlt.destinations.filesystem(bucket_url=lake.as_uri(), layout=LAYOUT)
    pipeline = dlt.pipeline(pipeline_name=name, destination=destination, dataset_name=DATASET)
    pipeline.run(resource, loader_file_format="parquet")


def run(resources: Mapping[str, str]) -> int:
    """Land every resource; name each that failed and return 1 if any did, else 0."""
    failed = []
    for name, url in resources.items():
        try:
            land(name, url)
        except Exception as error:  # one resource's failure must not stop the others
            failed.append(name)
            log.error("%s failed: %s", name, error)
            print(f"{name} failed: {error}", file=sys.stderr)
    if failed:
        print("failed resources: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return run(RESOURCES)
