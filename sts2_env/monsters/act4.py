"""Act 4 (Underdocks) monsters: weak, normal, elite, boss.

All HP ranges, damage values, and state machines verified against decompiled C# source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts2_env.core.creature import Creature
from sts2_env.core.enums import CombatSide, MoveRepeatType, PowerId, ValueProp
from sts2_env.core.damage import calculate_damage, apply_damage
from sts2_env.core.rng import Rng
from sts2_env.monsters.intents import (
    Intent, IntentType, attack_intent, multi_attack_intent,
    buff_intent, debuff_intent, strong_debuff_intent, status_intent,
    defend_intent, sleep_intent,
)
from sts2_env.monsters.state_machine import (
    ConditionalBranchState, MonsterAI, MonsterState, MoveState, RandomBranchState,
)

if TYPE_CHECKING:
    from sts2_env.core.combat import CombatState


# ---- Helpers ----

def _deal_damage_to_player(combat: CombatState, creature: Creature, base_dmg: int, hits: int = 1) -> None:
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

        fire_after_block_gained(creature, gained, combat)


# ========================================================================
# WEAK ENCOUNTERS
# ========================================================================

# ---- CorpseSlug (HP 25-27 / 27-29 asc) ----

def create_corpse_slug(rng: Rng, starter_idx: int = 0) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(25, 27)
    creature = Creature(max_hp=hp, monster_id="CORPSE_SLUG")
    whip_slap_dmg = 3
    glomp_dmg = 8

    def whip_slap(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, whip_slap_dmg, hits=2)

    def glomp(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, glomp_dmg)

    def goop(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.FRAIL, 2)

    states: dict[str, MonsterState] = {
        "WHIP_SLAP_MOVE": MoveState(
            "WHIP_SLAP_MOVE",
            whip_slap,
            [multi_attack_intent(whip_slap_dmg, 2)],
            follow_up_id="GLOMP_MOVE",
        ),
        "GLOMP_MOVE": MoveState("GLOMP_MOVE", glomp, [attack_intent(glomp_dmg)], follow_up_id="GOOP_MOVE"),
        "GOOP_MOVE": MoveState("GOOP_MOVE", goop, [debuff_intent()], follow_up_id="WHIP_SLAP_MOVE"),
    }

    starter_map = {0: "WHIP_SLAP_MOVE", 1: "GLOMP_MOVE", 2: "GOOP_MOVE"}
    initial = starter_map.get(starter_idx, "WHIP_SLAP_MOVE")

    creature.apply_power(PowerId.RAVENOUS, 4)
    return creature, MonsterAI(states, initial, rng)


# ---- Seapunk (HP 44-46 / 47-49 asc) ----

def create_seapunk(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(44, 46)
    creature = Creature(max_hp=hp, monster_id="SEAPUNK")
    sea_kick_dmg = 11
    spinning_kick_dmg = 2
    bubble_block = 7
    bubble_str = 1

    def sea_kick(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, sea_kick_dmg)

    def spinning_kick(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, spinning_kick_dmg, hits=4)

    def bubble_burp(combat: CombatState) -> None:
        _gain_block(creature, bubble_block, combat)
        creature.apply_power(PowerId.STRENGTH, bubble_str, applier=creature)

    states: dict[str, MonsterState] = {
        "SEA_KICK_MOVE": MoveState(
            "SEA_KICK_MOVE",
            sea_kick,
            [attack_intent(sea_kick_dmg)],
            follow_up_id="SPINNING_KICK_MOVE",
        ),
        "SPINNING_KICK_MOVE": MoveState(
            "SPINNING_KICK_MOVE",
            spinning_kick,
            [multi_attack_intent(spinning_kick_dmg, 4)],
            follow_up_id="BUBBLE_BURP_MOVE",
        ),
        "BUBBLE_BURP_MOVE": MoveState(
            "BUBBLE_BURP_MOVE",
            bubble_burp,
            [buff_intent(), defend_intent()],
            follow_up_id="SEA_KICK_MOVE",
        ),
    }
    return creature, MonsterAI(states, "SEA_KICK_MOVE")


# ---- SludgeSpinner (HP 37-39 / 41-42 asc) ----

def create_sludge_spinner(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(37, 39)
    creature = Creature(max_hp=hp, monster_id="SLUDGE_SPINNER")
    oil_spray_dmg = 8
    slam_dmg = 11
    rage_dmg = 6

    def oil_spray(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, oil_spray_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.WEAK, 1, applier=creature)

    def slam(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, slam_dmg)

    def rage(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, rage_dmg)
        combat.apply_power_to(creature, PowerId.STRENGTH, 3, applier=creature)

    rand = RandomBranchState("RAND")
    rand.add_branch("OIL_SPRAY_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("SLAM_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("RAGE_MOVE", MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        "RAND": rand,
        "OIL_SPRAY_MOVE": MoveState(
            "OIL_SPRAY_MOVE",
            oil_spray,
            [attack_intent(oil_spray_dmg), debuff_intent()],
            follow_up_id="RAND",
        ),
        "SLAM_MOVE": MoveState("SLAM_MOVE", slam, [attack_intent(slam_dmg)], follow_up_id="RAND"),
        "RAGE_MOVE": MoveState(
            "RAGE_MOVE",
            rage,
            [attack_intent(rage_dmg), buff_intent()],
            follow_up_id="RAND",
        ),
    }
    return creature, MonsterAI(states, "OIL_SPRAY_MOVE")


# ---- Toadpole (HP 21-25 / 22-26 asc) ----

def create_toadpole(rng: Rng, slot: str = "first") -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(21, 25)
    creature = Creature(max_hp=hp, monster_id="TOADPOLE")
    spike_spit_dmg = 3
    whirl_dmg = 7
    spiken_amount = 2

    def spike_spit(combat: CombatState) -> None:
        if creature.has_power(PowerId.THORNS):
            creature.apply_power(PowerId.THORNS, -spiken_amount, applier=creature)
        _deal_damage_to_player(combat, creature, spike_spit_dmg, hits=3)

    def whirl(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, whirl_dmg)

    def spiken(combat: CombatState) -> None:
        creature.apply_power(PowerId.THORNS, spiken_amount, applier=creature)

    is_front = slot in {"first", "front"}
    init = ConditionalBranchState("INIT_MOVE")
    init.add_branch(lambda: not is_front, "WHIRL_MOVE")
    init.add_branch(lambda: True, "SPIKEN_MOVE")

    states: dict[str, MonsterState] = {
        "INIT_MOVE": init,
        "SPIKE_SPIT_MOVE": MoveState(
            "SPIKE_SPIT_MOVE",
            spike_spit,
            [multi_attack_intent(spike_spit_dmg, 3)],
            follow_up_id="WHIRL_MOVE",
        ),
        "WHIRL_MOVE": MoveState("WHIRL_MOVE", whirl, [attack_intent(whirl_dmg)], follow_up_id="SPIKEN_MOVE"),
        "SPIKEN_MOVE": MoveState("SPIKEN_MOVE", spiken, [buff_intent()], follow_up_id="SPIKE_SPIT_MOVE"),
    }

    return creature, MonsterAI(states, "INIT_MOVE", rng)


# ========================================================================
# NORMAL ENCOUNTERS
# ========================================================================

# ---- CalcifiedCultist (HP 38-41 / 39-42 asc) ----

def create_calcified_cultist(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(38, 41)
    creature = Creature(max_hp=hp, monster_id="CALCIFIED_CULTIST")
    dark_strike_dmg = 9

    def incantation(combat: CombatState) -> None:
        creature.apply_power(PowerId.RITUAL, 2)

    def dark_strike(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, dark_strike_dmg)

    states: dict[str, MonsterState] = {
        "INCANTATION_MOVE": MoveState(
            "INCANTATION_MOVE",
            incantation,
            [buff_intent()],
            follow_up_id="DARK_STRIKE_MOVE",
        ),
        "DARK_STRIKE_MOVE": MoveState(
            "DARK_STRIKE_MOVE",
            dark_strike,
            [attack_intent(dark_strike_dmg)],
            follow_up_id="DARK_STRIKE_MOVE",
        ),
    }
    return creature, MonsterAI(states, "INCANTATION_MOVE")


# ---- DampCultist (HP 51-53 / 52-54 asc) ----

def create_damp_cultist(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(51, 53)
    creature = Creature(max_hp=hp, monster_id="DAMP_CULTIST")
    dark_strike_dmg = 1

    def incantation(combat: CombatState) -> None:
        creature.apply_power(PowerId.RITUAL, 5)

    def dark_strike(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, dark_strike_dmg)

    states: dict[str, MonsterState] = {
        "INCANTATION_MOVE": MoveState(
            "INCANTATION_MOVE",
            incantation,
            [buff_intent()],
            follow_up_id="DARK_STRIKE_MOVE",
        ),
        "DARK_STRIKE_MOVE": MoveState(
            "DARK_STRIKE_MOVE",
            dark_strike,
            [attack_intent(dark_strike_dmg)],
            follow_up_id="DARK_STRIKE_MOVE",
        ),
    }
    return creature, MonsterAI(states, "INCANTATION_MOVE")


# ---- FossilStalker (HP 51-53 / 54-56 asc) ----

def create_fossil_stalker(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(51, 53)
    creature = Creature(max_hp=hp, monster_id="FOSSIL_STALKER")
    tackle_dmg = 9
    latch_dmg = 12
    lash_dmg = 3

    def tackle(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, tackle_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.FRAIL, 1)

    def latch(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, latch_dmg)

    def lash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, lash_dmg, hits=2)

    rand = RandomBranchState("RAND")
    rand.add_branch("LATCH_MOVE", weight=2.0)
    rand.add_branch("TACKLE_MOVE", weight=2.0)
    rand.add_branch("LASH_MOVE", weight=2.0)

    states: dict[str, MonsterState] = {
        "RAND": rand,
        "TACKLE_MOVE": MoveState(
            "TACKLE_MOVE",
            tackle,
            [attack_intent(tackle_dmg), debuff_intent()],
            follow_up_id="RAND",
        ),
        "LATCH_MOVE": MoveState("LATCH_MOVE", latch, [attack_intent(latch_dmg)], follow_up_id="RAND"),
        "LASH_MOVE": MoveState("LASH_MOVE", lash, [multi_attack_intent(lash_dmg, 2)], follow_up_id="RAND"),
    }

    creature.apply_power(PowerId.SUCK, 3)
    return creature, MonsterAI(states, "LATCH_MOVE")


# ---- GremlinMerc (HP 47-49 / 51-53 asc) + SneakyGremlin + FatGremlin ----

def create_sneaky_gremlin(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(10, 14)
    creature = Creature(max_hp=hp, monster_id="SNEAKY_GREMLIN")
    tackle_dmg = 9

    def spawned(combat: CombatState) -> None:
        pass

    def tackle(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, tackle_dmg)

    states: dict[str, MonsterState] = {
        "SPAWNED_MOVE": MoveState(
            "SPAWNED_MOVE",
            spawned,
            [Intent(IntentType.STUN)],
            follow_up_id="TACKLE_MOVE",
        ),
        "TACKLE_MOVE": MoveState(
            "TACKLE_MOVE",
            tackle,
            [attack_intent(tackle_dmg)],
            follow_up_id="TACKLE_MOVE",
        ),
    }
    return creature, MonsterAI(states, "SPAWNED_MOVE")


def create_fat_gremlin(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(13, 17)
    creature = Creature(max_hp=hp, monster_id="FAT_GREMLIN")

    def spawned(combat: CombatState) -> None:
        pass

    def flee(combat: CombatState) -> None:
        combat.escape_creature(creature)

    states: dict[str, MonsterState] = {
        "SPAWNED_MOVE": MoveState(
            "SPAWNED_MOVE",
            spawned,
            [Intent(IntentType.STUN)],
            follow_up_id="FLEE_MOVE",
        ),
        "FLEE_MOVE": MoveState(
            "FLEE_MOVE",
            flee,
            [Intent(IntentType.ESCAPE)],
            follow_up_id="FLEE_MOVE",
        ),
    }
    return creature, MonsterAI(states, "SPAWNED_MOVE")


def create_gremlin_merc(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(47, 49)
    creature = Creature(max_hp=hp, monster_id="GREMLIN_MERC")
    gimme_dmg = 7
    double_smash_dmg = 6
    hehe_dmg = 8

    def gimme(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, gimme_dmg, hits=2)

    def double_smash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, double_smash_dmg, hits=2)
        combat.apply_power_to(combat.primary_player, PowerId.WEAK, 2)

    def hehe(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, hehe_dmg)
        combat.apply_power_to(creature, PowerId.STRENGTH, 2, applier=creature)

    states: dict[str, MonsterState] = {
        "GIMME_MOVE": MoveState(
            "GIMME_MOVE",
            gimme,
            [multi_attack_intent(gimme_dmg, 2)],
            follow_up_id="DOUBLE_SMASH_MOVE",
        ),
        "DOUBLE_SMASH_MOVE": MoveState(
            "DOUBLE_SMASH_MOVE",
            double_smash,
            [multi_attack_intent(double_smash_dmg, 2), debuff_intent()],
            follow_up_id="HEHE_MOVE",
        ),
        "HEHE_MOVE": MoveState(
            "HEHE_MOVE",
            hehe,
            [attack_intent(hehe_dmg), buff_intent()],
            follow_up_id="GIMME_MOVE",
        ),
    }

    creature.apply_power(PowerId.SURPRISE, 1)
    creature.apply_power(PowerId.THIEVERY, 20)
    return creature, MonsterAI(states, "GIMME_MOVE")


# ---- HauntedShip (HP 63 / 67 asc) ----

def create_haunted_ship(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 63
    creature = Creature(max_hp=hp, monster_id="HAUNTED_SHIP")
    ramming_speed_dmg = 10
    swipe_dmg = 13
    stomp_dmg = 4

    def _odd_round_weight() -> float:
        combat = creature.combat_state
        return 1.0 if combat is None or combat.round_number % 2 != 0 else 0.0

    def _even_round_weight() -> float:
        combat = creature.combat_state
        return 1.0 if combat is not None and combat.round_number % 2 == 0 else 0.0

    def ramming_speed(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, ramming_speed_dmg)
        if combat.is_over:
            return
        combat.add_status_cards_to_discard(combat.primary_player, "WOUND", 2)

    def swipe(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, swipe_dmg)

    def stomp(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, stomp_dmg, hits=3)

    def haunt(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.WEAK, 2, applier=creature)
        combat.apply_power_to(combat.primary_player, PowerId.FRAIL, 2, applier=creature)
        combat.apply_power_to(combat.primary_player, PowerId.VULNERABLE, 2, applier=creature)

    rand = RandomBranchState("RAND")
    rand.add_branch("RAMMING_SPEED_MOVE", MoveRepeatType.CANNOT_REPEAT, weight=_odd_round_weight)
    rand.add_branch("SWIPE_MOVE", MoveRepeatType.CANNOT_REPEAT, weight=_odd_round_weight)
    rand.add_branch("STOMP_MOVE", MoveRepeatType.CANNOT_REPEAT, weight=_odd_round_weight)
    rand.add_branch("HAUNT_MOVE", MoveRepeatType.USE_ONLY_ONCE, weight=_even_round_weight)

    states: dict[str, MonsterState] = {
        "RAND": rand,
        "RAMMING_SPEED_MOVE": MoveState(
            "RAMMING_SPEED_MOVE",
            ramming_speed,
            [attack_intent(ramming_speed_dmg), status_intent()],
            follow_up_id="RAND",
        ),
        "SWIPE_MOVE": MoveState("SWIPE_MOVE", swipe, [attack_intent(swipe_dmg)], follow_up_id="RAND"),
        "STOMP_MOVE": MoveState(
            "STOMP_MOVE",
            stomp,
            [multi_attack_intent(stomp_dmg, 3)],
            follow_up_id="RAND",
        ),
        "HAUNT_MOVE": MoveState("HAUNT_MOVE", haunt, [debuff_intent()], follow_up_id="RAND"),
    }
    return creature, MonsterAI(states, "RAMMING_SPEED_MOVE")


# ---- LivingFog (HP 80 / 82 asc) + GasBomb ----

def create_gas_bomb(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 10
    creature = Creature(max_hp=hp, monster_id="GAS_BOMB")
    explode_dmg = 8

    def explode(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, explode_dmg)
        combat.kill_creature(creature)

    states: dict[str, MonsterState] = {
        "EXPLODE_MOVE": MoveState(
            "EXPLODE_MOVE",
            explode,
            [Intent(IntentType.DEATH_BLOW, damage=explode_dmg)],
            follow_up_id="EXPLODE_MOVE",
        ),
    }
    return creature, MonsterAI(states, "EXPLODE_MOVE")


def create_living_fog(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 80
    creature = Creature(max_hp=hp, monster_id="LIVING_FOG")
    advanced_gas_dmg = 8
    bloat_dmg = 5
    super_gas_blast_dmg = 8
    state = {"bloat_amount": 1}

    def advanced_gas(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, advanced_gas_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.SMOGGY, 1, applier=creature)

    def bloat(combat: CombatState) -> None:
        for _ in range(state["bloat_amount"]):
            bomb, bomb_ai = create_gas_bomb(rng)
            combat.add_enemy(bomb, bomb_ai)
        state["bloat_amount"] = min(state["bloat_amount"] + 1, 5)
        _deal_damage_to_player(combat, creature, bloat_dmg)

    def super_gas_blast(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, super_gas_blast_dmg)

    states: dict[str, MonsterState] = {
        "ADVANCED_GAS_MOVE": MoveState(
            "ADVANCED_GAS_MOVE",
            advanced_gas,
            [attack_intent(advanced_gas_dmg), Intent(IntentType.CARD_DEBUFF)],
            follow_up_id="BLOAT_MOVE",
        ),
        "BLOAT_MOVE": MoveState(
            "BLOAT_MOVE",
            bloat,
            [attack_intent(bloat_dmg), Intent(IntentType.SUMMON)],
            follow_up_id="SUPER_GAS_BLAST_MOVE",
        ),
        "SUPER_GAS_BLAST_MOVE": MoveState(
            "SUPER_GAS_BLAST_MOVE",
            super_gas_blast,
            [attack_intent(super_gas_blast_dmg)],
            follow_up_id="BLOAT_MOVE",
        ),
    }
    return creature, MonsterAI(states, "ADVANCED_GAS_MOVE")


# ---- PunchConstruct (HP 55 / 60 asc) ----

def create_punch_construct(
    rng: Rng,
    *,
    starts_with_strong_punch: bool = False,
    starting_hp_reduction: int = 0,
) -> tuple[Creature, MonsterAI]:
    hp = 55
    creature = Creature(max_hp=hp, monster_id="PUNCH_CONSTRUCT")
    strong_punch_dmg = 14
    fast_punch_dmg = 5
    ready_block = 10

    if starting_hp_reduction > 0:
        creature.current_hp = max(1, creature.current_hp - starting_hp_reduction)
    creature.apply_power(PowerId.ARTIFACT, 1)

    def ready(combat: CombatState) -> None:
        _gain_block(creature, ready_block, combat)

    def strong_punch(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, strong_punch_dmg)

    def fast_punch(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, fast_punch_dmg, hits=2)
        combat.apply_power_to(combat.primary_player, PowerId.WEAK, 1)

    states: dict[str, MonsterState] = {
        "READY_MOVE": MoveState(
            "READY_MOVE",
            ready,
            [defend_intent()],
            follow_up_id="STRONG_PUNCH_MOVE",
        ),
        "STRONG_PUNCH_MOVE": MoveState(
            "STRONG_PUNCH_MOVE",
            strong_punch,
            [attack_intent(strong_punch_dmg)],
            follow_up_id="FAST_PUNCH_MOVE",
        ),
        "FAST_PUNCH_MOVE": MoveState(
            "FAST_PUNCH_MOVE",
            fast_punch,
            [multi_attack_intent(fast_punch_dmg, 2), debuff_intent()],
            follow_up_id="READY_MOVE",
        ),
    }
    initial = "STRONG_PUNCH_MOVE" if starts_with_strong_punch else "READY_MOVE"
    return creature, MonsterAI(states, initial)


# ---- SewerClam (HP 56 / 58 asc) ----

def create_sewer_clam(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 56
    creature = Creature(max_hp=hp, monster_id="SEWER_CLAM")
    jet_dmg = 10
    pressurize_str = 4

    def pressurize(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, pressurize_str, applier=creature)

    def jet(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, jet_dmg)

    states: dict[str, MonsterState] = {
        "PRESSURIZE_MOVE": MoveState(
            "PRESSURIZE_MOVE",
            pressurize,
            [buff_intent()],
            follow_up_id="JET_MOVE",
        ),
        "JET_MOVE": MoveState(
            "JET_MOVE",
            jet,
            [attack_intent(jet_dmg)],
            follow_up_id="PRESSURIZE_MOVE",
        ),
    }
    creature.apply_power(PowerId.PLATING, 8)
    return creature, MonsterAI(states, "JET_MOVE")


# ---- TwoTailedRat (HP 17-21 / 18-22 asc) ----

def create_two_tailed_rat(rng: Rng, starter_move_idx: int = -1) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(17, 21)
    creature = Creature(max_hp=hp, monster_id="TWO_TAILED_RAT")
    scratch_dmg = 8
    disease_bite_dmg = 6
    state = {
        "turns_until_summonable": 2,
        "call_for_backup_count": 0,
    }

    def can_summon(combat: CombatState | None = None) -> bool:
        combat = combat or creature.combat_state
        if combat is None:
            return False
        if state["turns_until_summonable"] > 0:
            return False
        if state["call_for_backup_count"] >= 3:
            return False
        alive_rats = [
            enemy
            for enemy in combat.enemies
            if enemy.monster_id == "TWO_TAILED_RAT" and enemy.is_alive
        ]
        if len(alive_rats) >= 5:
            return False
        for enemy in alive_rats:
            if enemy is creature:
                continue
            ai = combat.enemy_ais.get(enemy.combat_id)
            if ai is not None and ai.current_move.state_id == "CALL_FOR_BACKUP_MOVE":
                return False
        return True

    def _attack_performed() -> None:
        state["turns_until_summonable"] -= 1

    def scratch(combat: CombatState) -> None:
        _attack_performed()
        _deal_damage_to_player(combat, creature, scratch_dmg)

    def disease_bite(combat: CombatState) -> None:
        _attack_performed()
        _deal_damage_to_player(combat, creature, disease_bite_dmg)

    def screech(combat: CombatState) -> None:
        _attack_performed()
        combat.apply_power_to(combat.primary_player, PowerId.FRAIL, 1, applier=creature)

    def call_for_backup(combat: CombatState) -> None:
        if can_summon(combat):
            backup, backup_ai = create_two_tailed_rat(rng)
            combat.add_enemy(backup, backup_ai)
        rat_ais = [
            combat.enemy_ais[enemy.combat_id]
            for enemy in combat.enemies
            if enemy.monster_id == "TWO_TAILED_RAT" and enemy.combat_id in combat.enemy_ais
        ]
        max_count = max(
            getattr(ai, "_two_tailed_rat_state", {}).get("call_for_backup_count", 0) + 1
            for ai in rat_ais
        )
        for ai in rat_ais:
            rat_state = getattr(ai, "_two_tailed_rat_state", None)
            if rat_state is not None:
                rat_state["call_for_backup_count"] = max_count

    rand = RandomBranchState("RAND")
    rand.add_branch(
        "SCRATCH_MOVE",
        MoveRepeatType.CANNOT_REPEAT,
        weight=lambda: 1.0 / 12.0 if can_summon() else 1.0,
    )
    rand.add_branch(
        "DISEASE_BITE_MOVE",
        MoveRepeatType.CANNOT_REPEAT,
        weight=lambda: 1.0 / 12.0 if can_summon() else 1.0,
    )
    rand.add_branch(
        "SCREECH_MOVE",
        MoveRepeatType.CANNOT_REPEAT,
        weight=lambda: 1.0 / 12.0 if can_summon() else 3.0,
    )
    rand.add_branch(
        "CALL_FOR_BACKUP_MOVE",
        MoveRepeatType.USE_ONLY_ONCE,
        weight=lambda: 0.75 if can_summon() else 0.0,
    )

    states: dict[str, MonsterState] = {
        "RAND": rand,
        "SCRATCH_MOVE": MoveState(
            "SCRATCH_MOVE",
            scratch,
            [attack_intent(scratch_dmg)],
            follow_up_id="RAND",
        ),
        "DISEASE_BITE_MOVE": MoveState(
            "DISEASE_BITE_MOVE",
            disease_bite,
            [attack_intent(disease_bite_dmg)],
            follow_up_id="RAND",
        ),
        "SCREECH_MOVE": MoveState(
            "SCREECH_MOVE",
            screech,
            [debuff_intent()],
            follow_up_id="RAND",
        ),
        "CALL_FOR_BACKUP_MOVE": MoveState(
            "CALL_FOR_BACKUP_MOVE",
            call_for_backup,
            [Intent(IntentType.SUMMON)],
            follow_up_id="RAND",
        ),
    }

    starter_map = {
        0: "SCRATCH_MOVE",
        1: "DISEASE_BITE_MOVE",
        2: "SCREECH_MOVE",
    }
    initial = starter_map.get(starter_move_idx, "RAND")
    ai = MonsterAI(states, initial, rng)
    ai._two_tailed_rat_state = state  # noqa: SLF001
    return creature, ai


# ========================================================================
# ELITE ENCOUNTERS
# ========================================================================

# ---- PhantasmalGardener (HP 28-32 / 29-33 asc) ----

def create_phantasmal_gardener(rng: Rng, slot: str = "first") -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(28, 32)
    creature = Creature(max_hp=hp, monster_id="PHANTASMAL_GARDENER")
    bite_dmg = 5
    lash_dmg = 7
    flail_dmg = 1

    def bite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bite_dmg)

    def lash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, lash_dmg)

    def flail(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, flail_dmg, hits=3)

    def enlarge(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 2, applier=creature)

    init = ConditionalBranchState("INIT_MOVE")
    init.add_branch(lambda: slot == "first", "FLAIL_MOVE")
    init.add_branch(lambda: slot == "second", "BITE_MOVE")
    init.add_branch(lambda: slot == "third", "LASH_MOVE")
    init.add_branch(lambda: slot == "fourth", "ENLARGE_MOVE")

    states: dict[str, MonsterState] = {
        "INIT_MOVE": init,
        "BITE_MOVE": MoveState("BITE_MOVE", bite, [attack_intent(bite_dmg)], follow_up_id="LASH_MOVE"),
        "LASH_MOVE": MoveState("LASH_MOVE", lash, [attack_intent(lash_dmg)], follow_up_id="FLAIL_MOVE"),
        "FLAIL_MOVE": MoveState(
            "FLAIL_MOVE",
            flail,
            [multi_attack_intent(flail_dmg, 3)],
            follow_up_id="ENLARGE_MOVE",
        ),
        "ENLARGE_MOVE": MoveState("ENLARGE_MOVE", enlarge, [buff_intent()], follow_up_id="BITE_MOVE"),
    }
    creature.apply_power(PowerId.SKITTISH, 6)
    return creature, MonsterAI(states, "INIT_MOVE", rng)


# ---- SkulkingColony (HP 79 / 84 asc) ----

def create_skulking_colony(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 79
    creature = Creature(max_hp=hp, monster_id="SKULKING_COLONY")
    super_crab_dmg = 6
    zoom_dmg = 16
    smash_dmg = 9
    inertia_block = 10

    def inertia(combat: CombatState) -> None:
        _gain_block(creature, inertia_block, combat)
        creature.apply_power(PowerId.STRENGTH, 3, applier=creature)

    def zoom(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, zoom_dmg)

    def super_crab(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, super_crab_dmg, hits=2)

    def smash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, smash_dmg)
        if combat.is_over:
            return
        combat.add_status_cards_to_discard(combat.primary_player, "DAZED", 4)

    states: dict[str, MonsterState] = {
        "INERTIA_MOVE": MoveState(
            "INERTIA_MOVE",
            inertia,
            [defend_intent(), buff_intent()],
            follow_up_id="SUPER_CRAB_MOVE",
        ),
        "ZOOM_MOVE": MoveState("ZOOM_MOVE", zoom, [attack_intent(zoom_dmg)], follow_up_id="INERTIA_MOVE"),
        "SUPER_CRAB_MOVE": MoveState(
            "SUPER_CRAB_MOVE",
            super_crab,
            [multi_attack_intent(super_crab_dmg, 2)],
            follow_up_id="SMASH_MOVE",
        ),
        "SMASH_MOVE": MoveState(
            "SMASH_MOVE",
            smash,
            [attack_intent(smash_dmg), status_intent()],
            follow_up_id="ZOOM_MOVE",
        ),
    }
    creature.apply_power(PowerId.HARDENED_SHELL, 20)
    return creature, MonsterAI(states, "SMASH_MOVE")


# ---- TerrorEel (HP 140 / 150 asc) ----

def create_terror_eel(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 140
    creature = Creature(max_hp=hp, monster_id="TERROR_EEL")
    crash_dmg = 17
    thrash_dmg = 3

    def crash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, crash_dmg)

    def thrash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, thrash_dmg, hits=3)
        combat.apply_power_to(creature, PowerId.VIGOR, 7, applier=creature)

    def stun(combat: CombatState) -> None:
        pass

    def terror(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.VULNERABLE, 99, applier=creature)

    states: dict[str, MonsterState] = {
        "CRASH_MOVE": MoveState("CRASH_MOVE", crash, [attack_intent(crash_dmg)], follow_up_id="ThrashMove"),
        "ThrashMove": MoveState(
            "ThrashMove",
            thrash,
            [multi_attack_intent(thrash_dmg, 3), buff_intent()],
            follow_up_id="CRASH_MOVE",
        ),
        "STUN_MOVE": MoveState("STUN_MOVE", stun, [Intent(IntentType.STUN)], follow_up_id="TERROR_MOVE"),
        "TERROR_MOVE": MoveState("TERROR_MOVE", terror, [debuff_intent()], follow_up_id="CRASH_MOVE"),
    }
    creature.apply_power(PowerId.SHRIEK, 70)
    return creature, MonsterAI(states, "CRASH_MOVE")


# ========================================================================
# BOSS ENCOUNTERS
# ========================================================================

# ---- WaterfallGiant (HP 250 / 260 asc) ----

def create_waterfall_giant(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 250
    creature = Creature(max_hp=hp, monster_id="WATERFALL_GIANT")
    stomp_dmg = 15
    ram_dmg = 10
    pressure_up_dmg = 13
    pressurize_amount = 15
    base_pressure_gun_dmg = 20
    pressure_gun_increase = 5
    siphon_heal = 15

    _state = {
        "current_pressure_gun_damage": base_pressure_gun_dmg,
        "steam_eruption_damage": 0,
    }

    def _gain_pressure(combat: CombatState, amount: int) -> None:
        combat.apply_power_to(creature, PowerId.STEAM_ERUPTION, amount, applier=creature)

    def pressurize(combat: CombatState) -> None:
        _gain_pressure(combat, pressurize_amount)

    def stomp(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, stomp_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.WEAK, 1)
        _gain_pressure(combat, 3)

    def ram(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, ram_dmg)
        _gain_pressure(combat, 3)

    def siphon(combat: CombatState) -> None:
        creature.heal(siphon_heal * len(combat.combat_player_states))
        _gain_pressure(combat, 3)

    def pressure_gun(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, _state["current_pressure_gun_damage"])
        _state["current_pressure_gun_damage"] += pressure_gun_increase
        _gain_pressure(combat, 3)

    def pressure_up(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, pressure_up_dmg)
        _gain_pressure(combat, 3)

    def about_to_blow(combat: CombatState) -> None:
        _state["steam_eruption_damage"] = creature.get_power_amount(PowerId.STEAM_ERUPTION)
        creature.powers.pop(PowerId.STEAM_ERUPTION, None)

    def explode(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, _state["steam_eruption_damage"])
        combat.kill_creature(creature)

    states: dict[str, MonsterState] = {
        "PRESSURIZE_MOVE": MoveState("PRESSURIZE_MOVE", pressurize, [buff_intent()], follow_up_id="STOMP_MOVE"),
        "STOMP_MOVE": MoveState(
            "STOMP_MOVE",
            stomp,
            [attack_intent(stomp_dmg), debuff_intent(), buff_intent()],
            follow_up_id="RAM_MOVE",
        ),
        "RAM_MOVE": MoveState("RAM_MOVE", ram, [attack_intent(ram_dmg), buff_intent()], follow_up_id="SIPHON_MOVE"),
        "SIPHON_MOVE": MoveState(
            "SIPHON_MOVE",
            siphon,
            [Intent(IntentType.HEAL), buff_intent()],
            follow_up_id="PRESSURE_GUN_MOVE",
        ),
        "PRESSURE_GUN_MOVE": MoveState(
            "PRESSURE_GUN_MOVE",
            pressure_gun,
            [attack_intent(base_pressure_gun_dmg), buff_intent()],
            follow_up_id="PRESSURE_UP_MOVE",
        ),
        "PRESSURE_UP_MOVE": MoveState(
            "PRESSURE_UP_MOVE",
            pressure_up,
            [attack_intent(pressure_up_dmg), buff_intent()],
            follow_up_id="STOMP_MOVE",
        ),
        "ABOUT_TO_BLOW_MOVE": MoveState(
            "ABOUT_TO_BLOW_MOVE",
            about_to_blow,
            [Intent(IntentType.STUN)],
            follow_up_id="EXPLODE_MOVE",
            must_perform_once=True,
        ),
        "EXPLODE_MOVE": MoveState("EXPLODE_MOVE", explode, [Intent(IntentType.DEATH_BLOW)], follow_up_id="EXPLODE_MOVE"),
    }
    return creature, MonsterAI(states, "PRESSURIZE_MOVE")


# ---- SoulFysh (HP 211 / 221 asc) ----

def create_soul_fysh(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 211
    creature = Creature(max_hp=hp, monster_id="SOUL_FYSH")
    de_gas_dmg = 16
    scream_dmg = 11
    gaze_dmg = 7

    def beckon(combat: CombatState) -> None:
        from sts2_env.cards.status import make_beckon

        combat.add_generated_card_to_creature_draw_pile(
            combat.primary_player,
            make_beckon(),
            added_by_player=False,
            random_position=True,
        )
        combat.add_generated_card_to_creature_discard(combat.primary_player, make_beckon(), added_by_player=False)

    def de_gas(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, de_gas_dmg)

    def gaze(combat: CombatState) -> None:
        from sts2_env.cards.status import make_beckon

        _deal_damage_to_player(combat, creature, gaze_dmg)
        if combat.is_over:
            return
        combat.add_generated_card_to_creature_discard(combat.primary_player, make_beckon(), added_by_player=False)

    def fade(combat: CombatState) -> None:
        creature.apply_power(PowerId.INTANGIBLE, 2, applier=creature)

    def scream(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, scream_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.VULNERABLE, 3, applier=creature)

    states: dict[str, MonsterState] = {
        "BECKON_MOVE": MoveState("BECKON_MOVE", beckon, [status_intent()], follow_up_id="DE_GAS_MOVE"),
        "DE_GAS_MOVE": MoveState("DE_GAS_MOVE", de_gas, [attack_intent(de_gas_dmg)], follow_up_id="GAZE_MOVE"),
        "GAZE_MOVE": MoveState(
            "GAZE_MOVE",
            gaze,
            [attack_intent(gaze_dmg), status_intent()],
            follow_up_id="FADE_MOVE",
        ),
        "FADE_MOVE": MoveState("FADE_MOVE", fade, [buff_intent()], follow_up_id="SCREAM_MOVE"),
        "SCREAM_MOVE": MoveState(
            "SCREAM_MOVE",
            scream,
            [attack_intent(scream_dmg), debuff_intent()],
            follow_up_id="BECKON_MOVE",
        ),
    }
    return creature, MonsterAI(states, "BECKON_MOVE")


# ---- LagavulinMatriarch (HP 222 / 233 asc) ----
# C# cycle: SLEEP -> (branch: asleep->SLEEP, else->SLASH) ->
#   SLASH(19) -> DISEMBOWEL(9x2) -> SLASH2(12+12blk) -> SOUL_SIPHON(debuff+buff) -> SLASH...

def create_lagavulin_matriarch(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 222
    creature = Creature(max_hp=hp, monster_id="LAGAVULIN_MATRIARCH")
    slash_dmg = 19
    disembowel_dmg = 9
    slash2_dmg = 12
    slash2_block = 12

    def sleep_move(combat: CombatState) -> None:
        pass

    def slash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, slash_dmg)

    def disembowel(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, disembowel_dmg, hits=2)

    def slash2(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, slash2_dmg)
        _gain_block(creature, slash2_block, combat)

    def soul_siphon(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.STRENGTH, -2, applier=creature)
        combat.apply_power_to(combat.primary_player, PowerId.DEXTERITY, -2, applier=creature)
        creature.apply_power(PowerId.STRENGTH, 2, applier=creature)

    sleep_branch = ConditionalBranchState("SLEEP_BRANCH")
    sleep_branch.add_branch(lambda: creature.has_power(PowerId.ASLEEP), "SLEEP_MOVE")
    sleep_branch.add_branch(lambda: True, "SLASH_MOVE")

    states: dict[str, MonsterState] = {
        "SLEEP_MOVE": MoveState("SLEEP_MOVE", sleep_move, [sleep_intent()], follow_up_id="SLEEP_BRANCH"),
        "SLEEP_BRANCH": sleep_branch,
        "SLASH_MOVE": MoveState("SLASH_MOVE", slash, [attack_intent(slash_dmg)], follow_up_id="DISEMBOWEL_MOVE"),
        "DISEMBOWEL_MOVE": MoveState(
            "DISEMBOWEL_MOVE",
            disembowel,
            [multi_attack_intent(disembowel_dmg, 2)],
            follow_up_id="SLASH2_MOVE",
        ),
        "SLASH2_MOVE": MoveState(
            "SLASH2_MOVE",
            slash2,
            [attack_intent(slash2_dmg), defend_intent()],
            follow_up_id="SOUL_SIPHON_MOVE",
        ),
        "SOUL_SIPHON_MOVE": MoveState(
            "SOUL_SIPHON_MOVE",
            soul_siphon,
            [debuff_intent(), buff_intent()],
            follow_up_id="SLASH_MOVE",
        ),
    }

    creature.apply_power(PowerId.PLATING, 12)
    creature.apply_power(PowerId.ASLEEP, 3)
    return creature, MonsterAI(states, "SLEEP_MOVE")
