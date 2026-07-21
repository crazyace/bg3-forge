# Retail validation checklist

How to run the first validation pass against a real BG3 install and
capture the project's baseline numbers. Windows/PowerShell commands
shown; the Linux/macOS equivalents are the obvious ones.

## 1. Set up

```powershell
cd D:\Projects\bg3-forge
python --version                      # needs 3.10+
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[all,dev]"
pip install psutil                    # Windows only: enables Peak RSS in benchmark
```

## 2. Sanity-check the toolkit itself

```powershell
pytest
```

Expected: **98 passed** in under a couple of seconds. This proves the
environment before any game data is involved — if this fails, stop and
report it; nothing else will be meaningful.

## 3. Diagnose the install

```powershell
bg3forge doctor
```

Auto-detects Steam/GOG installs. If yours isn't found:

```powershell
bg3forge --game-path "C:\Program Files (x86)\Steam\steamapps\common\Baldurs Gate 3" doctor
# or persistently:
$env:BG3_PATH = "C:\...\Baldurs Gate 3"
```

Expected: all ✓, `Warnings: None`, and a real `Game data version` line.
Capture the output either way — the version line anchors every later
report.

## 4. The coverage sweep (the actual validation)

```powershell
bg3forge validate --max-issues 999 *> validate.txt
$LASTEXITCODE                         # 0 = every recognized file parsed
Get-Content validate.txt
```

This parses **every** stats/loca/LSX/LSF/atlas file in every pak, so
expect it to run for a few minutes on a full install. Two outcomes:

* **Exit 0** — every format assumption held on real data. The counts
  block (how many stats entries, templates, handles, …) is itself part
  of the baseline; save it.
* **Exit 1** — the issues list is exactly the set of files that
  disprove an assumption. That's not a failed test run, it's the
  deliverable: file `validate.txt` in an issue (or paste it back into
  the session) and each entry becomes a targeted fix with the offending
  path attached.

## 5. The baseline benchmark

Run it **twice, back to back**, and keep both outputs:

```powershell
bg3forge benchmark *> benchmark-cold.txt
bg3forge benchmark *> benchmark-warm.txt
```

The first run pays OS file-cache misses ("cold-ish"; a truly cold run
needs a reboot first — nice to have, not required), the second shows
steady-state. Note in the file names or a comment which patch the game
was on (doctor's version line covers this).

## 6. Optional but valuable extras

```powershell
# End-to-end export — proves the full pipeline and times it for real:
bg3forge export sqlite -o export
bg3forge export json -o export-json

# Spot-check the data quality in Python:
python -c "from bg3forge import Game; g = Game(); s = g.items.find('longsword'); print(len(g.items), len(g.spells)); print([i.display_name for i in s][:5])"
```

Sanity signals worth eyeballing: item/spell counts in plausible ranges
(tens of thousands of stats entries), display names actually localized
(not empty, not raw handles), and a known magic item resolving
`passives`/`spells` to non-empty lists.

## 7. What to bring back

1. `bg3forge doctor` output
2. `validate.txt` (plus exit code)
3. `benchmark-cold.txt` and `benchmark-warm.txt`
4. Anything surprising from step 6

Those four artifacts are the baseline the contributor policy
(CONTRIBUTING.md, principle #5) measures every future optimization
against — and the validate issues list, if any, is the highest-priority
bug list the project can have.
