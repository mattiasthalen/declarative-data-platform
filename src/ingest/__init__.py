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
from urllib.parse import urlsplit, urlunsplit

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


def lake_root() -> Path:
    return Path(os.environ.get("LAKE_ROOT", "lake")).resolve()


def odata_rows(url: str) -> Iterator[dict]:
    """Every row of an OData feed, following ``@odata.nextLink`` page by page.

    A next link is followed only to the feed's own scheme and host: the feed names the URL the
    next request goes to, and it must not be able to send that request elsewhere.
    """
    from dlt.sources.helpers import requests

    origin = urlsplit(url)[:2]
    while url:
        if urlsplit(url)[:2] != origin:
            raise ValueError(f"next link {url} leaves the feed at {urlunsplit(origin + ('', '', ''))}")
        response = requests.get(url)
        response.raise_for_status()
        page = response.json()
        for row in page.get("value", []):
            yield {"data": json.dumps(row)}
        url = page.get("@odata.nextLink")


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
