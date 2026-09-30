# RE:Trace

**A route tracker for the Kingdom Hearts II Final Mix Randomizer (PC).**

RE:Trace runs next to KH2 and records every seed you play: the worlds you visit in order, time per visit, checks, bosses, drive levels and deaths. Your runs are saved so you can see where your time goes, practise the slow parts, and race other players on the same seed. It only *reads* game memory and never writes to the game.

**[Download the latest RE-Trace.exe](../../releases/latest)**: no install needed. Windows SmartScreen may warn because the exe isn't code-signed; choose *More info → Run anyway*.

<!-- Screenshots: add images to docs/ and uncomment these lines.
![Live run](docs/live.png)
![Race](docs/race.png)
-->

## Supported versions

| Platform | Version | Timing |
|---|---|---|
| Steam | 1.0.0.10 | Loadless |
| Steam Global | 1.0.0.9 | Loadless |
| Steam JP | 1.0.0.9 | Real time only |
| Epic | 1.0.0.10 | Loadless |
| Epic Global | 1.0.0.9 | Loadless |

If a game update changes the memory layout, the header shows *"version isn't supported"* until RE:Trace is updated.

## Timing

Timing follows the KH2 Randomizer load remover for LiveSplit, so your time matches your splits.

- **Start:** with Auto-start on, the run starts the instant you pick YES on *"Start game with these settings?"*. You can also press **Start run**.
- **Loadless:** loads and black screens are removed, and the header shows *"Loading · timer held"* while that happens. Real time (RTA) is kept too.
- **End:** the run finishes on the frame Final Xemnas dies. **Finish** ends it by hand, **End unfinished** saves it as incomplete, and **Pause** stops the clock for breaks.
- **Steam JP 1.0.0.9** has no loadless timing, so it uses real time, starts when a fresh save reaches the GoA, and finishes when the Final Xemnas flag appears.

## Tabs

- **Live run:** your route as a coloured ribbon, each visit expandable to show its checks, bosses and deaths. For the current world you see this visit's time, your total there this run, and how that compares with your average (green = faster). Your notes for that world appear here too.
- **History:** every past run with its route, seed, preset and notes, plus that run's time per world, world breakdown and milestone splits. **Export** saves a run as a `.retrace` file for racing.
- **Stats:** average, best and worst time per world, visits, deaths, checks, and milestone splits (how far into a run you usually reach each boss).
- **Race:** compare runs with other players. See [Racing](#racing).
- **Notes:** practice notes for each world, plus general notes.

**Presets** group seeds played with the same settings (e.g. `FF4`, `1 Hour`). Pick one in the header before or during a run, or change a past run's preset in History; create, rename and delete them from the bottom of the dropdown. Stats can show one preset or **All presets**, and while a preset is selected, the Live tab compares you only against that preset's averages.

## Racing

1. Enter **Your racer name** at the top of the Race tab.
2. Export your run from History and send the `.retrace` file to the other racers. It includes your name, seed, route and times, but not your notes.
3. Press **New race**, then **Import .retrace…** (or drop files onto the tab) and **Add my run…**.

Everyone's route ribbons stack on one time scale, followed by side-by-side Summary, Route, Time per world, World breakdown and Milestone splits, with the fastest times in green. Races are saved with their own copy of each run.

## How tracking works

- **Worlds** follow rando conventions: Absent Silhouette and Data fights count toward their world (e.g. AS Zexion is Olympus Coliseum), GoA and crit-bonus selection count as Garden of Assemblage, and the Cavern of Remembrance counts as Hollow Bastion.
- **Checks** are detected from inventory changes: magic, drive forms, summons, proofs, reports, visit unlocks, torn pages, keyblades, growth abilities, Second Chance, Once More and more. Stat boosts, accessories and other filler aren't logged. Keyblades and growth are listed but don't count toward check totals.
- **Your data** stays on your PC in `%APPDATA%\RE-Trace\`, and nothing is uploaded.

## Running from source

You need Windows and [Python](https://www.python.org/downloads/) 3.10 or newer, with *"Add python.exe to PATH"* ticked.

| Script | What it does |
|---|---|
| `Run Tracker.bat` | Installs PySide6 into a local `.venv` on first launch, then starts RE:Trace |
| `Run Demo.bat` | Plays a fake, sped-up run with no game needed, in a separate history |
| `Build EXE.bat` | Builds `dist\RE-Trace.exe` with PyInstaller |

```
kh2rt/
  main.py          entry point and options (--demo, --speed, --db)
  memory.py        attaches to the game and reads memory
  game_data.py     per-version addresses, items and worlds
  milestones.json  story and boss progress flags
  timing.py        loadless timing, start and end detection
  tracker.py       turns memory snapshots into visits, checks, milestones and deaths
  controller.py    connects the game, the recorder and storage
  storage.py       SQLite history, presets, races and stats
  race.py          the .retrace file format
  demo.py          a fake game for the demo and testing
  ui.py            the PySide6 interface
```

To support a new game version, add its addresses to `VERSIONS` in `kh2rt/game_data.py`.

## Credits

Memory addresses, item offsets, progress flags, world icons and the KHMenu font come from [kh2-rando-tracker](https://github.com/KH2FM-Mods-equations19/kh2-rando-tracker) by equations19, under the Apache License 2.0 (see [NOTICE.txt](NOTICE.txt) and [LICENSE-kh2-rando-tracker.txt](LICENSE-kh2-rando-tracker.txt)). Timing follows the [KH2FM Load Remover for Randomizer](https://github.com/aliosgaming/KH2FM_Load_Remover-FOR-RANDOMIZER).

Kingdom Hearts and its characters, symbols and artwork are © Disney / Square Enix. RE:Trace is an unofficial fan tool, not affiliated with or endorsed by them.
