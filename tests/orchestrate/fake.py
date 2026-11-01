"""Stand-ins for the Taskfile commands the deployments run, so a test chooses what each one does.

Called as the command a deployment parameter names, with the flow's own last argument after
the test's: the source name for ``ingest``, ``TARGET=<target>`` for ``build``. Each call appends
one JSON line to its log: the argument the flow appended, the whole argv, the working
directory, and when it started and ended.

    fake.py list   <spec.json>                       print spec["stdout"], spec["stderr"]; exit spec["exit"]
    fake.py ingest <table.json> <log> SOURCE         behave as table[SOURCE] says (default exit 0)
    fake.py build  <spec.json> <log> TARGET=...      sleep spec["sleep"], exit spec["exit"]
    fake.py lake   <log> SOURCE                      land the synthetic Products lake under $LAKE_ROOT

A behaviour is an exit status, or ``{"sleep": seconds, "exit": status, "pidfile": path}``; with
``pidfile``, the fake writes its pid there before it sleeps.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def log(path: str, argument: str, started: float) -> None:
    with open(path, "a", encoding="utf-8") as out:
        out.write(
            json.dumps(
                {
                    "argument": argument,
                    "argv": sys.argv[1:],
                    "cwd": os.getcwd(),
                    "start": started,
                    "end": time.time(),
                }
            )
            + "\n"
        )


def behave(behaviour) -> int:
    if isinstance(behaviour, int):
        return behaviour
    if "pidfile" in behaviour:
        Path(behaviour["pidfile"]).write_text(str(os.getpid()))
    time.sleep(behaviour.get("sleep", 0))
    return behaviour.get("exit", 0)


def main(argv: list[str]) -> int:
    started = time.time()
    kind = argv[0]
    if kind == "list":
        spec = json.loads(Path(argv[1]).read_text())
        sys.stdout.write(spec.get("stdout", ""))
        sys.stderr.write(spec.get("stderr", ""))
        return spec.get("exit", 0)
    if kind == "ingest":
        table, path, source = json.loads(Path(argv[1]).read_text()), argv[2], argv[-1]
        status = behave(table.get(source, 0))
        log(path, source, started)
        return status
    if kind == "build":
        spec, path, target = json.loads(Path(argv[1]).read_text()), argv[2], argv[-1]
        status = behave(spec)
        log(path, target, started)
        return status
    if kind == "lake":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from harness import load_id, product, write_load

        path, source = argv[1], argv[-1]
        lake = Path(os.environ.get("LAKE_ROOT", "lake")).resolve()
        rows = [
            product(1, "OR-0001", "Orchestrated One", color="Black"),
            product(2, "OR-0002", "Orchestrated Two", color="Red", line="R "),
            product(3, "OR-0003", "Orchestrated Three", sell_end="2013-05-29"),
        ]
        write_load(lake, load_id(1), rows)
        log(path, source, started)
        return 0
    raise SystemExit(f"fake.py: unknown kind {kind!r}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
