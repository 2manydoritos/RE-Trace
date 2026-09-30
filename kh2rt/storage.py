"""SQLite history of runs + notes, and the practice statistics computed from it."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from .tracker import Event, Run, Segment, milestone_splits, world_breakdown


def run_from_dict(d: dict) -> Run:
    return Run([Segment(**s) for s in d["segments"]], [Event(**e) for e in d["events"]],
               real_time=d.get("real_time", 0.0))


def default_db_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home()))
    root, old = base / "RE-Trace", base / "KH2RouteTracker"
    if old.exists() and not root.exists():
        old.rename(root)  # keep history from before the rename
    root.mkdir(parents=True, exist_ok=True)
    return root / "runs.db"


SCHEMA = """
create table if not exists runs(
  id integer primary key, started_at real, duration real, status text,
  seed text default '', notes text default '', data text, preset_id integer);
create table if not exists presets(id integer primary key, name text unique collate nocase);
create table if not exists races(id integer primary key, name text, created_at real);
create table if not exists race_entries(id integer primary key, race_id integer, racer text, source text,
  data text, position integer);
create table if not exists world_notes(world text primary key, text text);
create table if not exists settings(key text primary key, value text);
"""


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("pragma table_info(runs)")}
        if "preset_id" not in cols:   # databases from before presets existed
            self.db.execute("alter table runs add column preset_id integer")
        # runs left 'live' by a crash are kept but marked
        self.db.execute("update runs set status='abandoned' where status='live'")
        self.db.commit()

    # ---- runs
    def create_run(self, seed: str, preset_id: int | None = None) -> int:
        cur = self.db.execute("insert into runs(started_at,duration,status,seed,data,preset_id) values(?,?,?,?,?,?)",
                              (time.time(), 0, "live", seed, json.dumps({"segments": [], "events": []}), preset_id))
        self.db.commit()
        return cur.lastrowid

    def save_run(self, run_id: int, run: Run, duration: float, status: str, seed: str | None = None):
        data = json.dumps({"segments": [s.__dict__ for s in run.segments],
                           "events": [e.__dict__ for e in run.events],
                           "real_time": run.real_time})
        if seed is None:
            self.db.execute("update runs set duration=?,status=?,data=? where id=?", (duration, status, data, run_id))
        else:
            self.db.execute("update runs set duration=?,status=?,data=?,seed=? where id=?",
                            (duration, status, data, seed, run_id))
        self.db.commit()

    def set_run_field(self, run_id: int, field: str, value: str):
        assert field in ("notes", "seed", "status")
        self.db.execute(f"update runs set {field}=? where id=?", (value, run_id))
        self.db.commit()

    def set_run_preset(self, run_id: int, preset_id: int | None):
        self.db.execute("update runs set preset_id=? where id=?", (preset_id, run_id))
        self.db.commit()

    def delete_run(self, run_id: int):
        self.db.execute("delete from runs where id=?", (run_id,))
        self.db.commit()

    def list_runs(self, preset: int | None = None) -> list[dict]:
        """preset: None for every run, else only that preset's runs."""
        where, args = "status!='live'", ()
        if preset is not None:
            where, args = where + " and runs.preset_id=?", (preset,)
        rows = self.db.execute(
            "select runs.id,started_at,duration,status,seed,notes,preset_id,presets.name from runs "
            f"left join presets on presets.id=runs.preset_id where {where} order by started_at desc", args)
        return [dict(zip(("id", "started_at", "duration", "status", "seed", "notes", "preset_id", "preset"), r))
                for r in rows]

    def load_run(self, run_id: int) -> Run:
        (data,) = self.db.execute("select data from runs where id=?", (run_id,)).fetchone()
        return run_from_dict(json.loads(data))

    def export_run(self, run_id: int) -> dict:
        """A saved run as plain data for a .retrace file or a race. Run notes stay private."""
        started, duration, status, seed, preset, data = self.db.execute(
            "select started_at,duration,status,seed,presets.name,data from runs "
            "left join presets on presets.id=runs.preset_id where runs.id=?", (run_id,)).fetchone()
        d = json.loads(data)
        return {"started_at": started, "duration": duration, "status": status, "seed": seed or "",
                "preset": preset or "", "real_time": d.get("real_time", 0.0),
                "segments": d["segments"], "events": d["events"]}

    # ---- presets
    def list_presets(self) -> list[dict]:
        rows = self.db.execute("select id,name from presets order by name collate nocase")
        return [{"id": i, "name": n} for i, n in rows]

    def preset_name(self, preset_id: int | None) -> str:
        r = self.db.execute("select name from presets where id=?", (preset_id,)).fetchone()
        return r[0] if r else ""

    def create_preset(self, name: str) -> int:
        """Returns the existing preset's id if one already has this name (ignoring case)."""
        name = name.strip()
        r = self.db.execute("select id from presets where name=?", (name,)).fetchone()
        if r:
            return r[0]
        cur = self.db.execute("insert into presets(name) values(?)", (name,))
        self.db.commit()
        return cur.lastrowid

    def rename_preset(self, preset_id: int, name: str) -> bool:
        """False if another preset already has this name."""
        try:
            self.db.execute("update presets set name=? where id=?", (name.strip(), preset_id))
        except sqlite3.IntegrityError:
            return False
        self.db.commit()
        return True

    def delete_preset(self, preset_id: int):
        """Its runs are kept and simply lose the preset."""
        self.db.execute("update runs set preset_id=null where preset_id=?", (preset_id,))
        self.db.execute("delete from presets where id=?", (preset_id,))
        self.db.commit()

    def preset_run_counts(self) -> dict[int, int]:
        rows = self.db.execute("select preset_id,count(*) from runs where preset_id is not null "
                               "and status!='live' group by preset_id")
        return dict(rows.fetchall())

    # ---- races (each entry keeps its own copy of the run, so races survive history edits)
    def list_races(self) -> list[dict]:
        rows = self.db.execute("select races.id,name,created_at,count(race_entries.id) from races "
                               "left join race_entries on race_entries.race_id=races.id "
                               "group by races.id order by created_at desc")
        return [{"id": i, "name": n, "created_at": c, "racers": k} for i, n, c, k in rows]

    def create_race(self, name: str) -> int:
        cur = self.db.execute("insert into races(name,created_at) values(?,?)", (name.strip(), time.time()))
        self.db.commit()
        return cur.lastrowid

    def rename_race(self, race_id: int, name: str):
        self.db.execute("update races set name=? where id=?", (name.strip(), race_id))
        self.db.commit()

    def delete_race(self, race_id: int):
        self.db.execute("delete from race_entries where race_id=?", (race_id,))
        self.db.execute("delete from races where id=?", (race_id,))
        self.db.commit()

    def race_entries(self, race_id: int) -> list[dict]:
        rows = self.db.execute("select id,racer,source,data from race_entries where race_id=? order by position,id",
                               (race_id,))
        return [{"id": i, "racer": r, "source": src, "run": json.loads(d)} for i, r, src, d in rows]

    def add_race_entry(self, race_id: int, racer: str, run: dict, source: str) -> int | None:
        """None if this exact run (same racer, start and time) is already in the race."""
        for e in self.race_entries(race_id):
            if e["racer"] == racer and e["run"].get("started_at") == run.get("started_at")                     and e["run"].get("duration") == run.get("duration"):
                return None
        (pos,) = self.db.execute("select coalesce(max(position),0)+1 from race_entries where race_id=?",
                                 (race_id,)).fetchone()
        cur = self.db.execute("insert into race_entries(race_id,racer,source,data,position) values(?,?,?,?,?)",
                              (race_id, racer, source, json.dumps(run), pos))
        self.db.commit()
        return cur.lastrowid

    def rename_racer(self, entry_id: int, racer: str):
        self.db.execute("update race_entries set racer=? where id=?", (racer.strip(), entry_id))
        self.db.commit()

    def remove_race_entry(self, entry_id: int):
        self.db.execute("delete from race_entries where id=?", (entry_id,))
        self.db.commit()

    # ---- notes
    def world_note(self, world: str) -> str:
        r = self.db.execute("select text from world_notes where world=?", (world,)).fetchone()
        return r[0] if r else ""

    def set_world_note(self, world: str, text: str):
        self.db.execute("insert into world_notes(world,text) values(?,?) "
                        "on conflict(world) do update set text=excluded.text", (world, text))
        self.db.commit()

    def setting(self, key: str, default: str = "") -> str:
        r = self.db.execute("select value from settings where key=?", (key,)).fetchone()
        return r[0] if r else default

    def set_setting(self, key: str, value: str):
        self.db.execute("insert into settings(key,value) values(?,?) "
                        "on conflict(key) do update set value=excluded.value", (key, value))
        self.db.commit()

    # ---- stats
    def stats(self, finished_only: bool, preset: int | None = None) -> dict:
        """preset: as in list_runs (None compares every run)."""
        runs = [r for r in self.list_runs(preset) if r["status"] == "finished" or
                (not finished_only and r["status"] in ("finished", "abandoned"))]
        per_world: dict[str, dict] = {}
        milestones: dict[tuple[str, str], list[float]] = {}
        durations = []
        for r in runs:
            run = self.load_run(r["id"])
            if r["status"] == "finished":
                durations.append(r["duration"])
            for w, b in world_breakdown(run).items():
                d = per_world.setdefault(w, {"times": [], "visits": [], "deaths": [], "checks": []})
                d["times"].append(b["time"])
                d["visits"].append(b["visits"])
                d["deaths"].append(b["deaths"])
                d["checks"].append(b["checks"])
            for w, name, t in milestone_splits(run):
                milestones.setdefault((w, name), []).append(t)

        def avg(xs):
            return sum(xs) / len(xs) if xs else 0

        worlds = {w: {"runs": len(d["times"]), "avg": avg(d["times"]), "best": min(d["times"]),
                      "worst": max(d["times"]), "visits": avg(d["visits"]), "deaths": avg(d["deaths"]),
                      "checks": avg(d["checks"])} for w, d in per_world.items()}
        ms = [{"world": w, "name": n, "count": len(ts), "avg": avg(ts), "best": min(ts)}
              for (w, n), ts in milestones.items()]
        ms.sort(key=lambda m: m["avg"])
        return {"runs": len(runs), "finished": len(durations), "avg_duration": avg(durations),
                "best_duration": min(durations) if durations else 0, "worlds": worlds, "milestones": ms}

    def world_averages(self, preset: int | None = None) -> dict[str, float]:
        return {w: d["avg"] for w, d in self.stats(finished_only=False, preset=preset)["worlds"].items()}
