"""Act 1 weak monsters: Nibbit, ShrinkerBeetle, FuzzyWurmCrawler, Slimes.

All HP ranges and damage values verified against decompiled C# source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts2_env.core.creature import Creature
from sts2_env.core.enums import CombatSide, MoveRepeatType, PowerId, ValueProp
from sts2_env.core.damage import calculate_damage, apply_damage
from sts2_env.core.rng import Rng
from sts2_env.monsters.intents import (
    Intent, IntentType, attack_intent, buff_intent,
    debuff_intent, strong_debuff_intent, status_intent,
)
from sts2_env.monsters.state_machine import (
    ConditionalBranchState, MonsterAI, MonsterState, MoveState, RandomBranchState,
)
from sts2_env.cards.status import make_slimed

if TYPE_CHECKING:
    from sts2_env.core.combat import CombatState


# ---- Helpers ----

def _deal_damage_to_player(combat: CombatState, creature: Creature, base_dmg: int, hits: int = 1) -> None:
    """Monster deals powered damage to player."""
    for _ in range(hits):
        if combat.primary_player.is_dead:
            break
        dmg = calculate_damage(base_dmg, creature, combat.primary_player, ValueProp.MOVE, combat)
        apply_damage(combat.primary_player, dmg, ValueProp.MOVE, combat, creature)
        combat._check_combat_end()  # noqa: SLF001
        if combat.is_over:
            break


def _gain_block(creature: Creature, amount: int, combat: CombatState) -> None:
    if combat.is_over:
        return
    before = creature.block
    creature.gain_block(amount)
    gained = creature.block - before
    if gained > 0:
        from sts2_env.core.hooks import fire_after_block_gained

        fire_after_block_gained(creature, gained, combat, ValueProp.MOVE, None)


# ---- ShrinkerBeetle (HP 38-40) ----
# Cycle: SHRINKER_MOVE → CHOMP_MOVE → STOMP_MOVE → CHOMP_MOVE → STOMP_MOVE...

def create_shrinker_beetle(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(38, 40)
    creature = Creature(max_hp=hp, monster_id="SHRINKER_BEETLE")

    def shrink(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.SHRINK, 1)

    def chomp(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, 7)

    def stomp(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, 13)

    states: dict[str, MonsterState] = {
        "SHRINKER_MOVE": MoveState(
            "SHRINKER_MOVE",
            shrink,
            [strong_debuff_intent()],
            follow_up_id="CHOMP_MOVE",
        ),
        "CHOMP_MOVE": MoveState("CHOMP_MOVE", chomp, [attack_intent(7)], follow_up_id="STOMP_MOVE"),
        "STOMP_MOVE": MoveState("STOMP_MOVE", stomp, [attack_intent(13)], follow_up_id="CHOMP_MOVE"),
    }
    return creature, MonsterAI(states, "SHRINKER_MOVE")


# ---- FuzzyWurmCrawler (HP 55-57) ----
# Cycle: ACID_GOOP → INHALE → ACID_GOOP → ACID_GOOP → INHALE...

def create_fuzzy_wurm_crawler(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(55, 57)
    creature = Creature(max_hp=hp, monster_id="FUZZY_WURM_CRAWLER")

    def acid_goop(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, 4)

    def inhale(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 7)

    states: dict[str, MonsterState] = {
        "FIRST_ACID_GOOP": MoveState("FIRST_ACID_GOOP", acid_goop, [attack_intent(4)], follow_up_id="INHALE"),
        "INHALE": MoveState("INHALE", inhale, [buff_intent()], follow_up_id="ACID_GOOP"),
        "ACID_GOOP": MoveState("ACID_GOOP", acid_goop, [attack_intent(4)], follow_up_id="FIRST_ACID_GOOP"),
    }
    return creature, MonsterAI(states, "FIRST_ACID_GOOP")


# ---- Nibbit (HP 42-46) ----
# Conditional start based on IsAlone/IsFront, then fixed rotation:
# BUTT_MOVE(12) → SLICE_MOVE(6+5blk) → HISS_MOVE(Str+2) → BUTT_MOVE...

def create_nibbit(rng: Rng, is_alone: bool = True, is_front: bool = False) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(42, 46)
    creature = Creature(max_hp=hp, monster_id="NIBBIT")

    def butt(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, 12)

    def slice_move(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, 6)
        _gain_block(creature, 5, combat)

    def hiss(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 2)

    states: dict[str, MonsterState] = {
        "BUTT_MOVE": MoveState("BUTT_MOVE", butt, [attack_intent(12)], follow_up_id="SLICE_MOVE"),
        "SLICE_MOVE": MoveState("SLICE_MOVE", slice_move, [attack_intent(6)], follow_up_id="HISS_MOVE"),
        "HISS_MOVE": MoveState("HISS_MOVE", hiss, [buff_intent()], follow_up_id="BUTT_MOVE"),
    }

    # Determine starting state
    if is_alone:
        initial = "BUTT_MOVE"
    elif is_front:
        initial = "SLICE_MOVE"
    else:
        initial = "HISS_MOVE"

    cond = ConditionalBranchState("INITIAL")
    cond.add_branch(lambda: is_alone, "BUTT_MOVE")
    cond.add_branch(lambda: is_front, "SLICE_MOVE")
    cond.add_branch(lambda: True, "HISS_MOVE")
    states["INITIAL"] = cond

    return creature, MonsterAI(states, initial, rng)


# ---- LeafSlimeS (HP 11-15) ----
# Random: BUTT_MOVE(3) or GOOP_MOVE(add Slimed), CannotRepeat

def create_leaf_slime_s(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(11, 15)
    creature = Creature(max_hp=hp, monster_id="LEAF_SLIME_S")

    def butt(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, 3)

    def goop(combat: CombatState) -> None:
        combat.add_card_to_discard(make_slimed())

    rand = RandomBranchState("RANDOM")
    rand.add_branch("BUTT_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("GOOP_MOVE", MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        "RANDOM": rand,
        "BUTT_MOVE": MoveState("BUTT_MOVE", butt, [attack_intent(3)], follow_up_id="RANDOM"),
        "GOOP_MOVE": MoveState("GOOP_MOVE", goop, [status_intent()], follow_up_id="RANDOM"),
    }
    return creature, MonsterAI(states, "RANDOM", rng)


# ---- TwigSlimeS (HP 7-11) ----
# BUTT_MOVE(4) → BUTT_MOVE(4) (self loop)

def create_twig_slime_s(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(7, 11)
    creature = Creature(max_hp=hp, monster_id="TWIG_SLIME_S")

    def butt(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, 4)

    states: dict[str, MonsterState] = {
        "BUTT_MOVE": MoveState("BUTT_MOVE", butt, [attack_intent(4)], follow_up_id="BUTT_MOVE"),
    }
    return creature, MonsterAI(states, "BUTT_MOVE")


# ---- LeafSlimeM (HP 32-35) ----
# Strict alternation: STICKY_SHOT(add 2 Slimed) → CLUMP_SHOT(8) → STICKY_SHOT...

def create_leaf_slime_m(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(32, 35)
    creature = Creature(max_hp=hp, monster_id="LEAF_SLIME_M")

    def sticky_shot(combat: CombatState) -> None:
        for _ in range(2):
            combat.add_card_to_discard(make_slimed())

    def clump_shot(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, 8)

    states: dict[str, MonsterState] = {
        "STICKY_SHOT": MoveState("STICKY_SHOT", sticky_shot, [status_intent()], follow_up_id="CLUMP_SHOT"),
        "CLUMP_SHOT": MoveState("CLUMP_SHOT", clump_shot, [attack_intent(8)], follow_up_id="STICKY_SHOT"),
    }
    return creature, MonsterAI(states, "STICKY_SHOT")


# ---- TwigSlimeM (HP 26-28) ----
# STICKY_SHOT_MOVE → Random(CLUMP_SHOT_MOVE[max 2 consec] | STICKY_SHOT_MOVE[CannotRepeat])

def create_twig_slime_m(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(26, 28)
    creature = Creature(max_hp=hp, monster_id="TWIG_SLIME_M")

    def sticky_shot(combat: CombatState) -> None:
        combat.add_card_to_discard(make_slimed())

    def clump_shot(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, 11)

    rand = RandomBranchState("RANDOM")
    rand.add_branch("CLUMP_SHOT_MOVE", MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2)
    rand.add_branch("STICKY_SHOT_MOVE", MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        "RANDOM": rand,
        "STICKY_SHOT_MOVE": MoveState(
            "STICKY_SHOT_MOVE",
            sticky_shot,
            [status_intent()],
            follow_up_id="RANDOM",
        ),
        "CLUMP_SHOT_MOVE": MoveState(
            "CLUMP_SHOT_MOVE",
            clump_shot,
            [attack_intent(11)],
            follow_up_id="RANDOM",
        ),
    }
    return creature, MonsterAI(states, "STICKY_SHOT_MOVE")
