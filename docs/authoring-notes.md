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

## 3. Custom passives — `new_passive`

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

## Sequencing

Obtainability (1) is the highest-value next step: without it, authored
items can only be spawned by console. Weapons (2) and custom passives (3)
are natural follow-ons that reuse the `new_item` pattern. Custom spells
and statuses (4) are larger and should wait for a concrete need. As with
the read side, build each against a real example and verify in game.
