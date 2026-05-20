"""JSON-driven validation services for the damage workbench."""

from __future__ import annotations

import importlib
import inspect
from functools import lru_cache
from pathlib import Path
from typing import Any

import sts2_env.powers  # noqa: F401

from sts2_env.core.creature import Creature
from sts2_env.core.damage import calculate_block
from sts2_env.core.enums import CardId, CombatSide, PowerId, ValueProp
from sts2_env.core.rng import Rng
from sts2_env.damage_lab.tracing import LabTraceRecorder
from sts2_env.relics.base import RelicId

_MONSTER_MODULES = (
    "sts2_env.monsters.act1_weak",
    "sts2_env.monsters.act1",
    "sts2_env.monsters.act2",
    "sts2_env.monsters.act3",
    "sts2_env.monsters.act4",
    "sts2_env.monsters.shared",
)


def validate_case(case: dict[str, Any]) -> dict[str, Any]:
    combat = _build_combat(case)
    recorder = LabTraceRecorder(combat)
    combat._damage_lab_recorder = recorder

    operations: list[dict[str, Any]] = []
    for operation in case.get("operations", []):
        recorder.begin_operation(operation)
        op_type = operation["type"]
        if op_type == "deal_damage":
            actor = _resolve_creature_ref(combat, operation["actor"])
            target = _resolve_creature_ref(combat, operation["target"])
            props = _resolve_props(operation.get("props", ["MOVE"]))
            combat.deal_damage(
                dealer=actor,
                target=target,
                amount=int(operation["base_damage"]),
                props=props,
            )
        elif op_type == "gain_block":
            actor = _resolve_creature_ref(combat, operation["actor"])
            props = _resolve_props(operation.get("props", ["MOVE"]))
            block = calculate_block(int(operation["base_block"]), actor, props, combat)
            actor.gain_block(block)
            recorder.current_operation["applied_block"] = block
        elif op_type == "apply_power":
            actor = _resolve_creature_ref(combat, operation["actor"])
            applier = _resolve_creature_ref(combat, operation["applier"]) if operation.get("applier") else None
            actor.apply_power(_resolve_power_id(operation["power_id"]), int(operation["amount"]), applier=applier)
            recorder.current_operation["applied_power"] = {
                "power_id": operation["power_id"],
                "amount": int(operation["amount"]),
                "target": operation["actor"],
                "applier": operation.get("applier"),
            }
        else:
            raise ValueError(f"Unsupported operation type: {op_type!r}")
        operations.append(recorder.end_operation())

    return {
        "name": case.get("name"),
        "seed": int(case.get("seed", 0)),
        "operations": operations,
        "final_state": _serialize_combat_state(combat),
    }


def validate_suite(suite: dict[str, Any]) -> dict[str, Any]:
    cases = []
    passed = 0
    failed = 0
    for case in suite.get("cases", []):
        result = validate_case(case)
        expected = case.get("expect")
        mismatches = _compare_partial(expected, result) if expected is not None else []
        case_report = {
            "name": case.get("name"),
            "passed": not mismatches,
            "result": result,
            "mismatches": mismatches,
        }
        cases.append(case_report)
        if mismatches:
            failed += 1
        else:
            passed += 1
    return {
        "summary": {
            "total": len(cases),
            "passed": passed,
            "failed": failed,
        },
        "cases": cases,
    }


def catalog_payload() -> dict[str, Any]:
    from sts2_env.characters.all import ALL_CHARACTERS

    return {
        "character_ids": [character.character_id for character in ALL_CHARACTERS],
        "card_ids": sorted(card_id.name for card_id in CardId),
        "relic_ids": sorted(relic_id.name for relic_id in RelicId),
        "powers": sorted(power_id.name for power_id in PowerId),
        "value_props": sorted(flag.name for flag in ValueProp if flag is not ValueProp.NONE),
        "monster_factories": sorted(_monster_factory_registry().keys()),
        "operation_types": ["deal_damage", "gain_block", "apply_power"],
    }


def load_case_input(path: str) -> dict[str, Any]:
    source = Path(path)
    if source.is_dir():
        cases = []
        for case_path in sorted(source.glob("*.json")):
            case = _load_json(case_path)
            case.setdefault("name", case_path.stem)
            cases.append(case)
        return {"cases": cases}
    return _load_json(source)


def _build_combat(case: dict[str, Any]):
    seed = int(case.get("seed", 0))
    character_id = case.get("character_id", "ironclad")
    player_spec = case.get("player", {})
    deck = _create_starting_deck(character_id)
    from sts2_env.core.combat import CombatState

    player_hp = int(player_spec.get("current_hp", player_spec.get("max_hp", 80)))
    player_max_hp = int(player_spec.get("max_hp", max(player_hp, 1)))
    combat = CombatState(
        player_hp=player_hp,
        player_max_hp=player_max_hp,
        deck=deck,
        rng_seed=seed,
        character_id=character_id,
        relics=player_spec.get("relics", []),
    )

    rng = Rng(seed)
    for index, enemy_spec in enumerate(case.get("enemies", [])):
        creature, ai = _build_enemy(enemy_spec, rng)
        if creature.monster_id is None:
            creature.monster_id = f"ENEMY_{index}"
        combat.add_enemy(creature, ai)

    combat.start_combat()
    combat._damage_lab_entity_labels = {combat.player: "player"}

    _apply_creature_spec(combat.player, player_spec)
    for index, enemy_spec in enumerate(case.get("enemies", [])):
        enemy = combat.enemies[index]
        combat._damage_lab_entity_labels[enemy] = f"enemy:{index}"
        _apply_creature_spec(enemy, enemy_spec)
    return combat


def _build_enemy(enemy_spec: dict[str, Any], rng: Rng):
    monster_factory = enemy_spec.get("monster_factory")
    if monster_factory:
        factory = _monster_factory_registry()[monster_factory]
        creature, ai = factory(rng)
        return creature, ai

    creature = Creature(
        max_hp=int(enemy_spec.get("max_hp", enemy_spec.get("current_hp", 50))),
        current_hp=int(enemy_spec.get("current_hp", enemy_spec.get("max_hp", 50))),
        side=CombatSide.ENEMY,
        monster_id=enemy_spec.get("monster_id"),
        combat_id=int(enemy_spec.get("combat_id", 0)),
    )

    def _noop(*_args, **_kwargs) -> None:
        return None

    from sts2_env.monsters.intents import Intent
    from sts2_env.monsters.state_machine import MonsterAI, MoveState
    from sts2_env.core.enums import IntentType

    ai = MonsterAI({"NOTHING": MoveState("NOTHING", _noop, [Intent(IntentType.UNKNOWN)], follow_up_id="NOTHING")}, "NOTHING")
    return creature, ai


def _apply_creature_spec(creature: Creature, spec: dict[str, Any]) -> None:
    creature.max_hp = int(spec.get("max_hp", creature.max_hp))
    creature.current_hp = int(spec.get("current_hp", creature.current_hp))
    creature.block = 0
    if spec.get("block"):
        creature.gain_block(int(spec["block"]), unpowered=True)
    creature.powers.clear()
    for power_spec in spec.get("powers", []):
        creature.apply_power(_resolve_power_id(power_spec["id"]), int(power_spec["amount"]))


def _resolve_creature_ref(combat, ref: str) -> Creature:
    if ref == "player":
        return combat.player
    if ref.startswith("enemy:"):
        index = int(ref.split(":", 1)[1])
        return combat.enemies[index]
    raise ValueError(f"Unsupported creature ref: {ref!r}")


def _resolve_power_id(power_name: str) -> PowerId:
    normalized = power_name.strip().upper()
    return PowerId[normalized]


def _resolve_props(prop_names: list[str]) -> ValueProp:
    props = ValueProp.NONE
    for name in prop_names:
        props |= ValueProp[name.strip().upper()]
    return props


def _serialize_combat_state(combat) -> dict[str, Any]:
    return {
        "player": _serialize_creature(combat.player),
        "enemies": [_serialize_creature(enemy) for enemy in combat.enemies],
    }


def _serialize_creature(creature: Creature) -> dict[str, Any]:
    return {
        "monster_id": creature.monster_id,
        "current_hp": creature.current_hp,
        "max_hp": creature.max_hp,
        "block": creature.block,
        "powers": [
            {
                "id": power_id.name,
                "amount": power.amount,
            }
            for power_id, power in sorted(creature.powers.items(), key=lambda item: item[0].name)
            if power.amount != 0
        ],
    }


def _compare_partial(expected: Any, actual: Any, path: str = "") -> list[dict[str, Any]]:
    if expected is None:
        return []
    if isinstance(expected, dict):
        mismatches: list[dict[str, Any]] = []
        actual_dict = actual if isinstance(actual, dict) else {}
        for key, expected_value in expected.items():
            child_path = f"{path}.{key}" if path else key
            mismatches.extend(_compare_partial(expected_value, actual_dict.get(key), child_path))
        return mismatches
    if isinstance(expected, list):
        mismatches = []
        actual_list = actual if isinstance(actual, list) else []
        for index, expected_value in enumerate(expected):
            child_path = f"{path}[{index}]"
            actual_value = actual_list[index] if index < len(actual_list) else None
            mismatches.extend(_compare_partial(expected_value, actual_value, child_path))
        return mismatches
    if expected != actual:
        return [{"path": path, "expected": expected, "actual": actual}]
    return []


@lru_cache(maxsize=1)
def _monster_factory_registry() -> dict[str, Any]:
    registry: dict[str, Any] = {}
    for module_name in _MONSTER_MODULES:
        module = importlib.import_module(module_name)
        for _, fn in inspect.getmembers(module, inspect.isfunction):
            if not fn.__name__.startswith("create_"):
                continue
            signature = inspect.signature(fn)
            if len(signature.parameters) != 1:
                continue
            try:
                creature, _ai = fn(Rng(0))
            except Exception:
                continue
            registry.setdefault(fn.__name__, fn)
            monster_id = getattr(creature, "monster_id", None)
            if monster_id:
                registry.setdefault(monster_id, fn)
    return registry


def _load_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _create_starting_deck(character_id: str):
    key = character_id.lower()
    if key == "ironclad":
        from sts2_env.cards.ironclad_basic import create_ironclad_starter_deck

        return create_ironclad_starter_deck()
    if key == "silent":
        from sts2_env.cards.silent import create_silent_starter_deck

        return create_silent_starter_deck()
    if key == "defect":
        from sts2_env.cards.defect import create_defect_starter_deck

        return create_defect_starter_deck()
    if key == "regent":
        from sts2_env.cards.regent import create_regent_starter_deck

        return create_regent_starter_deck()
    if key == "necrobinder":
        from sts2_env.cards.necrobinder import create_necrobinder_starter_deck

        return create_necrobinder_starter_deck()
    raise ValueError(f"Unsupported character_id for damage lab: {character_id!r}")
