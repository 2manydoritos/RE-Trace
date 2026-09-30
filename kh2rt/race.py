"""The .retrace file: one run plus the racer's name, for comparing runs with other players."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

FORMAT = "retrace-run"
VERSION = 1
EXTENSION = ".retrace"
RUN_KEYS = ("started_at", "duration", "status", "seed", "preset", "real_time", "segments", "events")


class RaceFileError(Exception):
    pass


def write_file(path: Path, racer: str, run: dict):
    """run: as returned by Store.export_run (notes are never included)."""
    doc = {"format": FORMAT, "version": VERSION, "racer": racer, "exported_at": time.time(),
           "run": {k: run[k] for k in RUN_KEYS}}
    Path(path).write_text(json.dumps(doc, indent=1), encoding="utf-8")


def read_file(path: Path) -> tuple[str, dict]:
    """(racer, run) from a .retrace file. Raises RaceFileError with a readable reason."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RaceFileError(f"Couldn't read the file ({e.__class__.__name__}).") from e
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise RaceFileError("This isn't an RE:Trace run file.")
    if doc.get("version", 0) > VERSION:
        raise RaceFileError("This file comes from a newer RE:Trace. Update to open it.")
    run = doc.get("run")
    if not isinstance(run, dict) or not isinstance(run.get("segments"), list) or not isinstance(run.get("events"), list):
        raise RaceFileError("The file is missing its route data.")
    run = {"started_at": 0.0, "duration": 0.0, "status": "abandoned", "seed": "", "preset": "", "real_time": 0.0,
           **{k: run[k] for k in RUN_KEYS if k in run}}
    try:   # keep only the fields RE:Trace knows, with the right types
        run["duration"] = float(run["duration"])
        run["real_time"] = float(run["real_time"] or 0)
        run["started_at"] = float(run["started_at"] or 0)
        run["seed"], run["preset"], run["status"] = str(run["seed"] or ""), str(run["preset"] or ""), str(run["status"])
        run["segments"] = [{"world": str(s["world"]), "start": float(s["start"]), "end": float(s["end"]),
                            "level_in": int(s.get("level_in", 0)), "deaths": int(s.get("deaths", 0))}
                           for s in run["segments"]]
        run["events"] = [{"t": float(e["t"]), "kind": str(e["kind"]), "world": str(e.get("world", "")),
                          "name": str(e["name"]), "category": str(e.get("category", ""))} for e in run["events"]]
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise RaceFileError("The route data in this file is damaged.") from e
    return str(doc.get("racer") or "Unknown racer"), run


def suggested_name(racer: str, run: dict) -> str:
    """e.g. Sora_FF4-seed_2026-09-30.retrace"""
    day = time.strftime("%Y-%m-%d", time.localtime(run.get("started_at") or time.time()))
    parts = [racer or "run", run.get("seed") or "", day]
    clean = [re.sub(r"[^\w\-]+", "-", p).strip("-") for p in parts if p]
    return "_".join(p for p in clean if p) + EXTENSION
