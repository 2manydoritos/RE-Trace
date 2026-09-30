"""
Turns raw memory snapshots into a run: world visits in order, checks, boss kills, deaths.
Pure Python (no Qt, no Windows) so it can be tested with a fake game.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import game_data as gd


@dataclass
class Snapshot:
    world: str | None
    world_id: int
    room_id: int
    level: int
    dead: bool
    items: dict[str, int]          # key -> count/level
    milestones: frozenset[int]     # indices into gd.MILESTONES


def read_snapshot(read, version: gd.GameVersion) -> Snapshot:
    """read(offset, size) -> bytes, offsets relative to module base."""
    now = read(version.now, 10)
    world_id, room_id = now[0], now[1]
    event_id = int.from_bytes(now[8:10], "little")
    save = read(version.save + gd.SAVE_READ_START, gd.SAVE_READ_END - gd.SAVE_READ_START)

    def sb(off):
        return save[off - gd.SAVE_READ_START]

    in_stt = sb(gd.STT_FLAG_OFFSET) == 13
    world = gd.resolve_world(world_id, room_id, event_id, in_stt)

    items: dict[str, int] = {}
    for it in gd.ITEMS:
        v = sb(it.offset)
        items[it.key] = (1 if v & it.mask else 0) if it.mask else v
    for key, _name, off, base in gd.GROWTH:
        raw = (sb(off) | (sb(off + 1) << 8)) & 0x0FFF
        items[key] = max(0, raw - base)
    for key, _name, off in gd.DRIVE_LEVELS:
        v = sb(off)
        items[key] = v if v <= 7 else 0
    abil = save[gd.ABILITY_LIST_OFFSET - gd.SAVE_READ_START:
                gd.ABILITY_LIST_OFFSET - gd.SAVE_READ_START + gd.ABILITY_LIST_LEN]
    for aid, (key, _n) in gd.ABILITY_IDS.items():
        items[key] = 1 if aid in abil[0::2] else 0

    ms = frozenset(i for i, m in enumerate(gd.MILESTONES) if sb(m["offset"]) & m["mask"])
    pause = read(version.ability_to_pause, 1)[0]
    return Snapshot(world, world_id, room_id, sb(gd.SORA_LEVEL_OFFSET), pause in (4, 5), items, ms)


ITEM_NAMES = {i.key: i.name for i in gd.ITEMS}
ITEM_NAMES.update({k: n for k, n, *_ in gd.GROWTH})
ITEM_NAMES.update({k: n for k, n in gd.ABILITY_IDS.values()})
ITEM_NAMES.update({k: n for k, n, _ in gd.DRIVE_LEVELS})
GROWTH_KEYS = {k for k, *_ in gd.GROWTH}
DRIVE_KEYS = {k for k, *_ in gd.DRIVE_LEVELS}
MAGIC_KEYS = {i.key for i in gd.ITEMS if i.category == "Magic"}


@dataclass
class Event:
    t: float            # seconds into run
    kind: str           # check | milestone | drive | death | level
    world: str
    name: str
    category: str = ""


@dataclass
class Segment:
    world: str
    start: float
    end: float
    level_in: int = 0
    deaths: int = 0


@dataclass
class Run:
    segments: list[Segment] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    finished: bool = False
    real_time: float = 0.0     # RTA, alongside the loadless duration


class RunRecorder:
    """
    Feed it snapshots with tick(). Values must be stable for STABLE ticks before
    they're accepted, which filters out junk reads during loads.
    """
    STABLE = 2

    def __init__(self, baseline: Snapshot, t0: float):
        self.run = Run()
        self.best = dict(baseline.items)          # max seen per item
        self.ms_seen = set(baseline.milestones)
        self.level = baseline.level
        self.was_dead = baseline.dead
        self._pending_world: tuple[str, float, int] | None = None
        self._pending_items: dict[str, tuple[int, int]] = {}
        self._pending_ms: dict[int, int] = {}
        self.t = t0
        self.t0 = t0
        self.awaiting_baseline = baseline.world is None
        if baseline.world:
            self.run.segments.append(Segment(baseline.world, t0, t0, baseline.level))

    @property
    def current(self) -> Segment | None:
        return self.run.segments[-1] if self.run.segments else None

    def rebaseline(self, s: Snapshot):
        """Run started on the title screen: the new save is only in memory once you reach a world.
        Its starting inventory becomes the baseline, and time since YES goes to that first world."""
        self.best = dict(s.items)
        self.ms_seen = set(s.milestones)
        self.level = s.level
        self.was_dead = s.dead
        self.run.segments.append(Segment(s.world, self.t0, self.t, s.level))
        self.awaiting_baseline = False

    def add_final(self, t: float):
        if not any(e.kind == "milestone" and e.name == gd.FINAL_MILESTONE for e in self.run.events):
            world = self.current.world if self.current else "The World That Never Was"
            self.run.events.append(Event(t, "milestone", world, gd.FINAL_MILESTONE))
        if self.current:
            self.current.end = t

    def tick(self, s: Snapshot, t: float) -> list[Event]:
        self.t = t
        new: list[Event] = []
        if self.awaiting_baseline:
            if s.world:
                self.rebaseline(s)
            return new
        if self.current:
            self.current.end = t

        # --- world changes
        if s.world and (not self.current or s.world != self.current.world):
            pw = self._pending_world
            if pw and pw[0] == s.world:
                self._pending_world = (pw[0], pw[1], pw[2] + 1)
            else:
                self._pending_world = (s.world, t, 1)
            if self._pending_world[2] >= self.STABLE:
                w, since, _ = self._pending_world
                if self.current:
                    self.current.end = since
                self.run.segments.append(Segment(w, since, t, s.level))
                self._pending_world = None
        else:
            self._pending_world = None

        world = self.current.world if self.current else (s.world or "Unknown")

        # --- items
        for key, val in s.items.items():
            if val > self.best.get(key, 0):
                pv, n = self._pending_items.get(key, (val, 0))
                n = n + 1 if pv == val else 1
                if n >= self.STABLE:
                    for lvl in range(self.best.get(key, 0) + 1, val + 1):
                        name = ITEM_NAMES[key]
                        if key in DRIVE_KEYS:
                            if lvl >= 2:  # level 1 = just obtained the form
                                new.append(Event(t, "drive", world, f"{name} Lv {lvl}", "Drive Level"))
                            continue
                        if key in GROWTH_KEYS or key in MAGIC_KEYS:
                            name = f"{name} {lvl}" if key in GROWTH_KEYS else f"{name} ({lvl})"
                        new.append(Event(t, "check", world, name, gd.CATEGORY_OF[key]))
                    self.best[key] = val
                    self._pending_items.pop(key, None)
                else:
                    self._pending_items[key] = (val, n)
            else:
                self._pending_items.pop(key, None)

        # --- milestones
        for i in s.milestones - self.ms_seen:
            n = self._pending_ms.get(i, 0) + 1
            if n >= self.STABLE:
                m = gd.MILESTONES[i]
                new.append(Event(t, "milestone", m["world"], m["name"]))
                self.ms_seen.add(i)
                self._pending_ms.pop(i, None)
                if m["name"] == gd.FINAL_MILESTONE:
                    self.run.finished = True
            else:
                self._pending_ms[i] = n
        for i in list(self._pending_ms):
            if i not in s.milestones:
                del self._pending_ms[i]

        # --- deaths / levels
        if s.dead and not self.was_dead:
            new.append(Event(t, "death", world, "Death"))
            if self.current:
                self.current.deaths += 1
        self.was_dead = s.dead
        if 1 <= s.level <= 99 and s.level > self.level:
            new.append(Event(t, "level", world, f"Level {s.level}"))
            self.level = s.level

        self.run.events.extend(new)
        return new


NOT_CHECKS = {"Keyblade", "Growth"}


def is_check(e) -> bool:
    """Counts toward check totals. Keyblades and growth abilities are listed but never counted."""
    return e.kind == "check" and e.category not in NOT_CHECKS


def world_totals(segments: list[Segment]) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in segments:
        out[s.world] = out.get(s.world, 0) + (s.end - s.start)
    return out


def world_breakdown(run: Run) -> dict[str, dict]:
    """One run's time, visits, deaths and checks per world."""
    out = {w: {"time": secs, "visits": 0, "deaths": 0, "checks": 0} for w, secs in world_totals(run.segments).items()}
    for s in run.segments:
        out[s.world]["visits"] += 1
        out[s.world]["deaths"] += s.deaths
    for e in run.events:
        if is_check(e) and e.world in out:
            out[e.world]["checks"] += 1
    return out


def milestone_splits(run: Run) -> list[tuple[str, str, float]]:
    """(world, name, time) for every milestone and drive level-up, in the order they happened."""
    out = []
    for e in run.events:
        if e.kind == "milestone":
            out.append((e.world, e.name, e.t))
        elif e.kind == "drive":
            out.append(("Drive Forms", e.name, e.t))
    return out


def fmt(sec: float, always_hours=False) -> str:
    sec = max(0, int(sec))   # truncate like LiveSplit / speedrun timers (never round up)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02}:{s:02}" if h or always_hours else f"{m}:{s:02}"
