# Plan: next three milestones

Agreed working plan as of 2026-07. The release is intentionally *not*
on this list — it happens whenever the maintainer calls it, and the
prep (CHANGELOG, release checklist, verified packaging) is already
done and waiting.

## 1. Retail verification of the completed journal layer

*Small — one loop of the usual cycle.*

The objectives/categories parsers are the only code not yet proven
against retail at scale (they were built from 40-line samples).

- [ ] `git pull`, then `bg3forge validate --max-issues 999` on the
      game machine
- [ ] Expect: `objectives` in the low thousands (~3.5k steps suggests
      a similar order), `quest_categories` in the dozens, zero issues
- [ ] Spot check: a real quest's `quest.category.display_name` and
      `quest.objectives[0].markers`
- [ ] Fold the new counts into `docs/baseline.md`

Exit criterion: clean sweep with the two new counts recorded. Any
failure follows the standard loop (paste → fix → regression test).

## 2. Compiled Osiris reader (`story.div.osi`) — metadata level

*The next format project, LSF-sized. Deepens the quest graph the most.*

The shipped goal *source* already gives quest↔logic edges, but the
compiled story database is the authoritative, complete form (and the
Honour/HonourX variants ship only compiled). Same discipline as LSF:

- [ ] Study the reference implementation (LSLib `Story/StoryReader`)
      before writing any struct — fetch the actual source, no
      from-memory format guessing (the LSF v6 lesson)
- [ ] Scope v1 to *metadata*: header/version, goal list, database
      names/signatures, rule counts — enough to cross-check the goal
      scripts and diff Gustav vs Honour. Full rule decompilation is
      explicitly out of scope for v1
- [ ] Parser in `parsers/osiris.py`, read-only; `game.story`
      lazy (six files, but large)
- [ ] Wire into `validate` (counts + per-file failures) so the retail
      run judges it; add a benchmark stage
- [ ] Fixtures: hand-crafted minimal .osi per the reference structs
      (like the LSF byte-layout pinning tests)

Exit criterion: all six retail `story.div.osi` files parse; goal list
cross-checks against `game.goals` (every source goal appears in the
compiled story).

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

1 is a quick gate and goes first. 2 and 3 are independent and can
interleave; default order is 2 then 3, but if Pathway work is ready to
start, 3 can lead — its friction list would inform what "metadata
level" needs to mean for 2.
