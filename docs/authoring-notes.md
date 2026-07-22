# Mod authoring — format notes for future features

The capstone (`bg3forge.authoring.Mod`) currently produces items: a stats
entry, a RootTemplate in `_merged.lsf`, a `meta.lsx`, and localization,
packed into a loadable `.pak` (retail-verified — see `baseline.md`).

These notes record the file formats for the *next* authoring features,
learned by diffing a known-good retail item mod. They describe structure
only (generic BG3 field names), so the reference mod itself is not needed
again. Each maps to a proposed capstone API.

## 1. Obtainability — `TreasureTable.txt` — DONE

*Implemented: `write_treasure_tables`, `mod.place_in_treasure(table, item)`,
and the `treasure=` shortcut on `new_item`/`new_armor`.*

Items otherwise only exist; they aren't placed in the world. A mod makes
them obtainable by *patching an existing treasure table* (e.g. the
tutorial chest) at `Public/<Mod>/Stats/Generated/TreasureTable.txt`:

```
treasure itemtypes "Common","Uncommon","Rare","Epic","Legendary"
new treasuretable "<ExistingTableName>"
CanMerge 1
new subtable "-1"
object category "I_<StatsName>",1,0,0,0,0,0,0,0
```

Key points:

- Reusing an existing table name + `CanMerge 1` *injects* into it rather
  than replacing it — that's how items land in a base-game container.
- `object category "I_<StatsName>"` references an item by its stats name
  with an `I_` prefix; the trailing numbers are drop weights/frequencies.
- The parser side already exists (`parse_treasure_tables`); this needs a
  *writer* and a `mod.add_to_treasure(table, stats_name)` orchestration.

Proposed: `mod.place_in_treasure("<ExistingTableName>", "<item>")`.

## 2. Weapons — `new_weapon` — DONE

*Implemented: `mod.new_weapon(damage=, damage_type=, weapon_properties=, …)`,
routing on-wield `boosts`/`grants_spells` to `BoostsOnEquipMainHand` and
always-on effects to `DefaultBoosts`.*

Weapons are `type "Weapon"` stats with weapon-specific fields:

```
new entry "<Name>"
type "Weapon"
using "<BaseWeapon>"
data "RootTemplate" "<uuid>"
data "Damage" "2d6"
data "Damage Type" "Slashing"
data "Weapon Properties" "Twohanded;Heavy;Melee;Dippable"
data "BoostsOnEquipMainHand" "UnlockSpell(...);UnlockSpell(...)"
data "DefaultBoosts" "WeaponProperty(Magical)"
```

Note weapons use **`BoostsOnEquipMainHand`** (and off-hand variants), not
`Boosts` — the capstone's ability-merge logic would need weapon-aware
keys. A `mod.new_weapon(name, damage="2d6", damage_type="Slashing",
properties=[...], grants_spells=[...])` convenience fits the existing
`new_item` shape.

## 3. Custom passives — `new_passive` — DONE

*Implemented: `mod.new_passive(name, boosts=[...], display_name=…,
description=…)` returns the passive name for use in an item's
`passives=[...]`. Handles carry the `;version` suffix; `Properties` defaults
to `Highlighted`.*


The ability params reference *existing* passives; defining new ones is a
`type "PassiveData"` stats entry:

```
new entry "<Name>"
type "PassiveData"
using "<OptionalBasePassive>"
data "DisplayName" "<handle>;<version>"
data "Description" "<handle>;<version>"
data "Boosts" "DamageReduction(All, Flat, 3)"
```

Note the `DisplayName`/`Description` handles here carry a `;<version>`
suffix (unlike the RootTemplate handles). A `mod.new_passive(name,
boosts=[...], display_name=..., description=...)` would mint the handles
and register the loca, mirroring `new_item`.

## 4. Custom spells and statuses — DONE

*Statuses implemented: `mod.new_status(boosts=…, on_apply=…, …)` emits the
retail `StatusData` BOOST shape (StackId = name, `;version` handles,
`OnApplyFunctors` for instant effects). Spells implemented:
`mod.new_spell(using=…, …)` — the clone-and-tweak slice.*

Spells are `type "SpellData"` with a `SpellType` (`Target`, `Projectile`,
`Shout`, `Zone`, …), typically `using` a base spell, plus
`SpellProperties`/`SpellRoll`/`SpellSuccess`/`Level`/`Cooldown`. Statuses
are `type "StatusData"` with a `StatusType`. Both are the richest stats
schemas and are best modeled per-`SpellType`/`StatusType` when a consumer
needs them — not speculatively.

`new_spell`'s first slice leans on `using` inheritance: cloning a retail
base (e.g. `Projectile_FireBolt`) carries the targeting, animation, sound,
VFX, `UseCosts`, and `SpellFlags` plumbing, so a custom spell only
overrides identity (`DisplayName`/`Description`/`Icon`, `;version`
handles) and effect (`SpellRoll`/`SpellSuccess`/`SpellProperties`,
`TooltipDamageList`, `DamageType`). From-scratch definitions require
`spell_type=` and the full casting surface via `data=`. Delivery paths:
`new_scroll(spell=<custom>)` (the ActionType 12 `SkillID` accepts a modded
SpellData name) and `grants_spells=[<custom>]` on an equipped item
(`UnlockSpell`).

## 5. Consumables — scrolls, potions, elixirs — reference-existing forms DONE

*Implemented: `new_potion(status=…)`, `new_elixir(status=…)` (Consume action,
`StatusDuration` 0 / -1), and `new_scroll(spell=…)` (ActionType 12 with
`SkillID`, `CanUseSpellScroll` condition, shared retail `ClassId`). The
mechanism lives on the RootTemplate as `OnUsePeaceActions` — found by
inspecting retail templates; attribute types pinned (`int32`/`bool`/`guid`).
Fully-original consumables still await custom `SpellData`/`StatusData` (4).*

Consumables are `type "Object"` items with an on-use action, plus the usual
RootTemplate + treasure obtainability. Concrete slices to build when needed,
each verified in game like the others:

* **Scrolls** — an Object whose use casts a spell (references a `SpellData`
  by name). A `new_scroll(name, spell=…)` on top of the item pipeline.
* **Potions** — an Object that applies a status on drink
  (`StatusOnConsume` / consume actions → a `StatusData`). Pairs with the
  custom-status work in (4).
* **Elixirs** — like potions but with the long-rest-duration status pattern
  BG3 elixirs use.

These reuse the same spine (`new_item` → stats + template + loca + treasure)
and mostly add a small stats surface plus, for scrolls/potions, a referenced
spell or status. Custom spells/statuses (4) unblock the fully-original
versions; the referencing form (a scroll of an *existing* spell, a potion
applying an *existing* status) can land first.

## Sequencing

Obtainability (1), weapons (2), and custom passives (3) are **done** and
retail-verified. Custom spells/statuses (4) are the richest schemas and gate
fully-original consumables. Consumables (5) — scrolls, potions, elixirs —
are the next content family; the forms that reference existing spells and
statuses can land before (4). As on the read side, build each against a real
example and verify in game.

## Teachable spells — wizard transcription (Patch 8)

How "Learn Spell" on a scroll works, traced through retail data:

- A class's ``ClassDescription`` (LSX) carries ``CanLearnSpells`` and a
  ``SpellList`` guid.  The Wizard's is
  ``beb9389e-24f8-49b0-86a5-e8d08b6fdc2e``
  (``WIZARD_LEARNABLE_LIST``, 112 spells) — the transcription pool.
- The scroll needs nothing special: learnability = list membership plus a
  spell slot of the spell's level (combined caster levels); cost is
  50 gp × spell level; the scroll is consumed.
- Wizard progressions carry ``SelectSpells`` only at level 1 (verified in
  every file, all sources) — level-up and transcription both draw on the
  ClassDescription list, not per-level selector lists.
- The game replaces spell lists wholesale by UUID, so
  ``mod.replace_spell_list(uuid, spells)`` must ship the full set — read
  the current list via ``game.spell_lists[uuid]`` at build time.  Two
  mods replacing the same list conflict (last in load order wins).

Related discovery: the scroll action's ``ClassId`` *is* the Wizard
ClassDescription UUID (the class marked ``IsDefaultForUseSpellAction``).
Spotting that required fixing the LSF guid text rendering — Larian
stores the last two guid groups as little-endian 16-bit words, which
earlier releases rendered byte-swapped (on-disk bytes were always
correct; only cross-format text comparisons were affected).

## Hotbar casting economy (Misty Step census, Patch 8)

How a granted spell charges the player, from dumping all 25 retail
`MistyStep` SpellData variants and everything that grants them:

| Pattern | `UseCosts` | `Cooldown` |
| --- | --- | --- |
| Class spell, leveled slot | `BonusActionPoint:1;SpellSlotsGroup:1:1:2` (`_3`.._6` for upcasts) | — |
| Item free-cast, per short rest | `BonusActionPoint:1` | `OncePerShortRestPerItem` |
| Once per long rest | `BonusActionPoint:1` | `OncePerRest` |
| Once per turn | `BonusActionPoint:1` | `OncePerTurn` |
| Fully free | `""` (empty override) | — |

Key facts:

- The economy lives **on the spell**, not the grant: retail items
  (Teleport Boots, Drow Commander's Amulet, Nightwalkers) all use the
  bare ``UnlockSpell(SpellName)`` — exactly what ``grants_spells=[...]``
  emits. Each item grants its *own spell variant* with the desired costs.
- ``OncePerShortRestPerItem`` is per **item**: two copies of the amulet
  each carry a charge.
- The multi-argument form ``UnlockSpell(spell, AddChildren, <guid>, ,
  Wisdom)`` appears only in *class passives* (e.g. Land Druid's
  ``Land_Coast``) to override the casting ability — not needed for
  item-granted casts.
- Class-*learned* spells (spellbook/prepare/upcast via level-up) are a
  different mechanism entirely — spell lists + progressions — and remain
  future work on the write side.

## ActionType catalog (corpus survey, Patch 8)

From `scripts/wiring_survey.py` over all 25,564 retail templates — the
`OnUsePeaceActions` action types and their attributes. Implemented by the
authoring layer: **7** (Consume) and **12** (cast from scroll).

| ActionType | Count | Meaning / key attributes |
| --- | --- | --- |
| 8 | 1,200 | plain use (Animation/Conditions only) |
| 11 | 1,071 | read book — `BookId` |
| **7** | 298 | **consume — `StatsId`, `StatusDuration`, `IsHiddenStatus`** |
| **12** | 165 | **cast from scroll — `SkillID`, `ClassId` (optional: 31 omit it), `Consume`** |
| 33 | 111 | secondary cast variant — `SpellId` |
| 15 / 14 | 78 / 16 | heal actions — `Heal` |
| 3 | 39 | teleport/event — `EventID`, `Source`, `Target` |
| 23 / 16 | 28 / 10 | combine/insert — `CombineSlots`, `InsertSlots` |
| 30 | 20 | learn recipe — `RecipeID` |
| 24 | 45 | ladder (note Larian's shipped typos: `BotomHorizontalOffset`, `NodeLadderOffest`) |
| others | ≤10 each | doors (9), surfaces (4, 10), sound (26), misc (1, 2, 18, 19, 20, 31, 32, 35) |

Survey-verified invariants: `OnUseDescription` is always a short use-verb
(21 distinct texts, none over 25 chars); every action attribute has one
consistent LSF type across the corpus; `StatusDuration` uses 0, -1, or a
positive turn count; retail itself ships exactly one dangling consume
`StatsId` (`LOW_MEPHISTOSVAULT_CRYSTALFORM`).
