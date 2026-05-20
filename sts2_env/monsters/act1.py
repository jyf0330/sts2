"""Act 1 (Overgrowth) monsters: weak, normal, elite, boss.

All HP ranges, damage values, and state machines verified against decompiled C# source.
Weak monsters are re-exported from act1_weak.py for convenience.
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
from sts2_env.monsters.state_machine import MonsterAI, MonsterState, MoveState, RandomBranchState
from sts2_env.monsters.targets import (
    add_generated_cards_to_living_player_discards,
    apply_power_to_living_player_targets,
    living_player_targets,
)
from sts2_env.cards.status import make_dazed, make_infection, make_wound

if TYPE_CHECKING:
    from sts2_env.core.combat import CombatState

# Re-export weak monsters
from sts2_env.monsters.act1_weak import (  # noqa: F401
    create_shrinker_beetle,
    create_fuzzy_wurm_crawler,
    create_nibbit,
    create_leaf_slime_s,
    create_twig_slime_s,
    create_leaf_slime_m,
    create_twig_slime_m,
)


# ---- Helpers ----

def _deal_damage_to_player(combat: CombatState, creature: Creature, base_dmg: int, hits: int = 1) -> None:
    for _ in range(hits):
        targets = living_player_targets(combat)
        if not targets:
            break
        for target in targets:
            dmg = calculate_damage(base_dmg, creature, target, ValueProp.MOVE, combat)
            apply_damage(target, dmg, ValueProp.MOVE, combat, creature)
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


# ========================================================================
# NORMAL ENCOUNTERS
# ========================================================================

# ---- CubexConstruct (HP 65 / 70 asc) ----
# CHARGE_UP_MOVE -> REPEATER_MOVE -> REPEATER_MOVE_2 -> EXPEL_BLAST -> REPEATER_MOVE (loop)

def create_cubex_construct(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 65
    creature = Creature(max_hp=hp, monster_id="CUBEX_CONSTRUCT")

    blast_dmg = 7
    expel_dmg = 5

    def charge_up(combat: CombatState) -> None:
        combat.apply_power_to(creature, PowerId.STRENGTH, 2, applier=creature)

    def repeater(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, blast_dmg)
        combat.apply_power_to(creature, PowerId.STRENGTH, 2, applier=creature)

    def expel_blast(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, expel_dmg, hits=2)

    def submerge(combat: CombatState) -> None:
        _gain_block(creature, 15, combat)

    states: dict[str, MonsterState] = {
        "CHARGE_UP_MOVE": MoveState("CHARGE_UP_MOVE", charge_up, [buff_intent()], follow_up_id="REPEATER_MOVE"),
        "REPEATER_MOVE": MoveState(
            "REPEATER_MOVE",
            repeater,
            [attack_intent(blast_dmg), buff_intent()],
            follow_up_id="REPEATER_MOVE_2",
        ),
        "REPEATER_MOVE_2": MoveState(
            "REPEATER_MOVE_2",
            repeater,
            [attack_intent(blast_dmg), buff_intent()],
            follow_up_id="EXPEL_BLAST",
        ),
        "EXPEL_BLAST": MoveState(
            "EXPEL_BLAST",
            expel_blast,
            [multi_attack_intent(expel_dmg, 2)],
            follow_up_id="REPEATER_MOVE",
        ),
        "SUBMERGE_MOVE": MoveState("SUBMERGE_MOVE", submerge, [defend_intent()], follow_up_id="CHARGE_UP_MOVE"),
    }

    return creature, MonsterAI(states, "CHARGE_UP_MOVE")


def apply_cubex_construct_room_setup(creature: Creature, combat: CombatState) -> None:
    _gain_block(creature, 13, combat)
    creature.apply_power(PowerId.ARTIFACT, 1)


# ---- Flyconid (HP 47-49 / 51-53 asc) ----

def create_flyconid(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(47, 49)
    creature = Creature(max_hp=hp, monster_id="FLYCONID")

    smash_dmg = 11
    spore_dmg = 8
    vulnerable_spores_vulnerable = 2
    frail_spores_frail = 2

    def vulnerable_spores(combat: CombatState) -> None:
        apply_power_to_living_player_targets(
            combat,
            PowerId.VULNERABLE,
            vulnerable_spores_vulnerable,
            applier=creature,
        )

    def frail_spores(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, spore_dmg)
        apply_power_to_living_player_targets(combat, PowerId.FRAIL, frail_spores_frail, applier=creature)

    def smash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, smash_dmg)

    # Initial random: FrailSpores(2) or Smash(1)
    initial_rand = RandomBranchState("INITIAL")
    initial_rand.add_branch("FRAIL_SPORES_MOVE", weight=2.0)
    initial_rand.add_branch("SMASH_MOVE", weight=1.0)

    # Main random: all 3, cannot repeat
    main_rand = RandomBranchState("RAND")
    main_rand.add_branch("VULNERABLE_SPORES_MOVE", MoveRepeatType.CANNOT_REPEAT, weight=3.0)
    main_rand.add_branch("FRAIL_SPORES_MOVE", MoveRepeatType.CANNOT_REPEAT, weight=2.0)
    main_rand.add_branch("SMASH_MOVE", MoveRepeatType.CANNOT_REPEAT, weight=1.0)

    states: dict[str, MonsterState] = {
        "INITIAL": initial_rand,
        "RAND": main_rand,
        "VULNERABLE_SPORES_MOVE": MoveState(
            "VULNERABLE_SPORES_MOVE",
            vulnerable_spores,
            [debuff_intent()],
            follow_up_id="RAND",
        ),
        "FRAIL_SPORES_MOVE": MoveState(
            "FRAIL_SPORES_MOVE",
            frail_spores,
            [attack_intent(spore_dmg), debuff_intent()],
            follow_up_id="RAND",
        ),
        "SMASH_MOVE": MoveState("SMASH_MOVE", smash, [attack_intent(smash_dmg)], follow_up_id="RAND"),
    }
    return creature, MonsterAI(states, "INITIAL", rng)


# ---- Fogmog (HP 74 / 78 asc) ----

def create_eye_with_teeth(rng: Rng) -> tuple[Creature, MonsterAI]:
    creature = Creature(max_hp=6, monster_id="EYE_WITH_TEETH")
    distract_dazed = 3

    def distract(combat: CombatState) -> None:
        add_generated_cards_to_living_player_discards(combat, make_dazed, distract_dazed)

    states: dict[str, MonsterState] = {
        "DISTRACT_MOVE": MoveState("DISTRACT_MOVE", distract, [status_intent()], follow_up_id="DISTRACT_MOVE"),
    }
    creature.apply_power(PowerId.ILLUSION, 1)
    creature.apply_power(PowerId.MINION, 1)
    return creature, MonsterAI(states, "DISTRACT_MOVE")


def create_fogmog(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 74
    creature = Creature(max_hp=hp, monster_id="FOGMOG")

    swipe_dmg = 8
    headbutt_dmg = 14

    def illusion(combat: CombatState) -> None:
        eye, eye_ai = create_eye_with_teeth(rng)
        combat.add_enemy(eye, eye_ai)

    def swipe(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, swipe_dmg)
        combat.apply_power_to(creature, PowerId.STRENGTH, 1, applier=creature)

    def headbutt(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, headbutt_dmg)

    rand = RandomBranchState("BRANCH")
    rand.add_branch("SWIPE_RANDOM_MOVE", MoveRepeatType.CANNOT_REPEAT, weight=0.4)
    rand.add_branch("HEADBUTT_MOVE", MoveRepeatType.CANNOT_REPEAT, weight=0.6)

    states: dict[str, MonsterState] = {
        "ILLUSION_MOVE": MoveState("ILLUSION_MOVE", illusion, [Intent(IntentType.SUMMON)], follow_up_id="SWIPE_MOVE"),
        "SWIPE_MOVE": MoveState(
            "SWIPE_MOVE",
            swipe,
            [attack_intent(swipe_dmg), buff_intent()],
            follow_up_id="BRANCH",
        ),
        "BRANCH": rand,
        "SWIPE_RANDOM_MOVE": MoveState(
            "SWIPE_RANDOM_MOVE",
            swipe,
            [attack_intent(swipe_dmg), buff_intent()],
            follow_up_id="HEADBUTT_MOVE",
        ),
        "HEADBUTT_MOVE": MoveState(
            "HEADBUTT_MOVE",
            headbutt,
            [attack_intent(headbutt_dmg)],
            follow_up_id="SWIPE_MOVE",
        ),
    }
    return creature, MonsterAI(states, "ILLUSION_MOVE")


# ---- Inklet (HP 11-17 / 12-18 asc) ----

def create_inklet(rng: Rng, *, middle_inklet: bool = False) -> tuple[Creature, MonsterAI]:
    min_initial_hp = 11
    max_initial_hp = 17
    hp = rng.next_int(min_initial_hp, max_initial_hp)
    creature = Creature(max_hp=hp, monster_id="INKLET")
    jab_move = "JAB_MOVE"
    whirlwind_move = "WHIRLWIND_MOVE"
    piercing_gaze_move = "PIERCING_GAZE_MOVE"
    rand_move = "RAND"
    jab_dmg = 3
    whirlwind_dmg = 2
    whirlwind_hits = 3
    piercing_gaze_dmg = 10
    slippery_amount = 1

    def jab(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, jab_dmg)

    def whirlwind(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, whirlwind_dmg, hits=whirlwind_hits)

    def piercing_gaze(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, piercing_gaze_dmg)

    rand = RandomBranchState(rand_move)
    rand.add_branch(piercing_gaze_move, MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch(whirlwind_move, MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        jab_move: MoveState(jab_move, jab, [attack_intent(jab_dmg)], follow_up_id=rand_move),
        whirlwind_move: MoveState(
            whirlwind_move,
            whirlwind,
            [multi_attack_intent(whirlwind_dmg, whirlwind_hits)],
            follow_up_id=jab_move,
        ),
        piercing_gaze_move: MoveState(
            piercing_gaze_move,
            piercing_gaze,
            [attack_intent(piercing_gaze_dmg)],
            follow_up_id=jab_move,
        ),
        rand_move: rand,
    }

    creature.apply_power(PowerId.SLIPPERY, slippery_amount)
    initial = whirlwind_move if middle_inklet else jab_move
    return creature, MonsterAI(states, initial, rng)


# ---- Mawler (HP 72 / 76 asc) ----

def create_mawler(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 72
    creature = Creature(max_hp=hp, monster_id="MAWLER")

    rip_dmg = 14
    claw_dmg = 4
    roar_vulnerable = 3

    def rip_and_tear(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, rip_dmg)

    def roar(combat: CombatState) -> None:
        apply_power_to_living_player_targets(combat, PowerId.VULNERABLE, roar_vulnerable, applier=creature)

    def claw(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, claw_dmg, hits=2)

    rand = RandomBranchState("RAND")
    rand.add_branch("RIP_AND_TEAR_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("ROAR_MOVE", MoveRepeatType.USE_ONLY_ONCE)
    rand.add_branch("CLAW_MOVE", MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        "RAND": rand,
        "RIP_AND_TEAR_MOVE": MoveState(
            "RIP_AND_TEAR_MOVE",
            rip_and_tear,
            [attack_intent(rip_dmg)],
            follow_up_id="RAND",
        ),
        "ROAR_MOVE": MoveState("ROAR_MOVE", roar, [debuff_intent()], follow_up_id="RAND"),
        "CLAW_MOVE": MoveState("CLAW_MOVE", claw, [multi_attack_intent(claw_dmg, 2)], follow_up_id="RAND"),
    }
    return creature, MonsterAI(states, "CLAW_MOVE")


# ---- VineShambler (HP 61 / 64 asc) ----

def create_vine_shambler(rng: Rng) -> tuple[Creature, MonsterAI]:
    initial_hp = 61
    hp = initial_hp
    creature = Creature(max_hp=hp, monster_id="VINE_SHAMBLER")
    grasping_vines_move = "GRASPING_VINES_MOVE"
    swipe_move = "SWIPE_MOVE"
    chomp_move = "CHOMP_MOVE"
    grasping_vines_dmg = 8
    tangled_amount = 1
    swipe_dmg = 6
    swipe_hits = 2
    chomp_dmg = 16

    def grasping_vines(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, grasping_vines_dmg)
        apply_power_to_living_player_targets(combat, PowerId.TANGLED, tangled_amount, applier=creature)

    def swipe(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, swipe_dmg, hits=swipe_hits)

    def chomp(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, chomp_dmg)

    states: dict[str, MonsterState] = {
        swipe_move: MoveState(
            swipe_move,
            swipe,
            [multi_attack_intent(swipe_dmg, swipe_hits)],
            follow_up_id=grasping_vines_move,
        ),
        grasping_vines_move: MoveState(
            grasping_vines_move,
            grasping_vines,
            [attack_intent(grasping_vines_dmg), Intent(IntentType.CARD_DEBUFF)],
            follow_up_id=chomp_move,
        ),
        chomp_move: MoveState(chomp_move, chomp, [attack_intent(chomp_dmg)], follow_up_id=swipe_move),
    }

    return creature, MonsterAI(states, swipe_move)


# ---- SlitheringStrangler (HP 53-55 / 54-56 asc) ----

def create_slithering_strangler(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(53, 55)
    creature = Creature(max_hp=hp, monster_id="SLITHERING_STRANGLER")

    twack_dmg = 7
    lash_dmg = 12
    twack_block = 5
    constrict_amount = 3

    def constrict(combat: CombatState) -> None:
        apply_power_to_living_player_targets(combat, PowerId.CONSTRICT, constrict_amount, applier=creature)

    def twack(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, twack_dmg)
        _gain_block(creature, twack_block, combat)

    def lash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, lash_dmg)

    rand = RandomBranchState("rand")
    rand.add_branch("TWACK")
    rand.add_branch("LASH")

    states: dict[str, MonsterState] = {
        "CONSTRICT": MoveState("CONSTRICT", constrict, [debuff_intent()], follow_up_id="rand"),
        "TWACK": MoveState("TWACK", twack, [attack_intent(twack_dmg), defend_intent()], follow_up_id="CONSTRICT"),
        "LASH": MoveState("LASH", lash, [attack_intent(lash_dmg)], follow_up_id="CONSTRICT"),
        "rand": rand,
    }

    return creature, MonsterAI(states, "CONSTRICT")


# ---- SnappingJaxfruit (HP 31-33 / 34-36 asc) ----

def create_snapping_jaxfruit(rng: Rng) -> tuple[Creature, MonsterAI]:
    min_initial_hp = 31
    max_initial_hp = 33
    hp = rng.next_int(min_initial_hp, max_initial_hp)
    creature = Creature(max_hp=hp, monster_id="SNAPPING_JAXFRUIT")
    energy_orb_move = "ENERGY_ORB_MOVE"
    energy_dmg = 3
    energy_strength = 2

    def energy_orb(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, energy_dmg)
        combat.apply_power_to(creature, PowerId.STRENGTH, energy_strength, applier=creature)

    states: dict[str, MonsterState] = {
        energy_orb_move: MoveState(
            energy_orb_move,
            energy_orb,
            [attack_intent(energy_dmg), buff_intent()],
            follow_up_id=energy_orb_move,
        ),
    }

    return creature, MonsterAI(states, energy_orb_move)


# ---- RubyRaiders ----

def create_assassin_ruby_raider(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(18, 23)
    creature = Creature(max_hp=hp, monster_id="ASSASSIN_RUBY_RAIDER")
    killshot_dmg = 11

    def killshot(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, killshot_dmg)

    states: dict[str, MonsterState] = {
        "KILLSHOT_MOVE": MoveState(
            "KILLSHOT_MOVE",
            killshot,
            [attack_intent(killshot_dmg)],
            follow_up_id="KILLSHOT_MOVE",
        ),
    }
    return creature, MonsterAI(states, "KILLSHOT_MOVE")


def create_axe_ruby_raider(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(20, 22)
    creature = Creature(max_hp=hp, monster_id="AXE_RUBY_RAIDER")
    swing_dmg = 5
    swing_block = 5
    big_swing_dmg = 12

    def swing(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, swing_dmg)
        _gain_block(creature, swing_block, combat)

    def big_swing(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, big_swing_dmg)

    states: dict[str, MonsterState] = {
        "SWING_1": MoveState("SWING_1", swing, [attack_intent(swing_dmg), defend_intent()], follow_up_id="SWING_2"),
        "SWING_2": MoveState("SWING_2", swing, [attack_intent(swing_dmg), defend_intent()], follow_up_id="BIG_SWING"),
        "BIG_SWING": MoveState("BIG_SWING", big_swing, [attack_intent(big_swing_dmg)], follow_up_id="SWING_1"),
    }
    return creature, MonsterAI(states, "SWING_1")


def create_brute_ruby_raider(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(30, 33)
    creature = Creature(max_hp=hp, monster_id="BRUTE_RUBY_RAIDER")
    beat_dmg = 7

    def beat(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, beat_dmg)

    def roar(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 3)

    states: dict[str, MonsterState] = {
        "BEAT_MOVE": MoveState("BEAT_MOVE", beat, [attack_intent(beat_dmg)], follow_up_id="ROAR_MOVE"),
        "ROAR_MOVE": MoveState("ROAR_MOVE", roar, [buff_intent()], follow_up_id="BEAT_MOVE"),
    }
    return creature, MonsterAI(states, "BEAT_MOVE")


def create_crossbow_ruby_raider(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(18, 21)
    creature = Creature(max_hp=hp, monster_id="CROSSBOW_RUBY_RAIDER")
    fire_dmg = 14
    reload_block = 3

    def fire(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, fire_dmg)

    def reload(combat: CombatState) -> None:
        _gain_block(creature, reload_block, combat)

    states: dict[str, MonsterState] = {
        "RELOAD_MOVE": MoveState("RELOAD_MOVE", reload, [defend_intent()], follow_up_id="FIRE_MOVE"),
        "FIRE_MOVE": MoveState("FIRE_MOVE", fire, [attack_intent(fire_dmg)], follow_up_id="RELOAD_MOVE"),
    }
    return creature, MonsterAI(states, "RELOAD_MOVE")


def create_tracker_ruby_raider(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(21, 25)
    creature = Creature(max_hp=hp, monster_id="TRACKER_RUBY_RAIDER")
    hounds_dmg = 1
    hounds_hits = 8
    track_frail = 2

    def track(combat: CombatState) -> None:
        apply_power_to_living_player_targets(combat, PowerId.FRAIL, track_frail, applier=creature)

    def hounds(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, hounds_dmg, hits=hounds_hits)

    states: dict[str, MonsterState] = {
        "TRACK_MOVE": MoveState("TRACK_MOVE", track, [debuff_intent()], follow_up_id="HOUNDS_MOVE"),
        "HOUNDS_MOVE": MoveState(
            "HOUNDS_MOVE",
            hounds,
            [multi_attack_intent(hounds_dmg, hounds_hits)],
            follow_up_id="HOUNDS_MOVE",
        ),
    }
    return creature, MonsterAI(states, "TRACK_MOVE")


# ========================================================================
# ELITE ENCOUNTERS
# ========================================================================

# ---- BygoneEffigy (HP 127 / 132 asc) ----

def create_bygone_effigy(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 127
    creature = Creature(max_hp=hp, monster_id="BYGONE_EFFIGY")
    slash_dmg = 15

    def initial_sleep(combat: CombatState) -> None:
        pass  # Does nothing

    def wake(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 10)

    def sleep_move(combat: CombatState) -> None:
        pass

    def slashes(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, slash_dmg)

    states: dict[str, MonsterState] = {
        "INITIAL_SLEEP_MOVE": MoveState(
            "INITIAL_SLEEP_MOVE",
            initial_sleep,
            [sleep_intent()],
            follow_up_id="WAKE_MOVE",
        ),
        "WAKE_MOVE": MoveState("WAKE_MOVE", wake, [buff_intent()], follow_up_id="SLASHES_MOVE"),
        "SLEEP_MOVE": MoveState("SLEEP_MOVE", sleep_move, [sleep_intent()], follow_up_id="SLASHES_MOVE"),
        "SLASHES_MOVE": MoveState(
            "SLASHES_MOVE",
            slashes,
            [attack_intent(slash_dmg)],
            follow_up_id="SLASHES_MOVE",
        ),
    }

    # AfterAddedToRoom: applies Slow power
    creature.apply_power(PowerId.SLOW, 1)

    return creature, MonsterAI(states, "INITIAL_SLEEP_MOVE")


# ---- Byrdonis (HP 91-94 / 99 asc) ----

def create_byrdonis(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(91, 94)
    creature = Creature(max_hp=hp, monster_id="BYRDONIS")
    peck_dmg = 3
    peck_hits = 3
    swoop_dmg = 16

    def peck(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, peck_dmg, hits=peck_hits)

    def swoop(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, swoop_dmg)

    states: dict[str, MonsterState] = {
        "SWOOP_MOVE": MoveState("SWOOP_MOVE", swoop, [attack_intent(swoop_dmg)], follow_up_id="PECK_MOVE"),
        "PECK_MOVE": MoveState(
            "PECK_MOVE",
            peck,
            [multi_attack_intent(peck_dmg, peck_hits)],
            follow_up_id="SWOOP_MOVE",
        ),
    }

    # AfterAddedToRoom: applies Territorial power
    creature.apply_power(PowerId.TERRITORIAL, 1)

    return creature, MonsterAI(states, "SWOOP_MOVE")


# ---- PhrogParasite (HP 61-64 / 66-68 asc) ----

def create_phrog_parasite(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(61, 64)
    creature = Creature(max_hp=hp, monster_id="PHROG_PARASITE")
    bite_dmg = 4
    infect_infections = 3

    def infest(combat: CombatState) -> None:
        add_generated_cards_to_living_player_discards(combat, make_infection, infect_infections)

    def bite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bite_dmg, hits=4)

    states: dict[str, MonsterState] = {
        "INFECT_MOVE": MoveState("INFECT_MOVE", infest, [status_intent()], follow_up_id="LASH_MOVE"),
        "LASH_MOVE": MoveState("LASH_MOVE", bite, [multi_attack_intent(bite_dmg, 4)], follow_up_id="INFECT_MOVE"),
    }

    # AfterAddedToRoom: Infested(4)
    creature.apply_power(PowerId.INFESTED, 4)

    return creature, MonsterAI(states, "INFECT_MOVE")


# ========================================================================
# BOSS ENCOUNTERS
# ========================================================================

# ---- Vantom (HP 173 / 183 asc) ----

def create_parafright(rng: Rng) -> tuple[Creature, MonsterAI]:
    creature = Creature(max_hp=21, monster_id="PARAFRIGHT")
    slam_dmg = 16

    def slam(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, slam_dmg)

    states: dict[str, MonsterState] = {
        "SLAM_MOVE": MoveState("SLAM_MOVE", slam, [attack_intent(slam_dmg)], follow_up_id="SLAM_MOVE"),
    }
    creature.apply_power(PowerId.ILLUSION, 1)
    creature.apply_power(PowerId.MINION, 1)
    return creature, MonsterAI(states, "SLAM_MOVE")


def create_vantom(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 173
    creature = Creature(max_hp=hp, monster_id="VANTOM")
    ink_blot_dmg = 7
    inky_lance_dmg = 6
    inky_lance_hits = 2
    dismember_dmg = 27
    dismember_wounds = 3
    prepare_strength = 2
    slippery_amount = 9

    def ink_blot(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, ink_blot_dmg)

    def inky_lance(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, inky_lance_dmg, hits=inky_lance_hits)

    def dismember(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, dismember_dmg)
        if combat.is_over:
            return
        add_generated_cards_to_living_player_discards(combat, make_wound, dismember_wounds)

    def prepare(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, prepare_strength, applier=creature)

    states: dict[str, MonsterState] = {
        "INK_BLOT_MOVE": MoveState(
            "INK_BLOT_MOVE",
            ink_blot,
            [attack_intent(ink_blot_dmg)],
            follow_up_id="INKY_LANCE_MOVE",
        ),
        "INKY_LANCE_MOVE": MoveState(
            "INKY_LANCE_MOVE",
            inky_lance,
            [multi_attack_intent(inky_lance_dmg, inky_lance_hits)],
            follow_up_id="DISMEMBER_MOVE",
        ),
        "DISMEMBER_MOVE": MoveState(
            "DISMEMBER_MOVE",
            dismember,
            [attack_intent(dismember_dmg), status_intent()],
            follow_up_id="PREPARE_MOVE",
        ),
        "PREPARE_MOVE": MoveState(
            "PREPARE_MOVE",
            prepare,
            [buff_intent()],
            follow_up_id="INK_BLOT_MOVE",
        ),
    }
    creature.apply_power(PowerId.SLIPPERY, slippery_amount)
    return creature, MonsterAI(states, "INK_BLOT_MOVE")


# ---- CeremonialBeast (HP 252 / 262 asc) ----

def create_ceremonial_beast(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 252
    creature = Creature(max_hp=hp, monster_id="CEREMONIAL_BEAST")
    stamp_move = "STAMP_MOVE"
    plow_move_id = "PLOW_MOVE"
    stun_move = "STUN_MOVE"
    beast_cry_move = "BEAST_CRY_MOVE"
    stomp_move_id = "STOMP_MOVE"
    crush_move_id = "CRUSH_MOVE"
    plow_dmg = 18
    stomp_dmg = 15
    crush_dmg = 17
    plow_amount = 150
    plow_strength = 2
    crush_strength = 3
    beast_cry_ringing = 1

    def stamp(combat: CombatState) -> None:
        creature.apply_power(PowerId.PLOW, plow_amount)

    def plow_move(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, plow_dmg)
        if combat.is_over:
            return
        combat.apply_power_to(creature, PowerId.STRENGTH, plow_strength, applier=creature)

    def stun(combat: CombatState) -> None:
        pass

    def beast_cry(combat: CombatState) -> None:
        apply_power_to_living_player_targets(combat, PowerId.RINGING, beast_cry_ringing, applier=creature)

    def stomp(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, stomp_dmg)

    def crush(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, crush_dmg)
        if combat.is_over:
            return
        combat.apply_power_to(creature, PowerId.STRENGTH, crush_strength, applier=creature)

    states: dict[str, MonsterState] = {
        stamp_move: MoveState(stamp_move, stamp, [buff_intent()], follow_up_id=plow_move_id),
        plow_move_id: MoveState(
            plow_move_id,
            plow_move,
            [attack_intent(plow_dmg), buff_intent()],
            follow_up_id=plow_move_id,
        ),
        stun_move: MoveState(
            stun_move,
            stun,
            [Intent(IntentType.STUN)],
            follow_up_id=beast_cry_move,
            must_perform_once=True,
        ),
        beast_cry_move: MoveState(beast_cry_move, beast_cry, [debuff_intent()], follow_up_id=stomp_move_id),
        stomp_move_id: MoveState(stomp_move_id, stomp, [attack_intent(stomp_dmg)], follow_up_id=crush_move_id),
        crush_move_id: MoveState(
            crush_move_id,
            crush,
            [attack_intent(crush_dmg), buff_intent()],
            follow_up_id=beast_cry_move,
        ),
    }
    return creature, MonsterAI(states, stamp_move)


# ---- TheKin (KinPriest + 2 KinFollowers) ----

def create_kin_priest(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 119
    creature = Creature(max_hp=hp, monster_id="KIN_PRIEST")
    smite_dmg = 22

    def conversion(combat: CombatState) -> None:
        creature.apply_power(PowerId.RITUAL, 4)

    def smite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, smite_dmg)

    states: dict[str, MonsterState] = {
        "CONVERSION": MoveState("CONVERSION", conversion, [buff_intent()], follow_up_id="SMITE"),
        "SMITE": MoveState("SMITE", smite, [attack_intent(smite_dmg)], follow_up_id="SMITE"),
    }
    return creature, MonsterAI(states, "CONVERSION")


def create_kin_follower(rng: Rng, *, starts_with_dance: bool = False) -> tuple[Creature, MonsterAI]:
    min_initial_hp = 58
    max_initial_hp = 59
    hp = rng.next_int(min_initial_hp, max_initial_hp)
    creature = Creature(max_hp=hp, monster_id="KIN_FOLLOWER")
    quick_slash_move = "QUICK_SLASH_MOVE"
    boomerang_move = "BOOMERANG_MOVE"
    power_dance_move = "POWER_DANCE_MOVE"
    quick_slash_dmg = 5
    boomerang_dmg = 2
    boomerang_hits = 2
    dance_strength = 2
    minion_amount = 1

    def quick_slash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, quick_slash_dmg)

    def boomerang(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, boomerang_dmg, hits=boomerang_hits)

    def power_dance(combat: CombatState) -> None:
        combat.apply_power_to(creature, PowerId.STRENGTH, dance_strength, applier=creature)

    states: dict[str, MonsterState] = {
        quick_slash_move: MoveState(
            quick_slash_move,
            quick_slash,
            [attack_intent(quick_slash_dmg)],
            follow_up_id=boomerang_move,
        ),
        boomerang_move: MoveState(
            boomerang_move,
            boomerang,
            [multi_attack_intent(boomerang_dmg, boomerang_hits)],
            follow_up_id=power_dance_move,
        ),
        power_dance_move: MoveState(
            power_dance_move,
            power_dance,
            [buff_intent()],
            follow_up_id=quick_slash_move,
        ),
    }

    creature.apply_power(PowerId.MINION, minion_amount)
    initial = power_dance_move if starts_with_dance else quick_slash_move
    return creature, MonsterAI(states, initial, rng)
