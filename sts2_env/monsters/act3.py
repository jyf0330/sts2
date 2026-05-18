"""Act 3 (Glory) monsters: weak, normal, elite, boss.

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
from sts2_env.cards.status import make_burn, make_dazed, make_slimed

if TYPE_CHECKING:
    from sts2_env.core.combat import CombatState


# ---- Helpers ----

def _deal_damage_to_player(combat: CombatState, creature: Creature, base_dmg: int, hits: int = 1) -> None:
    for _ in range(hits):
        if combat.primary_player.is_dead:
            break
        dmg = calculate_damage(base_dmg, creature, combat.primary_player, ValueProp.MOVE, combat)
        apply_damage(combat.primary_player, dmg, ValueProp.MOVE, combat, creature)


def _gain_block(creature: Creature, amount: int) -> None:
    creature.gain_block(amount)


# ========================================================================
# WEAK ENCOUNTERS
# ========================================================================

# ---- DevotedSculptor (HP 162 / 172 asc) ----

def create_devoted_sculptor(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 162
    creature = Creature(max_hp=hp, monster_id="DEVOTED_SCULPTOR")
    savage_dmg = 12

    def forbidden_incantation(combat: CombatState) -> None:
        creature.apply_power(PowerId.RITUAL, 9)

    def savage(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, savage_dmg)

    states: dict[str, MonsterState] = {
        "FORBIDDEN_INCANTATION_MOVE": MoveState("FORBIDDEN_INCANTATION_MOVE", forbidden_incantation, [buff_intent()], follow_up_id="SAVAGE_MOVE"),
        "SAVAGE_MOVE": MoveState("SAVAGE_MOVE", savage, [attack_intent(savage_dmg)], follow_up_id="SAVAGE_MOVE"),
    }
    return creature, MonsterAI(states, "FORBIDDEN_INCANTATION_MOVE")


# ---- ScrollOfBiting (HP 24-26 / 26-28 asc) ----

def create_scroll_of_biting(rng: Rng, starter_move_idx: int = 0) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(31, 38)
    creature = Creature(max_hp=hp, monster_id="SCROLL_OF_BITING")
    chomp_dmg = 14
    chew_dmg = 5

    def chomp(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, chomp_dmg)

    def chew(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, chew_dmg, hits=2)

    def more_teeth(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 2, applier=creature)

    rand = RandomBranchState("rand")
    rand.add_branch("CHOMP", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("CHEW", weight=2.0)

    states: dict[str, MonsterState] = {
        "CHOMP": MoveState("CHOMP", chomp, [attack_intent(chomp_dmg)], follow_up_id="MORE_TEETH"),
        "CHEW": MoveState("CHEW", chew, [multi_attack_intent(chew_dmg, 2)], follow_up_id="rand"),
        "MORE_TEETH": MoveState("MORE_TEETH", more_teeth, [buff_intent()], follow_up_id="CHEW"),
        "rand": rand,
    }
    initial = ("CHOMP", "CHEW", "MORE_TEETH")[starter_move_idx % 3]
    creature.apply_power(PowerId.PAPER_CUTS, 2)
    return creature, MonsterAI(states, initial, rng)


# ---- TurretOperator (HP 28-30 / 30-32 asc) ----

def create_turret_operator(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 41
    creature = Creature(max_hp=hp, monster_id="TURRET_OPERATOR")
    fire_dmg = 3

    def unload(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, fire_dmg, hits=5)

    def reload(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 1, applier=creature)

    states: dict[str, MonsterState] = {
        "UNLOAD_MOVE_1": MoveState("UNLOAD_MOVE_1", unload, [multi_attack_intent(fire_dmg, 5)], follow_up_id="UNLOAD_MOVE_2"),
        "UNLOAD_MOVE_2": MoveState("UNLOAD_MOVE_2", unload, [multi_attack_intent(fire_dmg, 5)], follow_up_id="RELOAD_MOVE"),
        "RELOAD_MOVE": MoveState("RELOAD_MOVE", reload, [buff_intent()], follow_up_id="UNLOAD_MOVE_1"),
    }
    return creature, MonsterAI(states, "UNLOAD_MOVE_1")


# ========================================================================
# NORMAL ENCOUNTERS
# ========================================================================

# ---- Axebot (HP 40-44 / 42-46 asc) ----

def create_axebot(
    rng: Rng,
    start_with_boot_up: bool = False,
    stock_amount: int | None = None,
) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(40, 44)
    creature = Creature(max_hp=hp, monster_id="AXEBOT")
    one_two_dmg = 5
    hammer_uppercut_dmg = 8
    boot_up_block = 10

    def boot_up(combat: CombatState) -> None:
        _gain_block(creature, boot_up_block)
        creature.apply_power(PowerId.STRENGTH, 1)

    def one_two(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, one_two_dmg, hits=2)

    def sharpen(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 4)

    def hammer_uppercut(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, hammer_uppercut_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.WEAK, 1)
        combat.apply_power_to(combat.primary_player, PowerId.FRAIL, 1)

    rand = RandomBranchState("RAND_MOVE")
    rand.add_branch("ONE_TWO_MOVE", MoveRepeatType.CAN_REPEAT_FOREVER, weight=2.0)
    rand.add_branch("SHARPEN_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("HAMMER_UPPERCUT_MOVE", MoveRepeatType.CAN_REPEAT_FOREVER, weight=2.0)

    states: dict[str, MonsterState] = {
        "RAND_MOVE": rand,
        "BOOT_UP_MOVE": MoveState("BOOT_UP_MOVE", boot_up, [defend_intent(), buff_intent()], follow_up_id="RAND_MOVE"),
        "ONE_TWO_MOVE": MoveState("ONE_TWO_MOVE", one_two, [multi_attack_intent(one_two_dmg, 2)], follow_up_id="RAND_MOVE"),
        "SHARPEN_MOVE": MoveState("SHARPEN_MOVE", sharpen, [buff_intent()], follow_up_id="RAND_MOVE"),
        "HAMMER_UPPERCUT_MOVE": MoveState("HAMMER_UPPERCUT_MOVE", hammer_uppercut, [attack_intent(hammer_uppercut_dmg), debuff_intent()], follow_up_id="RAND_MOVE"),
    }

    if stock_amount is None:
        creature.apply_power(PowerId.STOCK, 2)
    elif stock_amount > 0:
        creature.apply_power(PowerId.STOCK, stock_amount)

    initial = "BOOT_UP_MOVE" if start_with_boot_up or stock_amount is not None else "RAND_MOVE"
    return creature, MonsterAI(states, initial, rng)


# ---- Fabricator (HP 150 / 155 asc) + bots ----

def create_zapbot(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(23, 28)
    creature = Creature(max_hp=hp, monster_id="ZAPBOT")
    zap_dmg = 14

    def zap(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, zap_dmg)

    states: dict[str, MonsterState] = {
        "ZAP": MoveState("ZAP", zap, [attack_intent(zap_dmg)], follow_up_id="ZAP"),
    }
    creature.apply_power(PowerId.HIGH_VOLTAGE, 2)
    creature.apply_power(PowerId.MINION, 1)
    return creature, MonsterAI(states, "ZAP")


def create_stabbot(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(23, 28)
    creature = Creature(max_hp=hp, monster_id="STABBOT")
    stab_dmg = 11

    def stab(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, stab_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.FRAIL, 1, applier=creature)

    states: dict[str, MonsterState] = {
        "STAB_MOVE": MoveState("STAB_MOVE", stab, [attack_intent(stab_dmg), debuff_intent()], follow_up_id="STAB_MOVE"),
    }
    creature.apply_power(PowerId.MINION, 1)
    return creature, MonsterAI(states, "STAB_MOVE")


def create_guardbot(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(21, 25)
    creature = Creature(max_hp=hp, monster_id="GUARDBOT")

    def guard(combat: CombatState) -> None:
        # Give block to all Fabricators
        for enemy in combat.alive_enemies:
            if enemy.monster_id == "FABRICATOR":
                _gain_block(enemy, 15)

    states: dict[str, MonsterState] = {
        "GUARD_MOVE": MoveState("GUARD_MOVE", guard, [defend_intent()], follow_up_id="GUARD_MOVE"),
    }
    creature.apply_power(PowerId.MINION, 1)
    return creature, MonsterAI(states, "GUARD_MOVE")


def create_noisebot(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(23, 28)
    creature = Creature(max_hp=hp, monster_id="NOISEBOT")

    def noise(combat: CombatState) -> None:
        combat.move_card_to_creature_discard(combat.primary_player, make_dazed())
        combat.insert_card_into_creature_draw_pile(combat.primary_player, make_dazed(), random_position=True)

    states: dict[str, MonsterState] = {
        "NOISE_MOVE": MoveState("NOISE_MOVE", noise, [status_intent()], follow_up_id="NOISE_MOVE"),
    }
    creature.apply_power(PowerId.MINION, 1)
    return creature, MonsterAI(states, "NOISE_MOVE")


def create_fabricator(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 150
    creature = Creature(max_hp=hp, monster_id="FABRICATOR")
    fabricating_strike_dmg = 18
    disintegrate_dmg = 11

    _state = {"last_aggro": None, "last_defense": None}

    aggro_creators = [create_zapbot, create_stabbot]
    defense_creators = [create_guardbot, create_noisebot]

    def _spawn_aggro(combat: CombatState) -> None:
        idx = 0 if _state["last_aggro"] == 1 else (1 if _state["last_aggro"] == 0 else rng.next_int(0, 1))
        _state["last_aggro"] = idx
        bot, bot_ai = aggro_creators[idx](rng)
        combat.add_enemy(bot, bot_ai)

    def _spawn_defense(combat: CombatState) -> None:
        idx = 0 if _state["last_defense"] == 1 else (1 if _state["last_defense"] == 0 else rng.next_int(0, 1))
        _state["last_defense"] = idx
        bot, bot_ai = defense_creators[idx](rng)
        combat.add_enemy(bot, bot_ai)

    def fabricate(combat: CombatState) -> None:
        _spawn_defense(combat)
        _spawn_aggro(combat)

    def fabricating_strike(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, fabricating_strike_dmg)
        _spawn_aggro(combat)

    def disintegrate(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, disintegrate_dmg)

    def _can_fabricate() -> bool:
        combat = creature.combat_state
        if combat is None:
            return True
        alive_teammates = [
            enemy for enemy in combat.alive_enemies
            if enemy is not creature and enemy.side == creature.side
        ]
        return len(alive_teammates) < 4

    fab_branch = ConditionalBranchState("fabricateBranch")
    fab_branch.add_branch(_can_fabricate, "RAND")
    fab_branch.add_branch(lambda: True, "DISINTEGRATE_MOVE")

    fab_rand = RandomBranchState("RAND")
    fab_rand.add_branch("FABRICATE_MOVE")
    fab_rand.add_branch("FABRICATING_STRIKE_MOVE")

    states: dict[str, MonsterState] = {
        "fabricateBranch": fab_branch,
        "RAND": fab_rand,
        "FABRICATE_MOVE": MoveState("FABRICATE_MOVE", fabricate, [Intent(IntentType.SUMMON)], follow_up_id="fabricateBranch"),
        "FABRICATING_STRIKE_MOVE": MoveState("FABRICATING_STRIKE_MOVE", fabricating_strike, [attack_intent(fabricating_strike_dmg), Intent(IntentType.SUMMON)], follow_up_id="fabricateBranch"),
        "DISINTEGRATE_MOVE": MoveState("DISINTEGRATE_MOVE", disintegrate, [attack_intent(disintegrate_dmg)], follow_up_id="fabricateBranch"),
    }
    return creature, MonsterAI(states, "fabricateBranch", rng)


# ---- FrogKnight (HP 191 / 199 asc) ----

def create_frog_knight(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 191
    creature = Creature(max_hp=hp, monster_id="FROG_KNIGHT")
    strike_down_evil_dmg = 21
    tongue_lash_dmg = 13
    beetle_charge_dmg = 35

    _state = {"beetle_charged": False}

    def tongue_lash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, tongue_lash_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.FRAIL, 2)

    def strike_down_evil(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, strike_down_evil_dmg)

    def for_the_queen(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 5)

    def beetle_charge(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, beetle_charge_dmg)
        _state["beetle_charged"] = True

    # After for_the_queen, check HP for beetle charge
    charge_check = ConditionalBranchState("HALF_HEALTH")
    charge_check.add_branch(
        lambda: not _state["beetle_charged"] and creature.current_hp < creature.max_hp // 2,
        "BEETLE_CHARGE"
    )
    charge_check.add_branch(lambda: True, "TONGUE_LASH")

    states: dict[str, MonsterState] = {
        "TONGUE_LASH": MoveState("TONGUE_LASH", tongue_lash, [attack_intent(tongue_lash_dmg), debuff_intent()], follow_up_id="STRIKE_DOWN_EVIL"),
        "STRIKE_DOWN_EVIL": MoveState("STRIKE_DOWN_EVIL", strike_down_evil, [attack_intent(strike_down_evil_dmg)], follow_up_id="FOR_THE_QUEEN"),
        "FOR_THE_QUEEN": MoveState("FOR_THE_QUEEN", for_the_queen, [buff_intent()], follow_up_id="HALF_HEALTH"),
        "HALF_HEALTH": charge_check,
        "BEETLE_CHARGE": MoveState("BEETLE_CHARGE", beetle_charge, [attack_intent(beetle_charge_dmg)], follow_up_id="TONGUE_LASH"),
    }

    creature.apply_power(PowerId.PLATING, 15)
    return creature, MonsterAI(states, "TONGUE_LASH")


# ---- GlobeHead (HP 148 / 158 asc) ----

def create_globe_head(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 148
    creature = Creature(max_hp=hp, monster_id="GLOBE_HEAD")
    shocking_slap_dmg = 13
    thunder_strike_dmg = 6
    galvanic_burst_dmg = 16

    def shocking_slap(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, shocking_slap_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.FRAIL, 2)

    def thunder_strike(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, thunder_strike_dmg, hits=3)

    def galvanic_burst(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, galvanic_burst_dmg)
        creature.apply_power(PowerId.STRENGTH, 2)

    states: dict[str, MonsterState] = {
        "SHOCKING_SLAP": MoveState("SHOCKING_SLAP", shocking_slap, [attack_intent(shocking_slap_dmg), debuff_intent()], follow_up_id="THUNDER_STRIKE"),
        "THUNDER_STRIKE": MoveState("THUNDER_STRIKE", thunder_strike, [multi_attack_intent(thunder_strike_dmg, 3)], follow_up_id="GALVANIC_BURST"),
        "GALVANIC_BURST": MoveState("GALVANIC_BURST", galvanic_burst, [attack_intent(galvanic_burst_dmg), buff_intent()], follow_up_id="SHOCKING_SLAP"),
    }

    creature.apply_power(PowerId.GALVANIC, 6)
    return creature, MonsterAI(states, "SHOCKING_SLAP")


# ---- OwlMagistrate (HP 82 / 86 asc) ----

def create_owl_magistrate(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 234
    creature = Creature(max_hp=hp, monster_id="OWL_MAGISTRATE")
    scrutiny_dmg = 16
    peck_assault_dmg = 4
    verdict_dmg = 33

    def magistrate_scrutiny(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, scrutiny_dmg)

    def peck_assault(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, peck_assault_dmg, hits=6)

    def judicial_flight(combat: CombatState) -> None:
        creature.apply_power(PowerId.SOAR, 1, applier=creature)

    def verdict(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, verdict_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.VULNERABLE, 4, applier=creature)
        creature.powers.pop(PowerId.SOAR, None)

    states: dict[str, MonsterState] = {
        "MAGISTRATE_SCRUTINY": MoveState("MAGISTRATE_SCRUTINY", magistrate_scrutiny, [attack_intent(scrutiny_dmg)], follow_up_id="PECK_ASSAULT"),
        "PECK_ASSAULT": MoveState("PECK_ASSAULT", peck_assault, [multi_attack_intent(peck_assault_dmg, 6)], follow_up_id="JUDICIAL_FLIGHT"),
        "JUDICIAL_FLIGHT": MoveState("JUDICIAL_FLIGHT", judicial_flight, [buff_intent()], follow_up_id="VERDICT"),
        "VERDICT": MoveState("VERDICT", verdict, [attack_intent(verdict_dmg), debuff_intent()], follow_up_id="MAGISTRATE_SCRUTINY"),
    }
    return creature, MonsterAI(states, "MAGISTRATE_SCRUTINY")


# ---- SlimedBerserker (HP 60-65 / 64-69 asc) ----

def create_slimed_berserker(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 266
    creature = Creature(max_hp=hp, monster_id="SLIMED_BERSERKER")
    pummeling_dmg = 4
    smother_dmg = 30

    def vomit_ichor(combat: CombatState) -> None:
        for _ in range(10):
            combat.move_card_to_creature_discard(combat.primary_player, make_slimed())

    def furious_pummeling(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, pummeling_dmg, hits=4)

    def leeching_hug(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.WEAK, 3, applier=creature)
        creature.apply_power(PowerId.STRENGTH, 3)

    def smother(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, smother_dmg)

    states: dict[str, MonsterState] = {
        "VOMIT_ICHOR_MOVE": MoveState("VOMIT_ICHOR_MOVE", vomit_ichor, [status_intent()], follow_up_id="FURIOUS_PUMMELING_MOVE"),
        "FURIOUS_PUMMELING_MOVE": MoveState("FURIOUS_PUMMELING_MOVE", furious_pummeling, [multi_attack_intent(pummeling_dmg, 4)], follow_up_id="LEECHING_HUG_MOVE"),
        "LEECHING_HUG_MOVE": MoveState("LEECHING_HUG_MOVE", leeching_hug, [debuff_intent(), buff_intent()], follow_up_id="SMOTHER_MOVE"),
        "SMOTHER_MOVE": MoveState("SMOTHER_MOVE", smother, [attack_intent(smother_dmg)], follow_up_id="VOMIT_ICHOR_MOVE"),
    }
    return creature, MonsterAI(states, "VOMIT_ICHOR_MOVE")


# ---- TheLost + TheForgotten ----

def create_the_lost(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 93
    creature = Creature(max_hp=hp, monster_id="THE_LOST")
    eye_lasers_dmg = 4

    def debilitating_smog(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.STRENGTH, -2, applier=creature)
        creature.apply_power(PowerId.STRENGTH, 2, applier=creature)

    def eye_lasers(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, eye_lasers_dmg, hits=2)

    states: dict[str, MonsterState] = {
        "DEBILITATING_SMOG": MoveState("DEBILITATING_SMOG", debilitating_smog, [debuff_intent(), buff_intent()], follow_up_id="EYE_LASERS"),
        "EYE_LASERS": MoveState("EYE_LASERS", eye_lasers, [multi_attack_intent(eye_lasers_dmg, 2)], follow_up_id="DEBILITATING_SMOG"),
    }
    creature.apply_power(PowerId.POSSESS_STRENGTH, 1)
    return creature, MonsterAI(states, "DEBILITATING_SMOG")


def create_the_forgotten(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 106
    creature = Creature(max_hp=hp, monster_id="THE_FORGOTTEN")
    dread_dmg = 15

    def miasma(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.DEXTERITY, -2, applier=creature)
        _gain_block(creature, 8)
        creature.apply_power(PowerId.DEXTERITY, 2, applier=creature)

    def dread(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, dread_dmg)

    states: dict[str, MonsterState] = {
        "MIASMA": MoveState("MIASMA", miasma, [debuff_intent(), defend_intent(), buff_intent()], follow_up_id="DREAD"),
        "DREAD": MoveState("DREAD", dread, [attack_intent(dread_dmg)], follow_up_id="MIASMA"),
    }
    creature.apply_power(PowerId.POSSESS_SPEED, 1)
    return creature, MonsterAI(states, "MIASMA")


# ---- ConstructMenagerie ----


# ========================================================================
# ELITE ENCOUNTERS
# ========================================================================

# ---- Knights (FlailKnight, MagiKnight, SpectralKnight) ----

def create_flail_knight(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 101
    creature = Creature(max_hp=hp, monster_id="FLAIL_KNIGHT")
    flail_dmg = 9
    ram_dmg = 15

    def war_chant(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 3)

    def flail(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, flail_dmg, hits=2)

    def ram(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, ram_dmg)

    rand = RandomBranchState("RAND")
    rand.add_branch("WAR_CHANT", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("FLAIL_MOVE", MoveRepeatType.CAN_REPEAT_FOREVER, weight=2.0)
    rand.add_branch("RAM_MOVE", MoveRepeatType.CAN_REPEAT_FOREVER, weight=2.0)

    states: dict[str, MonsterState] = {
        "RAND": rand,
        "WAR_CHANT": MoveState("WAR_CHANT", war_chant, [buff_intent()], follow_up_id="RAND"),
        "FLAIL_MOVE": MoveState("FLAIL_MOVE", flail, [multi_attack_intent(flail_dmg, 2)], follow_up_id="RAND"),
        "RAM_MOVE": MoveState("RAM_MOVE", ram, [attack_intent(ram_dmg)], follow_up_id="RAND"),
    }
    return creature, MonsterAI(states, "RAM_MOVE")


# ---- MysteriousKnight (HP 101, event combat) ----
# Identical state machine to FlailKnight, but starts with Str+6 and Plating(6).

def create_mysterious_knight(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 101
    creature = Creature(max_hp=hp, monster_id="MYSTERIOUS_KNIGHT")
    flail_dmg = 9
    ram_dmg = 15

    def war_chant(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 3)

    def flail(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, flail_dmg, hits=2)

    def ram(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, ram_dmg)

    rand = RandomBranchState("RAND")
    rand.add_branch("WAR_CHANT", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("FLAIL_MOVE", MoveRepeatType.CAN_REPEAT_FOREVER, weight=2.0)
    rand.add_branch("RAM_MOVE", MoveRepeatType.CAN_REPEAT_FOREVER, weight=2.0)

    states: dict[str, MonsterState] = {
        "RAND": rand,
        "WAR_CHANT": MoveState("WAR_CHANT", war_chant, [buff_intent()], follow_up_id="RAND"),
        "FLAIL_MOVE": MoveState("FLAIL_MOVE", flail, [multi_attack_intent(flail_dmg, 2)], follow_up_id="RAND"),
        "RAM_MOVE": MoveState("RAM_MOVE", ram, [attack_intent(ram_dmg)], follow_up_id="RAND"),
    }

    # AfterAddedToRoom: Strength+6, Plating(6) on top of FlailKnight's base
    creature.apply_power(PowerId.STRENGTH, 6)
    creature.apply_power(PowerId.PLATING, 6)
    return creature, MonsterAI(states, "RAM_MOVE")


# ---- LivingShield (HP 55) ----
# Moves: SHIELD_SLAM(6) while allies alive, SMASH(16, Str+3) when alone.
# Conditional branch checks ally count.
# AfterAddedToRoom: Rampart(25)

def create_living_shield(rng: Rng, get_ally_count=None) -> tuple[Creature, MonsterAI]:
    hp = 55
    creature = Creature(max_hp=hp, monster_id="LIVING_SHIELD")
    shield_slam_dmg = 6
    smash_dmg = 16
    enrage_str = 3

    def shield_slam(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, shield_slam_dmg)

    def smash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, smash_dmg)
        creature.apply_power(PowerId.STRENGTH, enrage_str)

    # Default ally count checker: count alive teammates excluding self
    def _default_ally_count() -> int:
        combat = creature.combat_state
        if combat is None:
            return 0
        return len(combat.get_teammates_of(creature))

    ally_count_fn = get_ally_count or _default_ally_count

    # Conditional: if allies alive -> SHIELD_SLAM, else -> SMASH (self loop)
    shield_slam_branch = ConditionalBranchState("SHIELD_SLAM_BRANCH")
    shield_slam_branch.add_branch(lambda: ally_count_fn() > 0, "SHIELD_SLAM_MOVE")
    shield_slam_branch.add_branch(lambda: ally_count_fn() == 0, "SMASH_MOVE")

    states: dict[str, MonsterState] = {
        "SHIELD_SLAM_BRANCH": shield_slam_branch,
        "SHIELD_SLAM_MOVE": MoveState("SHIELD_SLAM_MOVE", shield_slam, [attack_intent(shield_slam_dmg)], follow_up_id="SHIELD_SLAM_BRANCH"),
        "SMASH_MOVE": MoveState("SMASH_MOVE", smash, [attack_intent(smash_dmg), buff_intent()], follow_up_id="SMASH_MOVE"),
    }

    creature.apply_power(PowerId.RAMPART, 25)
    return creature, MonsterAI(states, "SHIELD_SLAM_MOVE")


def create_magi_knight(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 82
    creature = Creature(max_hp=hp, monster_id="MAGI_KNIGHT")
    power_shield_dmg = 6
    power_shield_block = 5
    spear_dmg = 10
    bomb_dmg = 35

    def power_shield(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, power_shield_dmg)
        _gain_block(creature, power_shield_block)

    def dampen(combat: CombatState) -> None:
        power = combat.primary_player.powers.get(PowerId.DAMPEN)
        if power is not None:
            add_caster = getattr(power, "add_caster", None)
            if callable(add_caster):
                add_caster(creature)
            return
        combat.apply_power_to(combat.primary_player, PowerId.DAMPEN, 1, applier=creature)
        power = combat.primary_player.powers.get(PowerId.DAMPEN)
        if power is not None:
            add_caster = getattr(power, "add_caster", None)
            if callable(add_caster):
                add_caster(creature)

    def spear(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, spear_dmg)

    def prep(combat: CombatState) -> None:
        _gain_block(creature, power_shield_block)

    def magic_bomb(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bomb_dmg)

    states: dict[str, MonsterState] = {
        "FIRST_POWER_SHIELD_MOVE": MoveState("FIRST_POWER_SHIELD_MOVE", power_shield, [attack_intent(power_shield_dmg), defend_intent()], follow_up_id="DAMPEN_MOVE"),
        "DAMPEN_MOVE": MoveState("DAMPEN_MOVE", dampen, [debuff_intent()], follow_up_id="RAM_MOVE"),
        "RAM_MOVE": MoveState("RAM_MOVE", spear, [attack_intent(spear_dmg)], follow_up_id="PREP_MOVE"),
        "PREP_MOVE": MoveState("PREP_MOVE", prep, [defend_intent()], follow_up_id="MAGIC_BOMB"),
        "MAGIC_BOMB": MoveState("MAGIC_BOMB", magic_bomb, [attack_intent(bomb_dmg)], follow_up_id="RAM_MOVE"),
    }
    return creature, MonsterAI(states, "FIRST_POWER_SHIELD_MOVE")


def create_spectral_knight(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 93
    creature = Creature(max_hp=hp, monster_id="SPECTRAL_KNIGHT")
    soul_slash_dmg = 15
    soul_flame_dmg = 3

    def hex_player(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.HEX, 2, applier=creature)

    def soul_slash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, soul_slash_dmg)

    def soul_flame(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, soul_flame_dmg, hits=3)

    rand = RandomBranchState("RAND")
    rand.add_branch("SOUL_SLASH", weight=2.0)
    rand.add_branch("SOUL_FLAME", MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        "HEX": MoveState("HEX", hex_player, [debuff_intent()], follow_up_id="SOUL_SLASH"),
        "RAND": rand,
        "SOUL_SLASH": MoveState("SOUL_SLASH", soul_slash, [attack_intent(soul_slash_dmg)], follow_up_id="RAND"),
        "SOUL_FLAME": MoveState("SOUL_FLAME", soul_flame, [multi_attack_intent(soul_flame_dmg, 3)], follow_up_id="RAND"),
    }
    return creature, MonsterAI(states, "HEX")


# ---- MechaKnight (HP 155 / 165 asc) ----

def create_mecha_knight(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 300
    creature = Creature(max_hp=hp, monster_id="MECHA_KNIGHT")
    charge_dmg = 25
    heavy_cleave_dmg = 35
    windup_block = 15

    def charge(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, charge_dmg)

    def flamethrower(combat: CombatState) -> None:
        for _ in range(4):
            combat.move_card_to_creature_hand(combat.primary_player, make_burn())

    def windup(combat: CombatState) -> None:
        _gain_block(creature, windup_block)
        creature.apply_power(PowerId.STRENGTH, 5)

    def heavy_cleave(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, heavy_cleave_dmg)

    states: dict[str, MonsterState] = {
        "CHARGE_MOVE": MoveState("CHARGE_MOVE", charge, [attack_intent(charge_dmg)], follow_up_id="FLAMETHROWER_MOVE"),
        "FLAMETHROWER_MOVE": MoveState("FLAMETHROWER_MOVE", flamethrower, [status_intent()], follow_up_id="WINDUP_MOVE"),
        "WINDUP_MOVE": MoveState("WINDUP_MOVE", windup, [defend_intent(), buff_intent()], follow_up_id="HEAVY_CLEAVE_MOVE"),
        "HEAVY_CLEAVE_MOVE": MoveState("HEAVY_CLEAVE_MOVE", heavy_cleave, [attack_intent(heavy_cleave_dmg)], follow_up_id="FLAMETHROWER_MOVE"),
    }
    creature.apply_power(PowerId.ARTIFACT, 3)
    return creature, MonsterAI(states, "CHARGE_MOVE")


# ---- SoulNexus (HP 155 / 165 asc) + Osty ----

def create_osty(rng: Rng) -> tuple[Creature, MonsterAI]:
    creature = Creature(max_hp=1, monster_id="OSTY")

    def nothing(combat: CombatState) -> None:
        pass

    states: dict[str, MonsterState] = {
        "NOTHING_MOVE": MoveState("NOTHING_MOVE", nothing, [Intent(IntentType.UNKNOWN)], follow_up_id="NOTHING_MOVE"),
    }
    return creature, MonsterAI(states, "NOTHING_MOVE")


def create_soul_nexus(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 234
    creature = Creature(max_hp=hp, monster_id="SOUL_NEXUS")
    soul_burn_dmg = 29
    maelstrom_dmg = 6
    drain_life_dmg = 18

    def soul_burn(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, soul_burn_dmg)

    def maelstrom(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, maelstrom_dmg, hits=4)

    def drain_life(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, drain_life_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.VULNERABLE, 2, applier=creature)
        combat.apply_power_to(combat.primary_player, PowerId.WEAK, 2, applier=creature)

    rand = RandomBranchState("RAND")
    rand.add_branch("SOUL_BURN_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("MAELSTROM_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("DRAIN_LIFE_MOVE", MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        "RAND": rand,
        "SOUL_BURN_MOVE": MoveState("SOUL_BURN_MOVE", soul_burn, [attack_intent(soul_burn_dmg)], follow_up_id="RAND"),
        "MAELSTROM_MOVE": MoveState("MAELSTROM_MOVE", maelstrom, [multi_attack_intent(maelstrom_dmg, 4)], follow_up_id="RAND"),
        "DRAIN_LIFE_MOVE": MoveState("DRAIN_LIFE_MOVE", drain_life, [attack_intent(drain_life_dmg), strong_debuff_intent()], follow_up_id="RAND"),
    }
    return creature, MonsterAI(states, "SOUL_BURN_MOVE")


# ========================================================================
# BOSS ENCOUNTERS
# ========================================================================

# ---- Door + Doormaker ----

def create_door(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 155
    creature = Creature(max_hp=hp, monster_id="DOOR")
    dramatic_open_dmg = 25
    enforce_dmg = 20
    door_slam_dmg = 15

    def dramatic_open(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, dramatic_open_dmg)

    def enforce(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, enforce_dmg)
        creature.apply_power(PowerId.STRENGTH, 3)

    def door_slam(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, door_slam_dmg, hits=2)

    def dead_move(combat: CombatState) -> None:
        pass

    states: dict[str, MonsterState] = {
        "DRAMATIC_OPEN_MOVE": MoveState("DRAMATIC_OPEN_MOVE", dramatic_open, [attack_intent(dramatic_open_dmg)], follow_up_id="DOOR_SLAM_MOVE"),
        "DOOR_SLAM_MOVE": MoveState("DOOR_SLAM_MOVE", door_slam, [multi_attack_intent(door_slam_dmg, 2)], follow_up_id="ENFORCE_MOVE"),
        "ENFORCE_MOVE": MoveState("ENFORCE_MOVE", enforce, [attack_intent(enforce_dmg), buff_intent()], follow_up_id="DRAMATIC_OPEN_MOVE"),
        "DEAD_MOVE": MoveState("DEAD_MOVE", dead_move, [Intent(IntentType.UNKNOWN)], follow_up_id="DEAD_MOVE"),
    }

    creature.apply_power(PowerId.DOOR_REVIVAL, 1)
    return creature, MonsterAI(states, "DRAMATIC_OPEN_MOVE")


def create_doormaker(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 489
    creature = Creature(max_hp=hp, monster_id="DOORMAKER")
    laser_beam_dmg = 31
    get_back_in_dmg = 40

    def what_is_it(combat: CombatState) -> None:
        pass

    def beam(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, laser_beam_dmg)

    def get_back_in(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, get_back_in_dmg)
        creature.apply_power(PowerId.STRENGTH, 5)
        combat.revive_door()
        combat.escape_creature(creature)

    states: dict[str, MonsterState] = {
        "WHAT_IS_IT_MOVE": MoveState("WHAT_IS_IT_MOVE", what_is_it, [Intent(IntentType.STUN)], follow_up_id="BEAM_MOVE"),
        "BEAM_MOVE": MoveState("BEAM_MOVE", beam, [attack_intent(laser_beam_dmg)], follow_up_id="GET_BACK_IN_MOVE"),
        "GET_BACK_IN_MOVE": MoveState("GET_BACK_IN_MOVE", get_back_in, [attack_intent(get_back_in_dmg), buff_intent()], follow_up_id="GET_BACK_IN_MOVE"),
    }
    return creature, MonsterAI(states, "WHAT_IS_IT_MOVE")


# ---- Queen (HP 302 / 322 asc) ----

def create_royal_guard(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 40
    creature = Creature(max_hp=hp, monster_id="ROYAL_GUARD")
    strike_dmg = 15

    def guard_strike(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, strike_dmg)

    states: dict[str, MonsterState] = {
        "STRIKE": MoveState("STRIKE", guard_strike, [attack_intent(strike_dmg)], follow_up_id="STRIKE"),
    }
    creature.apply_power(PowerId.MINION, 1)
    return creature, MonsterAI(states, "STRIKE")


def create_queen(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 400
    creature = Creature(max_hp=hp, monster_id="QUEEN")
    off_with_your_head_dmg = 3
    execution_dmg = 15

    def _has_amalgam_alive() -> bool:
        combat = creature.combat_state
        if combat is None:
            return True
        return any(enemy.monster_id == "TORCH_HEAD_AMALGAM" and enemy.is_alive for enemy in combat.enemies)

    def puppet_strings(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.CHAINS_OF_BINDING, 3, applier=creature)

    def youre_mine(combat: CombatState) -> None:
        combat.apply_power_to(combat.primary_player, PowerId.FRAIL, 99, applier=creature)
        combat.apply_power_to(combat.primary_player, PowerId.WEAK, 99, applier=creature)
        combat.apply_power_to(combat.primary_player, PowerId.VULNERABLE, 99, applier=creature)

    def burn_bright_for_me(combat: CombatState) -> None:
        for enemy in combat.alive_enemies:
            if enemy is not creature and enemy.side == creature.side:
                enemy.apply_power(PowerId.STRENGTH, 1, applier=creature)
        _gain_block(creature, 20)

    def off_with_your_head(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, off_with_your_head_dmg, hits=5)

    def execution(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, execution_dmg)

    def enrage(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 2, applier=creature)

    youre_mine_now_branch = ConditionalBranchState("YOURE_MINE_NOW_BRANCH")
    youre_mine_now_branch.add_branch(_has_amalgam_alive, "BURN_BRIGHT_FOR_ME_MOVE")
    youre_mine_now_branch.add_branch(lambda: True, "OFF_WITH_YOUR_HEAD_MOVE")

    burn_bright_branch = ConditionalBranchState("BURN_BRIGHT_FOR_ME_BRANCH")
    burn_bright_branch.add_branch(_has_amalgam_alive, "BURN_BRIGHT_FOR_ME_MOVE")
    burn_bright_branch.add_branch(lambda: True, "OFF_WITH_YOUR_HEAD_MOVE")

    states: dict[str, MonsterState] = {
        "PUPPET_STRINGS_MOVE": MoveState("PUPPET_STRINGS_MOVE", puppet_strings, [strong_debuff_intent()], follow_up_id="YOUR_MINE_MOVE"),
        "YOUR_MINE_MOVE": MoveState("YOUR_MINE_MOVE", youre_mine, [debuff_intent()], follow_up_id="YOURE_MINE_NOW_BRANCH"),
        "YOURE_MINE_NOW_BRANCH": youre_mine_now_branch,
        "BURN_BRIGHT_FOR_ME_MOVE": MoveState("BURN_BRIGHT_FOR_ME_MOVE", burn_bright_for_me, [buff_intent(), defend_intent()], follow_up_id="BURN_BRIGHT_FOR_ME_BRANCH"),
        "BURN_BRIGHT_FOR_ME_BRANCH": burn_bright_branch,
        "OFF_WITH_YOUR_HEAD_MOVE": MoveState("OFF_WITH_YOUR_HEAD_MOVE", off_with_your_head, [multi_attack_intent(off_with_your_head_dmg, 5)], follow_up_id="EXECUTION_MOVE"),
        "EXECUTION_MOVE": MoveState("EXECUTION_MOVE", execution, [attack_intent(execution_dmg)], follow_up_id="ENRAGE_MOVE"),
        "ENRAGE_MOVE": MoveState("ENRAGE_MOVE", enrage, [buff_intent()], follow_up_id="OFF_WITH_YOUR_HEAD_MOVE"),
    }
    return creature, MonsterAI(states, "PUPPET_STRINGS_MOVE")


# ---- TestSubject (HP 255 / 270 asc) ----

def create_test_subject(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 100
    creature = Creature(max_hp=hp, monster_id="TEST_SUBJECT")
    bite_dmg = 20
    skull_bash_dmg = 14
    pounce_dmg = 30
    multi_claw_dmg = 10
    big_pounce_dmg = 45
    burning_growl_burns = 3
    burning_growl_strength = 2
    enrage_amount = 2
    second_form_hp = 200
    third_form_hp = 300

    _state = {
        "respawns": 0,
        "extra_multi_claw_count": 0,
    }

    def _multi_claw_total_count() -> int:
        return 3 + _state["extra_multi_claw_count"]

    def respawn(combat: CombatState) -> None:
        _state["respawns"] += 1
        adaptable = creature.powers.get(PowerId.ADAPTABLE)
        do_revive = getattr(adaptable, "do_revive", None)
        if callable(do_revive):
            do_revive()
        scaled_hp = (second_form_hp if _state["respawns"] == 1 else third_form_hp) * len(combat.combat_player_states)
        creature.max_hp = scaled_hp
        creature.current_hp = scaled_hp
        if _state["respawns"] == 1:
            creature.apply_power(PowerId.PAINFUL_STABS, 1)
        else:
            creature.apply_power(PowerId.NEMESIS, 1)
            creature.powers.pop(PowerId.ADAPTABLE, None)
            creature.powers.pop(PowerId.PAINFUL_STABS, None)

    def bite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bite_dmg)

    def skull_bash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, skull_bash_dmg)
        combat.apply_power_to(combat.primary_player, PowerId.VULNERABLE, 1)

    def pounce(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, pounce_dmg)

    def multi_claw(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, multi_claw_dmg, hits=_multi_claw_total_count())
        _state["extra_multi_claw_count"] += 1
        states["MULTI_CLAW_MOVE"].intents = [multi_attack_intent(multi_claw_dmg, _multi_claw_total_count())]

    def phase3_lacerate(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, multi_claw_dmg, hits=3)

    def big_pounce(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, big_pounce_dmg)

    def burning_growl(combat: CombatState) -> None:
        for target in combat.get_enemies_of(creature):
            if getattr(target, "is_player", False):
                combat.add_status_cards_to_discard(target, "BURN", burning_growl_burns)
        creature.apply_power(PowerId.STRENGTH, burning_growl_strength)

    revive_branch = ConditionalBranchState("REVIVE_BRANCH")
    revive_branch.add_branch(lambda: _state["respawns"] < 2, "MULTI_CLAW_MOVE")
    revive_branch.add_branch(lambda: True, "PHASE3_LACERATE_MOVE")

    states: dict[str, MonsterState] = {
        "RESPAWN_MOVE": MoveState("RESPAWN_MOVE", respawn, [Intent(IntentType.HEAL), buff_intent()], follow_up_id="REVIVE_BRANCH", must_perform_once=True),
        "REVIVE_BRANCH": revive_branch,
        "BITE_MOVE": MoveState("BITE_MOVE", bite, [attack_intent(bite_dmg)], follow_up_id="SKULL_BASH_MOVE"),
        "SKULL_BASH_MOVE": MoveState("SKULL_BASH_MOVE", skull_bash, [attack_intent(skull_bash_dmg), debuff_intent()], follow_up_id="BITE_MOVE"),
        "POUNCE_MOVE": MoveState("POUNCE_MOVE", pounce, [attack_intent(pounce_dmg)], follow_up_id="MULTI_CLAW_MOVE"),
        "MULTI_CLAW_MOVE": MoveState("MULTI_CLAW_MOVE", multi_claw, [multi_attack_intent(multi_claw_dmg, _multi_claw_total_count())], follow_up_id="POUNCE_MOVE"),
        "PHASE3_LACERATE_MOVE": MoveState("PHASE3_LACERATE_MOVE", phase3_lacerate, [multi_attack_intent(multi_claw_dmg, 3)], follow_up_id="BIG_POUNCE_MOVE"),
        "BIG_POUNCE_MOVE": MoveState("BIG_POUNCE_MOVE", big_pounce, [attack_intent(big_pounce_dmg)], follow_up_id="BURNING_GROWL_MOVE"),
        "BURNING_GROWL_MOVE": MoveState("BURNING_GROWL_MOVE", burning_growl, [status_intent(), buff_intent()], follow_up_id="PHASE3_LACERATE_MOVE"),
    }
    creature.apply_power(PowerId.ADAPTABLE, 1)
    creature.apply_power(PowerId.ENRAGE, enrage_amount)
    return creature, MonsterAI(states, "BITE_MOVE")
