"""
Loadless timing, start and end detection, matching the KH2 Randomizer LiveSplit load remover
(github.com/aliosgaming/KH2FM_Load_Remover-FOR-RANDOMIZER):

  start      value at [start_ptr]+0x1AC goes 132 -> 0  (YES on "Start game with these settings?")
  loading    black == 128  or  (load and loadscreen != 3)
  end        btlend becomes 4 in TWTNW room 0x14, event 0x4A  (the instant Final Xemnas dies)
"""
from __future__ import annotations

from dataclasses import dataclass

from . import game_data as gd


@dataclass
class TimingSample:
    start: int
    loading: bool
    world: int
    room: int
    event: int
    btlend: int


def read_timing(game) -> TimingSample | None:
    t = game.version.timing
    if t is None:
        return None
    now = game.read(game.version.now, 9)
    black = game.read(t.black, 1)[0]
    loadscreen = game.read(t.loadscreen, 1)[0]
    load = game.read(t.load, 1)[0] != 0
    # Like LiveSplit's pointer reads: if the pointer is null or can't be followed, the value is 0.
    # That matters: the pointer changes when you press YES, and LiveSplit's start condition
    # (132 -> 0) relies on this behaviour.
    start = 0
    try:
        ptr = int.from_bytes(game.read(t.start_ptr, 8), "little")
        if ptr:
            start = int.from_bytes(game.read_abs(ptr + gd.START_OFFSET, 4), "little")
    except OSError:
        start = 0
    return TimingSample(start, black == 128 or (load and loadscreen != 3),
                        now[0], now[1], now[8], game.read(t.btlend, 1)[0])


def pressed_start(old: TimingSample | None, cur: TimingSample) -> bool:
    return old is not None and old.start == 132 and cur.start == 0


def killed_final_xemnas(old: TimingSample | None, cur: TimingSample) -> bool:
    return (old is not None and old.btlend != 4 and cur.btlend == 4
            and (cur.world, cur.room, cur.event) == gd.FINAL_XEMNAS)


class RunClock:
    """Game time (loads removed) and real time. Like LiveSplit, each interval between samples counts
    toward game time according to whether the game was loading at the start of that interval."""

    def __init__(self):
        self.game_time = 0.0
        self.real_time = 0.0
        self.running = False
        self.paused = False
        self.loading = False
        self._last: float | None = None

    def start(self, now: float, loading: bool = False):
        """loading: the game's state on the start tick, so the very first interval is judged correctly."""
        self.game_time = self.real_time = 0.0
        self.running, self.paused, self.loading, self._last = True, False, loading, now

    def update(self, now: float, loading: bool | None, speed: float = 1.0):
        if self.running and self._last is not None and not self.paused:
            dt = (now - self._last) * speed
            self.real_time += dt
            if not self.loading:
                self.game_time += dt
        self._last = now
        if loading is not None:
            self.loading = loading

    def stop(self):
        self.running = False
