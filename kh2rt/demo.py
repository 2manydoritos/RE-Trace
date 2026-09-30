"""A fake KH2 that plays a random rando route. Used by --demo and for testing."""
from __future__ import annotations

import random

from . import game_data as gd

V = gd.VERSIONS[0]
REVERSE = {"Twilight Town": 0x02, "Hollow Bastion": 0x04, "Beast's Castle": 0x05, "Olympus Coliseum": 0x06,
           "Agrabah": 0x07, "Land of Dragons": 0x08, "100 Acre Wood": 0x09, "Pride Lands": 0x0A,
           "Atlantica": 0x0B, "Disney Castle": 0x0C, "Halloween Town": 0x0E, "Port Royal": 0x10,
           "Space Paranoids": 0x11, "The World That Never Was": 0x12}


class FakeGame:
    def __init__(self, seed=None):
        self.version = V
        self.rng = random.Random(seed)
        self.now = bytearray(10)
        self.save = bytearray(0x4000)
        self.pause = 0
        self.plan = self._make_plan()
        self.step = 0
        self.step_left = 0.0
        self.start_val = 132      # "start game with these settings?" is up
        self.loading_left = 0.0   # seconds of load screen remaining
        self.btlend = 0
        self.done = False
        self._set_world("title")
        self.save[gd.SORA_LEVEL_OFFSET] = 1

    def _make_plan(self):
        worlds = [w for w in REVERSE if w not in ("Twilight Town", "The World That Never Was")]
        worlds.append("Simulated Twilight Town")
        self.rng.shuffle(worlds)
        plan = [("title", 8), ("Garden of Assemblage", 45)]
        for w in worlds[:9]:
            plan += [(w, self.rng.uniform(250, 700)), ("Garden of Assemblage", self.rng.uniform(15, 50))]
        plan.insert(4, ("Twilight Town", 420))
        for w in worlds[:3]:  # second visits
            plan += [(w, self.rng.uniform(150, 400)), ("Garden of Assemblage", 20)]
        plan.append(("The World That Never Was", 900))
        return plan

    def _set_world(self, w):
        if w == "title":
            self.now[0], self.now[1] = 0xFF, 0x00
            return
        self.save[gd.STT_FLAG_OFFSET] = 13 if w == "Simulated Twilight Town" else 0
        if w == "Garden of Assemblage":
            self.now[0], self.now[1] = 0x04, 0x1A
        elif w == "Simulated Twilight Town":
            self.now[0], self.now[1] = 0x02, 0x05
        else:
            self.now[0], self.now[1] = REVERSE[w], self.rng.randint(0, 12)

    def advance(self, dt: float):
        """Advance game time by dt seconds."""
        self.step_left -= dt
        if self.pause in (4, 5) and self.rng.random() < 0.2:
            self.pause = 0
        self.loading_left = max(0.0, self.loading_left - dt)
        if self.done:
            return
        if self.step_left <= 0 and self.step < len(self.plan):
            w, secs = self.plan[self.step]
            if self.step == 1:
                self.start_val = 0          # player picked YES
            self.step += 1
            self.step_left = secs
            self._set_world(w)
            self.loading_left = 0 if w == "title" else self.rng.uniform(2.0, 6.0)
        w = self.plan[max(0, self.step - 1)][0]
        if w in ("Garden of Assemblage", "title"):
            return
        p = dt / 45  # roughly one event per 45 game-seconds
        if self.rng.random() < p:
            it = self.rng.choice(gd.ITEMS)
            if it.mask:
                self.save[it.offset] |= it.mask
            elif self.save[it.offset] < 3:
                self.save[it.offset] += 1
        if self.rng.random() < p / 4:
            k, _n, off = self.rng.choice(gd.DRIVE_LEVELS)
            self.save[off] = min(7, max(1, self.save[off] + 1))
        if self.rng.random() < p / 2:
            self.save[gd.SORA_LEVEL_OFFSET] = min(99, self.save[gd.SORA_LEVEL_OFFSET] + 1)
        if self.rng.random() < p / 3:
            cands = [i for i, m in enumerate(gd.MILESTONES) if m["world"] == w
                     and not self.save[m["offset"]] & m["mask"] and m["name"] != gd.FINAL_MILESTONE]
            if cands:
                m = gd.MILESTONES[cands[0]]
                self.save[m["offset"]] |= m["mask"]
        if self.rng.random() < p / 12:
            self.pause = 4
        if self.step >= len(self.plan) and self.step_left < -60:
            # Final Xemnas: battle ends in TWTNW room 0x14, event 0x4A; the story flag lands a bit later
            self.now[0], self.now[1], self.now[8] = gd.FINAL_XEMNAS
            self.btlend = 4
            m = next(m for m in gd.MILESTONES if m["name"] == gd.FINAL_MILESTONE)
            self.save[m["offset"]] |= m["mask"]
            self.done = True

    FAKE_PTR = 0x7FF000000000

    def read_abs(self, address, size):
        if address == self.FAKE_PTR + gd.START_OFFSET:
            return self.start_val.to_bytes(4, "little")
        return bytes(size)

    def read(self, offset, size):
        t = V.timing
        if offset == t.black:
            return bytes([128 if self.loading_left > 1.0 else 0])
        if offset == t.load:
            return bytes([1 if self.loading_left > 0 else 0])
        if offset == t.loadscreen:
            return bytes([0])
        if offset == t.start_ptr:
            return self.FAKE_PTR.to_bytes(8, "little")
        if offset == t.btlend:
            return bytes([self.btlend])
        if V.now <= offset < V.now + 10:
            o = offset - V.now
            return bytes(self.now[o:o + size])
        if V.save <= offset < V.save + 0x4000:
            o = offset - V.save
            return bytes(self.save[o:o + size])
        if offset == V.ability_to_pause:
            return bytes([self.pause])
        return bytes(size)

    def alive(self):
        return True

    def close(self):
        pass
