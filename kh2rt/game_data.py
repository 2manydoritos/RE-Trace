"""
Static KH2 data: game-version addresses, world IDs, trackable items, milestones.

Addresses, item offsets and milestone flags are ported from the open-source
KH2 rando tracker by equations19 (Apache 2.0):
https://github.com/KH2FM-Mods-equations19/kh2-rando-tracker
If a game patch breaks tracking, update the VERSIONS table below.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

EXE_NAME = "KINGDOM HEARTS II FINAL MIX.exe"


@dataclass(frozen=True)
class LoadTiming:
    """Load-remover / start / end addresses, from the KH2 Randomizer LiveSplit load remover
    (aliosgaming/KH2FM_Load_Remover-FOR-RANDOMIZER), so RE:Trace times runs the same way."""
    black: int        # byte: 128 while the screen is fully black
    loadscreen: int   # byte: 3 while the load screen is showing
    load: int         # bool: game is loading
    start_ptr: int    # pointer; value at +0x1AC goes 132 -> 0 when you pick YES on "Start game with these settings?"
    btlend: int       # byte: becomes 4 the instant a battle ends (Final Xemnas: TWTNW room 0x14, event 0x4A)


@dataclass(frozen=True)
class GameVersion:
    name: str
    version_check: int      # byte at this offset must equal 106
    now: int                # current location struct
    save: int               # save data in RAM
    ability_to_pause: int   # 4/5 = dying / continue screen
    timing: LoadTiming | None = None   # None: no load removal for this version (real time is used)


VERSION_CHECK_VALUE = 106
START_OFFSET = 0x1AC
FINAL_XEMNAS = (0x12, 0x14, 0x4A)   # world, room, event of the Final Xemnas fight

VERSIONS = [
    GameVersion("Steam 1.0.0.10", 0x660EF4, 0x717008, 0x9A98B0, 0xABB878,
                LoadTiming(0xABB3C7, 0x7435D0, 0x8EC5B3, 0xBEE6B0, 0x2A0FCE0)),
    GameVersion("Steam Global 1.0.0.9", 0x660E74, 0x717008, 0x9A9830, 0xABB7F8,
                LoadTiming(0xABB347, 0x7435D0, 0x8EC543, 0xBEE630, 0x2A0FC60)),
    GameVersion("Steam JP 1.0.0.9", 0x65FDF4, 0x716008, 0x9A8830, 0xABA7F8),
    GameVersion("Epic 1.0.0.10", 0x660E44, 0x716DF8, 0x9A9330, 0xABB2F8,
                LoadTiming(0xABAE47, 0x743350, 0x8EC053, 0xBEE130, 0x2A0F760)),
    GameVersion("Epic Global 1.0.0.9", 0x660E04, 0x716DF8, 0x9A92F0, 0xABB2B8,
                LoadTiming(0xABAE07, 0x743350, 0x8EBFF3, 0xBEE0F0, 0x2A0F720)),
]

# ---------------------------------------------------------------- worlds

# (start, end) gradient per world. Edit freely.
WORLD_GRADIENTS = {
    "Garden of Assemblage": ("#6C7390", "#A3AACB"),
    "Twilight Town": ("#FF6B1A", "#FFB64C"),
    "Simulated Twilight Town": ("#6DA1D0", "#C8EDFB"),
    "Hollow Bastion": ("#FF75D1", "#FFC283"),
    "Beast's Castle": ("#D312C0", "#FF64C3"),
    "Olympus Coliseum": ("#83CA51", "#F4FF6A"),
    "Agrabah": ("#EA7405", "#FFEF3F"),
    "Land of Dragons": ("#C82A37", "#FF7C3D"),
    "100 Acre Wood": ("#C3B61F", "#FFFF6F"),
    "Pride Lands": ("#C7273A", "#FF8D43"),
    "Atlantica": ("#1F6FC0", "#5FD0F0"),
    "Disney Castle": ("#3098F8", "#81FAFF"),
    "Halloween Town": ("#835AE9", "#CC88FF"),
    "Port Royal": ("#7461F7", "#A6CBFF"),
    "Space Paranoids": ("#6B5E8F", "#AFA6CC"),   # dusty violet, distinct from HT
    "The World That Never Was": ("#8F99B8", "#E4E9F5"),
}
WORLD_ORDER = list(WORLD_GRADIENTS)

# Icon files in kh2rt/icons (from the KH2 rando tracker's location icons)
WORLD_ICONS = {
    "Garden of Assemblage": "garden_of_assemblage", "Twilight Town": "twilight_town",
    "Simulated Twilight Town": "simulated_twilight_town", "Hollow Bastion": "hollow_bastion",
    "Beast's Castle": "beasts_castle", "Olympus Coliseum": "olympus_coliseum", "Agrabah": "agrabah",
    "Land of Dragons": "land_of_dragons", "100 Acre Wood": "hundred_acre_wood", "Pride Lands": "pride_lands",
    "Atlantica": "atlantica", "Disney Castle": "disney_castle", "Halloween Town": "halloween_town",
    "Port Royal": "port_royal", "Space Paranoids": "space_paranoids",
    "The World That Never Was": "twtnw", "Drive Forms": "drive_forms",
    "General": "sora",
}
WORLD_COLOURS = {w: g[0] for w, g in WORLD_GRADIENTS.items()}   # single-colour fallback

WORLD_IDS = {
    0x02: "Twilight Town",
    0x04: "Hollow Bastion",
    0x05: "Beast's Castle",
    0x06: "Olympus Coliseum",
    0x07: "Agrabah",
    0x08: "Land of Dragons",
    0x09: "100 Acre Wood",
    0x0A: "Pride Lands",
    0x0B: "Atlantica",
    0x0C: "Disney Castle",
    0x0D: "Disney Castle",  # Timeless River
    0x0E: "Halloween Town",
    0x10: "Port Royal",
    0x11: "Space Paranoids",
    0x12: "The World That Never Was",
}

STT_FLAG_OFFSET = 0x1CFF  # == 13 while in Simulated Twilight Town
SORA_LEVEL_OFFSET = 0x24FF


def resolve_world(world: int, room: int, event: int, in_stt: bool) -> str | None:
    """Maps raw IDs to the rando 'world' a player thinks in (e.g. AS Zexion counts as OC)."""
    base = WORLD_IDS.get(world)
    if base == "Hollow Bastion":
        if room == 0x1A:
            return "Garden of Assemblage"
        if room == 0x20:
            return "Halloween Town"  # Vexen
        if room == 0x21:
            if event in (0x7A, 0x7B, 0x84, 0x85, 0x8E, 0x93):
                return "Agrabah"  # Lexaeus
            if event in (0x80, 0x81, 0x8A, 0x8B, 0x8F, 0x94):
                return "Space Paranoids"  # Larxene
        if room == 0x22:
            return "Olympus Coliseum"  # Zexion
        if room == 0x26:
            return "Disney Castle"  # Marluxia
    if base == "Twilight Town":
        if in_stt:
            return "Simulated Twilight Town"
        if (room == 0x20 and event == 0x01) or (room == 0x01 and event == 0x34):
            return "Garden of Assemblage"  # crit bonus selection
    if base == "The World That Never Was":
        data_orgs = {0x15: (0x72, "Simulated Twilight Town"), 0x0A: (0x6C, "Land of Dragons"),
                     0x0F: (0x6E, "Pride Lands"), 0x0E: (0x70, "Port Royal")}
        if room in data_orgs and event == data_orgs[room][0]:
            return data_orgs[room][1]
    return base


# ---------------------------------------------------------------- items

@dataclass(frozen=True)
class Item:
    key: str
    name: str
    category: str
    offset: int
    mask: int = 0          # 0 = count byte, else bitmask


def _counts(cat, rows):
    return [Item(k, n, cat, o) for k, n, o in rows]


def _bits(cat, rows):
    return [Item(k, n, cat, o, m) for k, n, o, m in rows]


ITEMS: list[Item] = [
    *_counts("Magic", [
        ("fire", "Fire", 0x3594), ("blizzard", "Blizzard", 0x3595), ("thunder", "Thunder", 0x3596),
        ("cure", "Cure", 0x3597), ("reflect", "Reflect", 0x35D0), ("magnet", "Magnet", 0x35CF)]),
    *_counts("Proof", [
        ("proof_connection", "Proof of Connection", 0x36B2),
        ("proof_nonexistence", "Proof of Nonexistence", 0x36B3),
        ("proof_peace", "Proof of Peace", 0x36B4)]),
    *_bits("Drive Form", [
        ("valor", "Valor Form", 0x36C0, 0x80), ("wisdom", "Wisdom Form", 0x36C0, 0x04),
        ("limit", "Limit Form", 0x36CA, 0x08), ("master", "Master Form", 0x36C0, 0x40),
        ("final", "Final Form", 0x36C2, 0x02)]),
    *_bits("Summon", [
        ("baseball", "Baseball Charm", 0x36C0, 0x08), ("lamp", "Lamp Charm", 0x36C4, 0x10),
        ("ukulele", "Ukulele Charm", 0x36C0, 0x01), ("feather", "Feather Charm", 0x36C4, 0x20)]),
    *_bits("Report", [(f"report{i}", f"Ansem Report {i}", o, m) for i, (o, m) in enumerate([
        (0x36C4, 0x40), (0x36C4, 0x80), (0x36C5, 0x01), (0x36C5, 0x02), (0x36C5, 0x04),
        (0x36C5, 0x08), (0x36C5, 0x10), (0x36C5, 0x20), (0x36C5, 0x40), (0x36C5, 0x80),
        (0x36C6, 0x01), (0x36C6, 0x02), (0x36C6, 0x04)], start=1)]),
    *_counts("Key Item", [
        ("torn_page", "Torn Page", 0x3598), ("promise_charm", "Promise Charm", 0x3694),
        ("olympus_stone", "Olympus Stone", 0x3644), ("unknown_disk", "Unknown Disk", 0x365F),
        ("hades_cup", "Hades Cup Trophy", 0x3696),
        ("pouch_olette", "Munny Pouch (Olette)", 0x363C), ("pouch_mickey", "Munny Pouch (Mickey)", 0x3695)]),
    *_counts("Visit Unlock", [
        ("beasts_claw", "Beast's Claw", 0x35B3), ("bone_fist", "Bone Fist", 0x35B4),
        ("proud_fang", "Proud Fang", 0x35B5), ("battlefields", "Battlefields of War", 0x35AE),
        ("ancestor_sword", "Sword of the Ancestor", 0x35AF), ("skill_crossbones", "Skill and Crossbones", 0x35B6),
        ("scimitar", "Scimitar", 0x35C0), ("identity_disk", "Identity Disk", 0x35C2),
        ("way_to_dawn", "Way to the Dawn", 0x35C1), ("membership_card", "Membership Card", 0x3643),
        ("royal_summons", "Royal Summons", 0x365D), ("ice_cream", "Ice Cream", 0x3649),
        ("namine_sketches", "Namine's Sketches", 0x3642)]),
    *_counts("Keyblade", [
        ("oathkeeper", "Oathkeeper", 0x35A2), ("bond_of_flame", "Bond of Flame", 0x368D),
        ("sleeping_lion", "Sleeping Lion", 0x3689), ("winners_proof", "Winner's Proof", 0x3699),
        ("wishing_lamp", "Wishing Lamp", 0x3687), ("rumbling_rose", "Rumbling Rose", 0x3685),
        ("monochrome", "Monochrome", 0x3680), ("decisive_pumpkin", "Decisive Pumpkin", 0x3688),
        ("hidden_dragon", "Hidden Dragon", 0x367C), ("heros_crest", "Hero's Crest", 0x367F),
        ("circle_of_life", "Circle of Life", 0x3682), ("follow_the_wind", "Follow the Wind", 0x3681),
        ("photon_debugger", "Photon Debugger", 0x3683), ("two_become_one", "Two Become One", 0x3698),
        ("sweet_memories", "Sweet Memories", 0x368A)]),
]

# Growth abilities: 2-byte value; level = (value & 0x0FFF) - base
GROWTH = [
    ("high_jump", "High Jump", 0x25CE, 93), ("quick_run", "Quick Run", 0x25D0, 97),
    ("dodge_roll", "Dodge Roll", 0x25D2, 563), ("aerial_dodge", "Aerial Dodge", 0x25D4, 101),
    ("glide", "Glide", 0x25D6, 105),
]

# Second Chance / Once More: ability IDs anywhere in this list
ABILITY_LIST_OFFSET, ABILITY_LIST_LEN = 0x2544, 158
ABILITY_IDS = {0x9F: ("second_chance", "Second Chance"), 0xA0: ("once_more", "Once More")}

# Drive form levels: one byte each, 1..7
DRIVE_LEVELS = [
    ("valor_lv", "Valor Form", 0x32F6), ("wisdom_lv", "Wisdom Form", 0x332E),
    ("limit_lv", "Limit Form", 0x3366), ("master_lv", "Master Form", 0x339E),
    ("final_lv", "Final Form", 0x33D6),
]

CATEGORY_OF = {i.key: i.category for i in ITEMS}
CATEGORY_OF.update({k: "Drive Level" for k, *_ in DRIVE_LEVELS})
CATEGORY_OF.update({k: "Growth" for k, *_ in GROWTH})
CATEGORY_OF.update({"second_chance": "Ability", "once_more": "Ability"})

# Milestones (boss kills / world progress)
MILESTONES = json.loads((Path(__file__).parent / "milestones.json").read_text())
FINAL_MILESTONE = "Xemnas (Final)"

# One contiguous read of save data covers everything above.
SAVE_READ_START = 0x1C00
SAVE_READ_END = 0x3720
