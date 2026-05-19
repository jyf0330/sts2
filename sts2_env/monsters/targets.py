"""Target helpers for monster moves."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts2_env.core.creature import Creature
from sts2_env.core.enums import PowerId

if TYPE_CHECKING:
    from sts2_env.core.combat import CombatState


def living_player_targets(combat: CombatState) -> list[Creature]:
    return [
        state.creature
        for state in combat.combat_player_states
        if state.creature.is_alive
    ]


def player_or_pet_owner(target: Creature) -> Creature:
    return getattr(target, "pet_owner", None) or target


def apply_power_to_living_player_targets(
    combat: CombatState,
    power_id: PowerId,
    amount: int,
    *,
    applier: Creature | None = None,
    source: object | None = None,
    ignore_next_instance: bool = False,
) -> None:
    for target in living_player_targets(combat):
        combat.apply_power_to(
            target,
            power_id,
            amount,
            applier=applier,
            source=source,
            ignore_next_instance=ignore_next_instance,
        )
