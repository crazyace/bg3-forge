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

## 4. Custom spells and statuses

Spells are `type "SpellData"` with a `SpellType` (`Target`, `Projectile`,
`Shout`, `Zone`, …), typically `using` a base spell, plus
`SpellProperties`/`SpellRoll`/`SpellSuccess`/`Level`/`Cooldown`. Statuses
are `type "StatusData"` with a `StatusType`. Both are the richest stats
schemas and are best modeled per-`SpellType`/`StatusType` when a consumer
needs them — not speculatively.

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
