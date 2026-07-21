# Plan: next three milestones

Agreed working plan as of 2026-07. The release is intentionally *not*
on this list — it happens whenever the maintainer calls it, and the
prep (CHANGELOG, release checklist, verified packaging) is already
done and waiting.

## 1. Retail verification of the completed journal layer — complete

*Small — one loop of the usual cycle.*

The objectives/categories parsers were the final code not yet proven
against retail at scale (they were built from 40-line samples).

- [x] `git pull`, then `bg3forge validate --max-issues 999` on the
      game machine
- [x] Result: 1,335 `objectives`, 14 `quest_categories`, zero issues
- [x] Spot check: `PLA_ZhentShipment` resolved its localized category,
      first linked objective, and `PLA_ZhentShipment_Caravan` marker
- [x] Fold the new counts into `docs/baseline.md`

Completed 2026-07-21 against game data 4.8.700.7143220: clean sweep,
counts recorded, and the relationship chain verified.

## 2. Compiled Osiris reader (`story.div.osi`) — metadata level

*The next format project, LSF-sized. Deepens the quest graph the most.*

The shipped goal *source* already gives quest↔logic edges, but the
compiled story database is the authoritative, complete form (and the
Honour/HonourX variants ship only compiled). Same discipline as LSF:

- [x] Study the reference implementation (LSLib `Story/StoryReader`)
      before writing any struct — fetch the actual source, no
      from-memory format guessing (the LSF v6 lesson)
- [x] Scope v1 to *metadata*: header/version, goal list, database
      names/signatures, rule counts — enough to cross-check the goal
      scripts and diff Gustav vs Honour. Full rule decompilation is
      explicitly out of scope for v1
- [x] Parser in `parsers/osiris.py`, read-only; `game.story`
      lazy (current retail ships 11 files, and they are large)
- [x] Wire into `validate` (counts + per-file failures) so the retail
      run judges it; add a benchmark stage
- [x] Fixtures: hand-crafted minimal .osi per the reference structs
      (like the LSF byte-layout pinning tests)

Exit criterion: all 11 retail `story.div.osi` files parse; goal list
cross-checks against `game.goals` (every source goal appears in the
compiled story).

Implementation and synthetic layout tests completed 2026-07-21. The
first retail pass parsed ten files and identified Gustav's remaining
Osiris 1.13 expanded-value layout; the exit criterion remains open until
the follow-up sweep is clean.

## 3. BG3 Pathway integration — first real consumer

*The point of the whole library. Also the best API review we can get.*

- [ ] Inventory what Pathway actually needs from game data (items,
      spells, icons, builds/progressions, quests?)
- [ ] Depend on bg3forge via git ref (pinned commit) until the release
      is cut; no vendored copies
- [ ] Replace any existing extraction/scraping in Pathway with
      `Game`-API calls; Pathway should contain zero pak/format code
- [ ] Keep a running list of friction: every awkward call, missing
      field, or slow path becomes an issue here — real consumer
      feedback beats speculative API design
- [ ] Progressions are the likely gap: the parser exists but has no
      typed model/joins yet (classes → levels → spells/passives).
      Expect this milestone to drive that work

Exit criterion: Pathway builds its dataset entirely through bg3forge,
and the friction list has been triaged into issues.

## Sequencing

Milestone 1 is complete. Milestones 2 and 3 are independent and can
interleave; default order is 2 then 3, but if Pathway work is ready to
start, 3 can lead — its friction list would inform what "metadata level"
needs to mean for 2.
