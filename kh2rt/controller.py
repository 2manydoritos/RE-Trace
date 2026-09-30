"""Glue between the game, the recorder and storage. Emits Qt signals for the UI."""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from . import game_data as gd
from .storage import Store
from .timing import RunClock, TimingSample, killed_final_xemnas, pressed_start, read_timing
from .tracker import Event, RunRecorder, Snapshot, read_snapshot

FAST_MS = 16              # timing loop (~60 Hz, like LiveSplit)
TRACK_EVERY = 6           # route tracking every 6th tick (~10 Hz)
POLL_MS = FAST_MS * TRACK_EVERY
FRESH_TICKS = 10          # new-game state must hold for 1 second
FRESH_MAX_FLAGS = 3       # tolerate a few story flags the rando mod may preset


# Story flags that don't count as "progress" when spotting a new game: the rando mod may
# pre-complete Simulated Twilight Town when it drops you straight into the GoA.
_IGNORED_FOR_FRESH = frozenset(i for i, m in enumerate(gd.MILESTONES) if m["world"] == "Simulated Twilight Town")


def is_fresh_save(s) -> bool:
    """Looks like the start of a brand-new seed: GoA (or the Twilight Town opening) at level 1."""
    in_start_area = s.world == "Garden of Assemblage" or s.world_id == 0x02
    progress = len(s.milestones - _IGNORED_FOR_FRESH)
    return in_start_area and s.level <= 1 and progress <= FRESH_MAX_FLAGS


class Controller(QObject):
    status_changed = Signal(str, bool)       # text, connected
    run_changed = Signal()                   # run started / finished / structure changed
    events_added = Signal(list)
    ticked = Signal(float)                   # run clock
    history_changed = Signal()               # a saved run was deleted/edited
    filters_changed = Signal()               # e.g. keyblade tracking toggled
    note_changed = Signal(str, object)       # world, editor that saved it
    presets_changed = Signal()               # a preset was added, renamed or deleted
    preset_selected = Signal()               # the preset for the next / current run changed
    username_changed = Signal()              # your racer name, saved into exported runs

    def __init__(self, store: Store, demo=False, demo_speed=40.0):
        super().__init__()
        self.store = store
        self.demo = demo
        self.speed = demo_speed if demo else 1.0
        self.game = None
        self.recorder: RunRecorder | None = None
        self.run_id: int | None = None
        self.seed = ""
        saved = store.setting("preset_id", "")
        self.preset_id: int | None = int(saved) if saved.isdigit() and store.preset_name(int(saved)) else None
        self.paused = False
        self.auto_start = store.setting("auto_start", "1") == "1"
        self.track_keyblades = store.setting("track_keyblades", "1") == "1"
        self.last_snapshot: Snapshot | None = None
        self.world_avgs = store.world_averages(self.preset_id)
        self.clk = RunClock()
        self.last_timing: TimingSample | None = None
        self._tick = 0
        self._last_real = time.monotonic()
        self._last_save = 0.0
        self._segcount = 0
        self._fresh_n = 0
        self._armed = True   # re-armed once we see a non-fresh state

        self.history_changed.connect(self.on_history_changed)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._poll)
        self.timer.start(FAST_MS)
        self._attach_wait = 0

    # ---- clock
    @property
    def loadless(self) -> bool:
        """True when this game version supports load removal."""
        return self.game is not None and self.game.version.timing is not None

    def clock(self) -> float:
        """The run time shown and saved: game time (loads removed) when supported, else real time."""
        return self.clk.game_time

    # ---- attach
    def _try_attach(self):
        if self.demo:
            from .demo import FakeGame
            self.game = FakeGame()
            self.status_changed.emit("Demo game running", True)
            return
        from .memory import GameNotFound, GameProcess, UnsupportedVersion
        try:
            self.game = GameProcess()
            mode = "" if self.game.version.timing else " · real time"
            self.status_changed.emit(f"Connected · {self.game.version.name}{mode}", True)
        except (GameNotFound, UnsupportedVersion) as e:
            self.status_changed.emit(str(e), False)

    def _detach(self, why: str):
        if self.game:
            self.game.close()
        self.game = None
        self.status_changed.emit(why, False)

    # ---- polling
    def _poll(self):
        now_real = time.monotonic()
        dt_real, self._last_real = now_real - self._last_real, now_real
        if self.game is None:
            self._attach_wait -= FAST_MS
            if self._attach_wait <= 0:
                self._attach_wait = 2000
                self._try_attach()
            return
        if self.demo:
            self.game.advance(dt_real * self.speed)
        try:
            if not self.game.alive():
                raise OSError
            timing = read_timing(self.game)
        except OSError:
            self._detach("Game closed. Waiting for KH2…")
            return

        # --- timing, every tick
        prev, self.last_timing = self.last_timing, timing
        if timing and (prev is None or prev.start != timing.start):
            self._log_start(prev.start if prev else None, timing.start)
        self.clk.update(now_real, timing.loading if timing else False, self.speed)
        if timing:
            if self.recorder is None and self.auto_start and pressed_start(prev, timing):
                self.start_run(from_title=True)
            if self.recorder is not None and not self.paused and killed_final_xemnas(prev, timing):
                self.clk.stop()                       # freeze the time on the exact tick Xemnas dies
                self.recorder.add_final(self.clock())
                self.finish_run()
                return

        # --- route tracking, every few ticks
        self._tick += 1
        if self._tick % TRACK_EVERY:
            return
        try:
            snap = read_snapshot(self.game.read, self.game.version)
        except OSError:
            self._detach("Game closed. Waiting for KH2…")
            return
        self.last_snapshot = snap
        if timing is None:
            self._check_new_game(snap)   # versions without the start signal: fall back to fresh-save detection
        if self.recorder is None or self.paused:
            return
        t = self.clock()
        new = self.recorder.tick(snap, t)
        if len(self.recorder.run.segments) != self._segcount:
            self._segcount = len(self.recorder.run.segments)
            self.run_changed.emit()
        if new:
            self.events_added.emit(new)
        self.ticked.emit(t)
        if self.recorder.run.finished and timing is None:
            self.finish_run()   # no exact end signal: finish when the Final Xemnas flag appears
        elif t - self._last_save > 5:
            self._last_save = t
            self.recorder.run.real_time = self.clk.real_time
            self.store.save_run(self.run_id, self.recorder.run, t, "live")

    def _check_new_game(self, snap):
        if is_fresh_save(snap):
            self._fresh_n += 1
        else:
            self._fresh_n = 0
            self._armed = True
        if not (self.auto_start and self._armed and self._fresh_n >= FRESH_TICKS):
            return
        if self.recorder is not None:
            return   # never interrupt a run in progress
        self._armed = False
        self.start_run()

    def _log_start(self, old, new):
        """Keeps the last few start-value changes (shown in the header tooltip and saved to timing.log)."""
        stamp = time.strftime("%H:%M:%S")
        line = f"{stamp}  start {old} -> {new}" + ("   << auto-start trigger" if old == 132 and new == 0 else "")
        self.start_log = (getattr(self, "start_log", []) + [line])[-6:]
        try:
            from .storage import default_db_path
            with open(default_db_path().with_name("timing.log"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def diagnostics(self) -> str:
        s = self.last_snapshot
        if not s:
            return "No game data yet"
        tm = self.last_timing
        timing = (f"\nStart value {tm.start}  |  loading: {'yes' if tm.loading else 'no'}  |  battle end {tm.btlend}"
                  f"\nAuto-start: {'on' if self.auto_start else 'OFF'}"
                  f"{'  (waiting: a run is already in progress)' if self.recorder else ''}"
                  + ("\nRecent start values:\n  " + "\n  ".join(getattr(self, 'start_log', [])) if getattr(self, 'start_log', None) else "")
                  if tm else "\nLoadless timing not available for this version")
        return timing.lstrip("\n") + "\n" + (f"World 0x{s.world_id:02X}  Room 0x{s.room_id:02X}  ({s.world or 'none'})\n"
                f"Sora level {s.level}  |  story flags set: {len(s.milestones)}\n"
                f"Looks like a new game: {'yes' if is_fresh_save(s) else 'no'}"
                f"\nProgress flags (excluding STT): {len(s.milestones - _IGNORED_FOR_FRESH)}")

    # ---- run control
    def can_start(self) -> bool:
        return self.game is not None and self.recorder is None and \
            (self.last_snapshot is not None or self.last_timing is not None)

    def start_run(self, from_title: bool = False):
        """from_title: started by YES on the new-game screen, before the new save is in memory."""
        if not self.can_start():
            return
        self.clk.start(time.monotonic(), bool(self.last_timing and self.last_timing.loading))
        self.paused = False
        self.world_avgs = self.store.world_averages(self.preset_id)
        base = self.last_snapshot
        if from_title or base is None:
            base = Snapshot(None, 0, 0, 0, False, {}, frozenset())
        self.recorder = RunRecorder(base, 0.0)
        self._segcount = len(self.recorder.run.segments)
        self.run_id = self.store.create_run(self.seed, self.preset_id)
        self._armed = False
        self._last_save = 0.0
        self.run_changed.emit()

    def toggle_pause(self):
        if not self.recorder:
            return
        self.paused = not self.paused
        self.clk.paused = self.paused
        self.run_changed.emit()

    def _end(self, status: str):
        if not self.recorder:
            return
        self.clk.update(time.monotonic(), None, self.speed)
        t = self.clock()
        if self.recorder.current:
            self.recorder.current.end = t
        self.recorder.run.real_time = self.clk.real_time
        self.store.save_run(self.run_id, self.recorder.run, t, status, self.seed)
        self.clk.stop()
        self.recorder, self.run_id, self.paused = None, None, False
        self.world_avgs = self.store.world_averages(self.preset_id)
        self.run_changed.emit()

    def finish_run(self):
        self._end("finished")

    def abandon_run(self):
        self._end("abandoned")

    def on_history_changed(self):
        self.world_avgs = self.store.world_averages(self.preset_id)

    # ---- presets
    def set_preset(self, preset_id: int | None):
        """The preset for the run in progress (if any) and every run after it."""
        if preset_id == self.preset_id:
            return
        self.preset_id = preset_id
        self.store.set_setting("preset_id", str(preset_id or ""))
        if self.run_id is not None:
            self.store.set_run_preset(self.run_id, preset_id)
        self.world_avgs = self.store.world_averages(preset_id)   # the Live card compares within the preset
        self.preset_selected.emit()

    def presets_edited(self, deleted: int | None = None):
        """Call after creating, renaming or deleting a preset."""
        if deleted is not None and deleted == self.preset_id:
            self.set_preset(None)
        self.presets_changed.emit()
        self.history_changed.emit()

    def set_track_keyblades(self, on: bool):
        self.track_keyblades = on
        self.store.set_setting("track_keyblades", "1" if on else "0")
        self.filters_changed.emit()

    def event_visible(self, e) -> bool:
        return self.track_keyblades or e.category != "Keyblade"

    @property
    def username(self) -> str:
        return self.store.setting("username")

    def set_username(self, name: str):
        name = name.strip()
        if name != self.username:
            self.store.set_setting("username", name)
            self.username_changed.emit()

    def set_auto_start(self, on: bool):
        self.auto_start = on
        self.store.set_setting("auto_start", "1" if on else "0")
