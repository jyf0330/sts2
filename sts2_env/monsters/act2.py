"""Act 2 (Hive) monsters: weak, normal, elite, boss.

All HP ranges, damage values, and state machines verified against decompiled C# source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts2_env.core.creature import Creature
from sts2_env.core.enums import CardId, CardRarity, CombatSide, MoveRepeatType, PowerId, ValueProp
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
from sts2_env.monsters.targets import (
    add_generated_cards_to_living_player_discards,
    apply_power_to_living_player_targets,
    living_player_targets,
    player_or_pet_owner,
)
from sts2_env.cards.status import (
    make_dazed,
    make_disintegration,
    make_frantic_escape,
    make_infection,
    make_mind_rot,
    make_sloth_status,
    make_toxic,
    make_void,
    make_waste_away,
)
from sts2_env.powers.remaining_c import SandpitPower, SwipePower

if TYPE_CHECKING:
    from sts2_env.core.combat import CombatState


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


def _thieving_hopper_targets(combat: CombatState, creature: Creature) -> list[Creature]:
    return living_player_targets(combat)


def _contains_card_instance(cards: list, card) -> bool:
    return any(candidate is card for candidate in cards)


def _remove_card_instance(cards: list, card) -> None:
    for index, candidate in enumerate(cards):
        if candidate is card:
            cards.pop(index)
            return


def _thieving_hopper_steal_candidates(combat: CombatState, target: Creature) -> list:
    target_owner = player_or_pet_owner(target)
    state = combat.combat_player_state_for(target_owner)
    if state is None:
        return []
    return [
        card
        for card in list(state.draw) + list(state.discard)
        if _contains_card_instance(state.player_state.deck, card)
    ]


def _choose_thieving_hopper_card(combat: CombatState, cards: list):
    def not_imbued(card) -> bool:
        return not card.has_enchantment("Imbued")

    priorities = (
        lambda card: not_imbued(card) and card.rarity == CardRarity.UNCOMMON,
        lambda card: not_imbued(card) and card.rarity in {CardRarity.COMMON, CardRarity.RARE, CardRarity.EVENT},
        lambda card: not_imbued(card) and card.rarity in {CardRarity.BASIC, CardRarity.QUEST},
        lambda card: card.rarity == CardRarity.ANCIENT or card.has_enchantment("Imbued"),
    )
    for priority in priorities:
        matching = [card for card in cards if priority(card)]
        if matching:
            return combat.combat_card_generation_rng.choice(matching)
    return combat.combat_card_generation_rng.choice(cards) if cards else None


def _steal_card_with_swipe(combat: CombatState, creature: Creature, target: Creature) -> None:
    card = _choose_thieving_hopper_card(combat, _thieving_hopper_steal_candidates(combat, target))
    if card is None:
        return
    combat._remove_card_from_piles(card)
    target_owner = player_or_pet_owner(target)
    state = combat.combat_player_state_for(target_owner)
    if state is not None:
        _remove_card_instance(state.player_state.deck, card)
    swipe = creature.powers.get(PowerId.SWIPE)
    if not isinstance(swipe, SwipePower):
        swipe = SwipePower(0)
        creature.powers[PowerId.SWIPE] = swipe
    swipe.amount += 1
    swipe.steal(card, target_owner)


def _deal_damage_to_targets(
    combat: CombatState,
    creature: Creature,
    targets: list[Creature],
    base_dmg: int,
) -> None:
    for target in targets:
        if target.is_dead:
            continue
        dmg = calculate_damage(base_dmg, creature, target, ValueProp.MOVE, combat)
        apply_damage(target, dmg, ValueProp.MOVE, combat, creature)


# ========================================================================
# WEAK ENCOUNTERS
# ========================================================================

# ---- ThievingHopper (HP 79 / 84 asc) ----

def create_thieving_hopper(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 79
    creature = Creature(max_hp=hp, monster_id="THIEVING_HOPPER")
    theft_dmg = 17
    hat_trick_dmg = 21
    nab_dmg = 14

    def thievery(combat: CombatState) -> None:
        targets = _thieving_hopper_targets(combat, creature)
        for target in targets:
            _steal_card_with_swipe(combat, creature, target)
        _deal_damage_to_targets(combat, creature, targets, theft_dmg)

    def flutter(combat: CombatState) -> None:
        creature.apply_power(PowerId.FLUTTER, 5)

    def hat_trick(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, hat_trick_dmg)

    def nab(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, nab_dmg)

    def escape(combat: CombatState) -> None:
        combat.escape_creature(creature)

    states: dict[str, MonsterState] = {
        "THIEVERY_MOVE": MoveState(
            "THIEVERY_MOVE",
            thievery,
            [attack_intent(theft_dmg), Intent(IntentType.CARD_DEBUFF)],
            follow_up_id="FLUTTER_MOVE",
        ),
        "FLUTTER_MOVE": MoveState("FLUTTER_MOVE", flutter, [buff_intent()], follow_up_id="HAT_TRICK_MOVE"),
        "HAT_TRICK_MOVE": MoveState(
            "HAT_TRICK_MOVE",
            hat_trick,
            [attack_intent(hat_trick_dmg)],
            follow_up_id="NAB_MOVE",
        ),
        "NAB_MOVE": MoveState("NAB_MOVE", nab, [attack_intent(nab_dmg)], follow_up_id="ESCAPE_MOVE"),
        "ESCAPE_MOVE": MoveState("ESCAPE_MOVE", escape, [Intent(IntentType.ESCAPE)], follow_up_id="ESCAPE_MOVE"),
    }
    creature.apply_power(PowerId.ESCAPE_ARTIST, 5)
    return creature, MonsterAI(states, "THIEVERY_MOVE")


# ---- Tunneler (HP 87 / 92 asc) ----

def create_tunneler(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 87
    creature = Creature(max_hp=hp, monster_id="TUNNELER")
    bite_dmg = 13
    burrow_block = 32
    below_dmg = 23

    def burrow(combat: CombatState) -> None:
        creature.apply_power(PowerId.BURROWED, 1)
        _gain_block(creature, burrow_block, combat)

    def bite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bite_dmg)

    def below(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, below_dmg)

    def dizzy(combat: CombatState) -> None:
        return

    states: dict[str, MonsterState] = {
        "BITE_MOVE": MoveState("BITE_MOVE", bite, [attack_intent(bite_dmg)], follow_up_id="BURROW_MOVE"),
        "BURROW_MOVE": MoveState(
            "BURROW_MOVE",
            burrow,
            [buff_intent(), defend_intent()],
            follow_up_id="BELOW_MOVE_1",
        ),
        "BELOW_MOVE_1": MoveState(
            "BELOW_MOVE_1",
            below,
            [attack_intent(below_dmg)],
            follow_up_id="BELOW_MOVE_1",
        ),
        "DIZZY_MOVE": MoveState("DIZZY_MOVE", dizzy, [Intent(IntentType.STUN)], follow_up_id="BITE_MOVE"),
    }
    return creature, MonsterAI(states, "BITE_MOVE")


# ---- Bowlbugs ----

def create_bowlbug_egg(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(21, 22)
    creature = Creature(max_hp=hp, monster_id="BOWLBUG_EGG")
    bite_dmg = 7
    protect_block = 7

    def bite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bite_dmg)
        _gain_block(creature, protect_block, combat)

    states: dict[str, MonsterState] = {
        "BITE_MOVE": MoveState(
            "BITE_MOVE",
            bite,
            [attack_intent(bite_dmg), defend_intent()],
            follow_up_id="BITE_MOVE",
        ),
    }
    return creature, MonsterAI(states, "BITE_MOVE")


def create_bowlbug_nectar(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(35, 38)
    creature = Creature(max_hp=hp, monster_id="BOWLBUG_NECTAR")
    thrash_dmg = 3
    buff_str = 15

    def thrash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, thrash_dmg)

    def buff_move(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, buff_str)

    def thrash2(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, thrash_dmg)

    states: dict[str, MonsterState] = {
        "THRASH_MOVE": MoveState(
            "THRASH_MOVE",
            thrash,
            [attack_intent(thrash_dmg)],
            follow_up_id="BUFF_MOVE",
        ),
        "BUFF_MOVE": MoveState("BUFF_MOVE", buff_move, [buff_intent()], follow_up_id="THRASH2_MOVE"),
        "THRASH2_MOVE": MoveState(
            "THRASH2_MOVE",
            thrash2,
            [attack_intent(thrash_dmg)],
            follow_up_id="THRASH2_MOVE",
        ),
    }
    return creature, MonsterAI(states, "THRASH_MOVE")


def create_bowlbug_rock(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(45, 48)
    creature = Creature(max_hp=hp, monster_id="BOWLBUG_ROCK")
    headbutt_dmg = 15

    def headbutt(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, headbutt_dmg)

    def dizzy(combat: CombatState) -> None:
        power = creature.powers.get(PowerId.IMBALANCED)
        if power is not None and hasattr(power, "was_fully_blocked"):
            power.was_fully_blocked = False

    def is_off_balance() -> bool:
        power = creature.powers.get(PowerId.IMBALANCED)
        return bool(getattr(power, "was_fully_blocked", False))

    cond = ConditionalBranchState("POST_HEADBUTT")
    cond.add_branch(is_off_balance, "DIZZY_MOVE")
    cond.add_branch(lambda: True, "HEADBUTT_MOVE")

    states: dict[str, MonsterState] = {
        "HEADBUTT_MOVE": MoveState(
            "HEADBUTT_MOVE",
            headbutt,
            [attack_intent(headbutt_dmg)],
            follow_up_id="POST_HEADBUTT",
        ),
        "POST_HEADBUTT": cond,
        "DIZZY_MOVE": MoveState(
            "DIZZY_MOVE",
            dizzy,
            [Intent(IntentType.STUN)],
            follow_up_id="HEADBUTT_MOVE",
        ),
    }
    creature.apply_power(PowerId.IMBALANCED, 1)
    return creature, MonsterAI(states, "HEADBUTT_MOVE")


def create_bowlbug_silk(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(40, 43)
    creature = Creature(max_hp=hp, monster_id="BOWLBUG_SILK")
    thrash_dmg = 4
    toxic_spit_weak = 1

    def toxic_spit(combat: CombatState) -> None:
        apply_power_to_living_player_targets(combat, PowerId.WEAK, toxic_spit_weak, applier=creature)

    def thrash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, thrash_dmg, hits=2)

    states: dict[str, MonsterState] = {
        "TRASH_MOVE": MoveState(
            "TRASH_MOVE",
            thrash,
            [multi_attack_intent(thrash_dmg, 2)],
            follow_up_id="TOXIC_SPIT_MOVE",
        ),
        "TOXIC_SPIT_MOVE": MoveState(
            "TOXIC_SPIT_MOVE",
            toxic_spit,
            [debuff_intent()],
            follow_up_id="TRASH_MOVE",
        ),
    }
    return creature, MonsterAI(states, "TOXIC_SPIT_MOVE")


# ---- Exoskeleton (HP 24-28 / 25-29 asc) ----

def create_exoskeleton(rng: Rng, slot: str = "first") -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(24, 28)
    creature = Creature(max_hp=hp, monster_id="EXOSKELETON")
    skitter_dmg = 1
    skitter_hits = 3
    mandible_dmg = 8

    def skitter(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, skitter_dmg, hits=skitter_hits)

    def mandible(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, mandible_dmg)

    def enrage(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 2)

    rand = RandomBranchState("RAND")
    rand.add_branch("SKITTER_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("MANDIBLE_MOVE", MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        "RAND": rand,
        "SKITTER_MOVE": MoveState(
            "SKITTER_MOVE",
            skitter,
            [multi_attack_intent(skitter_dmg, skitter_hits)],
            follow_up_id="RAND",
        ),
        "MANDIBLE_MOVE": MoveState(
            "MANDIBLE_MOVE",
            mandible,
            [attack_intent(mandible_dmg)],
            follow_up_id="ENRAGE_MOVE",
        ),
        "ENRAGE_MOVE": MoveState("ENRAGE_MOVE", enrage, [buff_intent()], follow_up_id="RAND"),
    }

    slot_map = {
        "first": "SKITTER_MOVE",
        "second": "MANDIBLE_MOVE",
        "third": "ENRAGE_MOVE",
        "fourth": "RAND",
    }
    initial = slot_map.get(slot, "RAND")

    creature.apply_power(PowerId.HARD_TO_KILL, 9)
    return creature, MonsterAI(states, initial, rng)


# ========================================================================
# NORMAL ENCOUNTERS
# ========================================================================

# ---- Chomper (HP 60-64 / 63-67 asc) ----

def create_chomper(rng: Rng, scream_first: bool = False) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(60, 64)
    creature = Creature(max_hp=hp, monster_id="CHOMPER")
    clamp_dmg = 8
    screech_dazed = 3

    def clamp(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, clamp_dmg, hits=2)

    def screech(combat: CombatState) -> None:
        add_generated_cards_to_living_player_discards(combat, make_dazed, screech_dazed)

    states: dict[str, MonsterState] = {
        "CLAMP_MOVE": MoveState(
            "CLAMP_MOVE",
            clamp,
            [multi_attack_intent(clamp_dmg, 2)],
            follow_up_id="SCREECH_MOVE",
        ),
        "SCREECH_MOVE": MoveState("SCREECH_MOVE", screech, [status_intent()], follow_up_id="CLAMP_MOVE"),
    }

    creature.apply_power(PowerId.ARTIFACT, 2)
    initial = "SCREECH_MOVE" if scream_first else "CLAMP_MOVE"
    return creature, MonsterAI(states, initial, rng)


# ---- HunterKiller (HP 60-65 / 63-68 asc) ----

def create_hunter_killer(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 121
    creature = Creature(max_hp=hp, monster_id="HUNTER_KILLER")
    bite_dmg = 17
    puncture_dmg = 7
    tenderizing_goop_tender = 1

    def tenderizing_goop(combat: CombatState) -> None:
        apply_power_to_living_player_targets(combat, PowerId.TENDER, tenderizing_goop_tender, applier=creature)

    def bite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bite_dmg)

    def puncture(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, puncture_dmg, hits=3)

    rand = RandomBranchState("RAND")
    rand.add_branch("BITE_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("PUNCTURE_MOVE", MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2)

    states: dict[str, MonsterState] = {
        "TENDERIZING_GOOP_MOVE": MoveState(
            "TENDERIZING_GOOP_MOVE",
            tenderizing_goop,
            [debuff_intent()],
            follow_up_id="RAND",
        ),
        "BITE_MOVE": MoveState("BITE_MOVE", bite, [attack_intent(bite_dmg)], follow_up_id="RAND"),
        "PUNCTURE_MOVE": MoveState(
            "PUNCTURE_MOVE",
            puncture,
            [multi_attack_intent(puncture_dmg, 3)],
            follow_up_id="RAND",
        ),
        "RAND": rand,
    }
    return creature, MonsterAI(states, "TENDERIZING_GOOP_MOVE")


# ---- Wriggler (HP 17-21 / 18-22 asc) ----

def create_wriggler(
    rng: Rng,
    slot: str = "wriggler1",
    start_stunned: bool = False,
) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(17, 21)
    creature = Creature(max_hp=hp, monster_id="WRIGGLER")
    bite_dmg = 6
    wriggle_str = 2

    def bite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bite_dmg)

    def wriggle(combat: CombatState) -> None:
        combat.add_card_to_discard(make_infection())
        creature.apply_power(PowerId.STRENGTH, wriggle_str)

    def spawned(combat: CombatState) -> None:
        return

    init = ConditionalBranchState("INIT_MOVE")
    init.add_branch(lambda: slot in ("wriggler1", "wriggler3"), "NASTY_BITE_MOVE")
    init.add_branch(lambda: slot in ("wriggler2", "wriggler4"), "WRIGGLE_MOVE")
    init.add_branch(lambda: True, "NASTY_BITE_MOVE")

    states: dict[str, MonsterState] = {
        "INIT_MOVE": init,
        "SPAWNED_MOVE": MoveState(
            "SPAWNED_MOVE",
            spawned,
            [Intent(IntentType.STUN)],
            follow_up_id="INIT_MOVE",
        ),
        "NASTY_BITE_MOVE": MoveState(
            "NASTY_BITE_MOVE",
            bite,
            [attack_intent(bite_dmg)],
            follow_up_id="WRIGGLE_MOVE",
        ),
        "WRIGGLE_MOVE": MoveState(
            "WRIGGLE_MOVE",
            wriggle,
            [buff_intent(), status_intent()],
            follow_up_id="NASTY_BITE_MOVE",
        ),
    }
    initial = "SPAWNED_MOVE" if start_stunned else "INIT_MOVE"
    return creature, MonsterAI(states, initial, rng)


# ---- LouseProgenitor (HP 134-136 / 138-141 asc) ----

def create_louse_progenitor(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(134, 136)
    creature = Creature(max_hp=hp, monster_id="LOUSE_PROGENITOR")
    web_dmg = 9
    web_frail = 2
    pounce_dmg = 14
    curl_block = 14
    grow_str = 5

    def web(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, web_dmg)
        apply_power_to_living_player_targets(combat, PowerId.FRAIL, web_frail, applier=creature)

    def curl_and_grow(combat: CombatState) -> None:
        _gain_block(creature, curl_block, combat)
        creature.apply_power(PowerId.STRENGTH, grow_str)

    def pounce(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, pounce_dmg)

    states: dict[str, MonsterState] = {
        "WEB_CANNON_MOVE": MoveState(
            "WEB_CANNON_MOVE",
            web,
            [attack_intent(web_dmg), debuff_intent()],
            follow_up_id="CURL_AND_GROW_MOVE",
        ),
        "CURL_AND_GROW_MOVE": MoveState(
            "CURL_AND_GROW_MOVE",
            curl_and_grow,
            [defend_intent(), buff_intent()],
            follow_up_id="POUNCE_MOVE",
        ),
        "POUNCE_MOVE": MoveState(
            "POUNCE_MOVE",
            pounce,
            [attack_intent(pounce_dmg)],
            follow_up_id="WEB_CANNON_MOVE",
        ),
    }
    creature.apply_power(PowerId.CURL_UP, curl_block)
    return creature, MonsterAI(states, "WEB_CANNON_MOVE")


# ---- Myte (HP 61-67 / 64-69 asc) ----

def create_myte(rng: Rng, slot: str = "first") -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(61, 67)
    creature = Creature(max_hp=hp, monster_id="MYTE")
    bite_dmg = 13
    suck_dmg = 4
    toxic_count = 2

    def bite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bite_dmg)

    def toxic(combat: CombatState) -> None:
        for target in living_player_targets(combat):
            for _ in range(toxic_count):
                combat.add_generated_card_to_creature_hand(
                    target,
                    make_toxic(),
                    added_by_player=False,
                )

    def suck(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, suck_dmg)
        combat.apply_power_to(creature, PowerId.STRENGTH, 2, applier=creature)

    states: dict[str, MonsterState] = {
        "TOXIC_MOVE": MoveState("TOXIC_MOVE", toxic, [status_intent()], follow_up_id="BITE_MOVE"),
        "BITE_MOVE": MoveState("BITE_MOVE", bite, [attack_intent(bite_dmg)], follow_up_id="SUCK_MOVE"),
        "SUCK_MOVE": MoveState("SUCK_MOVE", suck, [attack_intent(suck_dmg), buff_intent()], follow_up_id="TOXIC_MOVE"),
    }

    initial = "TOXIC_MOVE" if slot == "first" else "SUCK_MOVE"
    return creature, MonsterAI(states, initial, rng)


# ---- Ovicopter (HP 67-72 / 70-75 asc) + ToughEgg ----

def create_tough_egg(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(14, 18)
    creature = Creature(max_hp=hp, monster_id="TOUGH_EGG")
    nibble_dmg = 4

    def hatch(combat: CombatState) -> None:
        hatchling_hp = rng.next_int(19, 22)
        creature.max_hp = hatchling_hp
        creature.current_hp = hatchling_hp
        creature.powers.pop(PowerId.HATCH, None)

    def nibble(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, nibble_dmg)

    states: dict[str, MonsterState] = {
        "HATCH_MOVE": MoveState("HATCH_MOVE", hatch, [Intent(IntentType.SUMMON)], follow_up_id="NIBBLE_MOVE"),
        "NIBBLE_MOVE": MoveState("NIBBLE_MOVE", nibble, [attack_intent(nibble_dmg)], follow_up_id="NIBBLE_MOVE"),
    }
    creature.apply_power(PowerId.MINION, 1)
    creature.apply_power(PowerId.HATCH, 1)
    return creature, MonsterAI(states, "HATCH_MOVE")


def create_ovicopter(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(124, 130)
    creature = Creature(max_hp=hp, monster_id="OVICOPTER")
    smash_dmg = 16
    tenderizer_dmg = 7
    tenderizer_vulnerable = 2
    paste_str = 3

    def can_lay(combat: CombatState | None) -> bool:
        if combat is None:
            return True
        return sum(1 for teammate in combat.get_teammates_of(creature) if teammate.is_alive) <= 3

    def lay_eggs(combat: CombatState) -> None:
        for _ in range(3):
            egg, egg_ai = create_tough_egg(rng)
            combat.add_enemy(egg, egg_ai)

    def smash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, smash_dmg)

    def tenderizer(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, tenderizer_dmg)
        apply_power_to_living_player_targets(combat, PowerId.VULNERABLE, tenderizer_vulnerable, applier=creature)

    def nutritional_paste(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, paste_str)

    summon_branch = ConditionalBranchState("SUMMON_BRANCH_STATE")
    summon_branch.add_branch(lambda: can_lay(creature.combat_state), "LAY_EGGS_MOVE")
    summon_branch.add_branch(lambda: True, "NUTRITIONAL_PASTE_MOVE")

    states: dict[str, MonsterState] = {
        "LAY_EGGS_MOVE": MoveState(
            "LAY_EGGS_MOVE",
            lay_eggs,
            [Intent(IntentType.SUMMON)],
            follow_up_id="SMASH_MOVE",
        ),
        "SMASH_MOVE": MoveState("SMASH_MOVE", smash, [attack_intent(smash_dmg)], follow_up_id="TENDERIZER_MOVE"),
        "TENDERIZER_MOVE": MoveState(
            "TENDERIZER_MOVE",
            tenderizer,
            [attack_intent(tenderizer_dmg), debuff_intent()],
            follow_up_id="SUMMON_BRANCH_STATE",
        ),
        "NUTRITIONAL_PASTE_MOVE": MoveState(
            "NUTRITIONAL_PASTE_MOVE",
            nutritional_paste,
            [buff_intent()],
            follow_up_id="SMASH_MOVE",
        ),
        "SUMMON_BRANCH_STATE": summon_branch,
    }
    return creature, MonsterAI(states, "LAY_EGGS_MOVE")


# ---- SlumberingBeetle (HP 66-70 / 69-73 asc) ----

def create_slumbering_beetle(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 86
    creature = Creature(max_hp=hp, monster_id="SLUMBERING_BEETLE")
    rollout_dmg = 16

    def snore(combat: CombatState) -> None:
        pass

    def rollout(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, rollout_dmg)
        combat.apply_power_to(creature, PowerId.STRENGTH, 2, applier=creature)

    cond = ConditionalBranchState("SNORE_NEXT")
    cond.add_branch(lambda: creature.has_power(PowerId.SLUMBER), "SNORE_MOVE")
    cond.add_branch(lambda: True, "ROLL_OUT_MOVE")

    states: dict[str, MonsterState] = {
        "SNORE_MOVE": MoveState("SNORE_MOVE", snore, [sleep_intent()], follow_up_id="SNORE_NEXT"),
        "SNORE_NEXT": cond,
        "ROLL_OUT_MOVE": MoveState(
            "ROLL_OUT_MOVE",
            rollout,
            [attack_intent(rollout_dmg), buff_intent()],
            follow_up_id="ROLL_OUT_MOVE",
        ),
    }
    creature.apply_power(PowerId.PLATING, 15)
    creature.apply_power(PowerId.SLUMBER, 3)
    return creature, MonsterAI(states, "SNORE_MOVE")


# ---- SpinyToad (HP 116-119 / 121-124 asc) ----

def create_spiny_toad(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(116, 119)
    creature = Creature(max_hp=hp, monster_id="SPINY_TOAD")
    lash_dmg = 17
    explosion_dmg = 23
    spines_amount = 5

    def lash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, lash_dmg)

    def spines(combat: CombatState) -> None:
        creature.apply_power(PowerId.THORNS, spines_amount)

    def explosion(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, explosion_dmg)
        # Remove all thorns
        if PowerId.THORNS in creature.powers:
            del creature.powers[PowerId.THORNS]

    states: dict[str, MonsterState] = {
        "PROTRUDING_SPIKES_MOVE": MoveState(
            "PROTRUDING_SPIKES_MOVE",
            spines,
            [buff_intent()],
            follow_up_id="SPIKE_EXPLOSION_MOVE",
        ),
        "SPIKE_EXPLOSION_MOVE": MoveState(
            "SPIKE_EXPLOSION_MOVE",
            explosion,
            [attack_intent(explosion_dmg)],
            follow_up_id="TONGUE_LASH_MOVE",
        ),
        "TONGUE_LASH_MOVE": MoveState(
            "TONGUE_LASH_MOVE",
            lash,
            [attack_intent(lash_dmg)],
            follow_up_id="PROTRUDING_SPIKES_MOVE",
        ),
    }
    return creature, MonsterAI(states, "PROTRUDING_SPIKES_MOVE")


# ---- TheObscura (HP 36-39 / 38-41 asc) ----

def create_the_obscura(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 123
    creature = Creature(max_hp=hp, monster_id="THE_OBSCURA")
    gaze_dmg = 10
    hardening_dmg = 6
    hardening_block = 6

    def illusion(combat: CombatState) -> None:
        from sts2_env.monsters.act1 import create_parafright

        parafright, parafright_ai = create_parafright(rng)
        combat.add_enemy(parafright, parafright_ai)

    def piercing_gaze(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, gaze_dmg)

    def sail(combat: CombatState) -> None:
        for teammate in combat.get_teammates_of(creature):
            if teammate.is_alive:
                teammate.apply_power(PowerId.STRENGTH, 3)

    def hardening_strike(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, hardening_dmg)
        _gain_block(creature, hardening_block, combat)

    rand = RandomBranchState("RAND")
    rand.add_branch("PIERCING_GAZE_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("SAIL_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("HARDENING_STRIKE_MOVE", MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        "ILLUSION_MOVE": MoveState("ILLUSION_MOVE", illusion, [Intent(IntentType.SUMMON)], follow_up_id="RAND"),
        "RAND": rand,
        "PIERCING_GAZE_MOVE": MoveState(
            "PIERCING_GAZE_MOVE",
            piercing_gaze,
            [attack_intent(gaze_dmg)],
            follow_up_id="RAND",
        ),
        "SAIL_MOVE": MoveState("SAIL_MOVE", sail, [buff_intent()], follow_up_id="RAND"),
        "HARDENING_STRIKE_MOVE": MoveState(
            "HARDENING_STRIKE_MOVE",
            hardening_strike,
            [attack_intent(hardening_dmg), defend_intent()],
            follow_up_id="RAND",
        ),
    }
    return creature, MonsterAI(states, "ILLUSION_MOVE")


# ========================================================================
# ELITE ENCOUNTERS
# ========================================================================

# ---- Decimillipede (3 segments) (HP 42-48 / 48-56 asc) ----

def create_decimillipede_segment(rng: Rng, starter_idx: int = 0) -> tuple[Creature, MonsterAI]:
    hp = rng.next_int(42, 48)
    creature = Creature(max_hp=hp, monster_id="DECIMILLIPEDE_SEGMENT")
    writhe_dmg = 5
    constrict_dmg = 8
    constrict_weak = 1
    bulk_dmg = 6

    def writhe(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, writhe_dmg, hits=2)

    def constrict(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, constrict_dmg)
        apply_power_to_living_player_targets(combat, PowerId.WEAK, constrict_weak, applier=creature)

    def bulk(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bulk_dmg)
        combat.apply_power_to(creature, PowerId.STRENGTH, 2, applier=creature)

    def dead_move(combat: CombatState) -> None:
        pass

    def reattach(combat: CombatState) -> None:
        power = creature.powers.get(PowerId.REATTACH)
        do_reattach = getattr(power, "do_reattach", None)
        if callable(do_reattach):
            do_reattach(creature)
        else:
            creature.heal(25)

    rand = RandomBranchState("RAND")
    rand.add_branch("WRITHE_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("BULK_MOVE", MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch("CONSTRICT_MOVE", MoveRepeatType.CANNOT_REPEAT)

    states: dict[str, MonsterState] = {
        "WRITHE_MOVE": MoveState(
            "WRITHE_MOVE",
            writhe,
            [multi_attack_intent(writhe_dmg, 2)],
            follow_up_id="CONSTRICT_MOVE",
        ),
        "CONSTRICT_MOVE": MoveState(
            "CONSTRICT_MOVE",
            constrict,
            [attack_intent(constrict_dmg), debuff_intent()],
            follow_up_id="BULK_MOVE",
        ),
        "BULK_MOVE": MoveState(
            "BULK_MOVE",
            bulk,
            [attack_intent(bulk_dmg), buff_intent()],
            follow_up_id="WRITHE_MOVE",
        ),
        "DEAD_MOVE": MoveState("DEAD_MOVE", dead_move, [Intent(IntentType.UNKNOWN)], follow_up_id="REATTACH_MOVE"),
        "REATTACH_MOVE": MoveState(
            "REATTACH_MOVE",
            reattach,
            [Intent(IntentType.HEAL)],
            follow_up_id="RAND",
            must_perform_once=True,
        ),
        "RAND": rand,
    }

    starter_map = {0: "WRITHE_MOVE", 1: "BULK_MOVE", 2: "CONSTRICT_MOVE"}
    initial = starter_map.get(starter_idx, "WRITHE_MOVE")
    creature.apply_power(PowerId.REATTACH, 25)
    return creature, MonsterAI(states, initial, rng)


# ---- DecimillipedeSegmentFront (HP 42-48 / 48-56 asc) ----
# Identical behavior to DecimillipedeSegment (same base class in C#).
# The only difference is visual (front segment animation).

def create_decimillipede_segment_front(rng: Rng, starter_idx: int = 0) -> tuple[Creature, MonsterAI]:
    creature, ai = create_decimillipede_segment(rng, starter_idx)
    creature.monster_id = "DECIMILLIPEDE_SEGMENT_FRONT"
    return creature, ai


# ---- DecimillipedeSegmentMiddle (HP 42-48 / 48-56 asc) ----
# Identical behavior to DecimillipedeSegment (same base class in C#).

def create_decimillipede_segment_middle(rng: Rng, starter_idx: int = 0) -> tuple[Creature, MonsterAI]:
    creature, ai = create_decimillipede_segment(rng, starter_idx)
    creature.monster_id = "DECIMILLIPEDE_SEGMENT_MIDDLE"
    return creature, ai


# ---- DecimillipedeSegmentBack (HP 42-48 / 48-56 asc) ----
# Identical behavior to DecimillipedeSegment (same base class in C#).

def create_decimillipede_segment_back(rng: Rng, starter_idx: int = 0) -> tuple[Creature, MonsterAI]:
    creature, ai = create_decimillipede_segment(rng, starter_idx)
    creature.monster_id = "DECIMILLIPEDE_SEGMENT_BACK"
    return creature, ai


# ---- Entomancer (HP 145 / 155 asc) ----

def create_entomancer(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 145
    creature = Creature(max_hp=hp, monster_id="ENTOMANCER")
    spear_dmg = 18
    bees_dmg = 3
    bees_hits = 7

    _state = {"personal_hive": 1}

    def bees(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bees_dmg, hits=bees_hits)

    def spear(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, spear_dmg)

    def pheromone_spit(combat: CombatState) -> None:
        if _state["personal_hive"] < 3:
            _state["personal_hive"] += 1
            creature.apply_power(PowerId.PERSONAL_HIVE, 1)
            creature.apply_power(PowerId.STRENGTH, 1)
        else:
            creature.apply_power(PowerId.STRENGTH, 2)

    states: dict[str, MonsterState] = {
        "BEES_MOVE": MoveState(
            "BEES_MOVE",
            bees,
            [multi_attack_intent(bees_dmg, bees_hits)],
            follow_up_id="SPEAR_MOVE",
        ),
        "SPEAR_MOVE": MoveState("SPEAR_MOVE", spear, [attack_intent(spear_dmg)], follow_up_id="PHEROMONE_SPIT_MOVE"),
        "PHEROMONE_SPIT_MOVE": MoveState(
            "PHEROMONE_SPIT_MOVE",
            pheromone_spit,
            [buff_intent()],
            follow_up_id="BEES_MOVE",
        ),
    }

    creature.apply_power(PowerId.PERSONAL_HIVE, 1)
    return creature, MonsterAI(states, "BEES_MOVE")


# ---- InfestedPrism (HP 200 / 215 asc) ----

def create_infested_prism(rng: Rng) -> tuple[Creature, MonsterAI]:
    creature = Creature(max_hp=200, monster_id="INFESTED_PRISM")
    jab_dmg = 22
    radiate_dmg = 16
    radiate_block = 16
    whirlwind_dmg = 9
    pulsate_block = 20
    pulsate_str = 4

    def jab(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, jab_dmg)

    def radiate(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, radiate_dmg)
        _gain_block(creature, radiate_block, combat)

    def whirlwind(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, whirlwind_dmg, hits=3)

    def pulsate(combat: CombatState) -> None:
        _gain_block(creature, pulsate_block, combat)
        creature.apply_power(PowerId.STRENGTH, pulsate_str)

    states: dict[str, MonsterState] = {
        "JAB_MOVE": MoveState("JAB_MOVE", jab, [attack_intent(jab_dmg)], follow_up_id="RADIATE_MOVE"),
        "RADIATE_MOVE": MoveState("RADIATE_MOVE", radiate, [attack_intent(radiate_dmg), defend_intent()], follow_up_id="WHIRLWIND_MOVE"),
        "WHIRLWIND_MOVE": MoveState("WHIRLWIND_MOVE", whirlwind, [multi_attack_intent(whirlwind_dmg, 3)], follow_up_id="PULSATE_MOVE"),
        "PULSATE_MOVE": MoveState("PULSATE_MOVE", pulsate, [defend_intent(), buff_intent()], follow_up_id="JAB_MOVE"),
    }

    creature.apply_power(PowerId.VITAL_SPARK, 1)
    return creature, MonsterAI(states, "JAB_MOVE")


# ========================================================================
# BOSS ENCOUNTERS
# ========================================================================

# ---- TheInsatiable (HP 242 / 256 asc) ----

def create_the_insatiable(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 321
    creature = Creature(max_hp=hp, monster_id="THE_INSATIABLE")
    thrash_dmg = 8
    bite_dmg = 28
    salivate_str = 2

    def liquify_ground(combat: CombatState) -> None:
        for target in living_player_targets(combat):
            sandpit = SandpitPower(4)
            sandpit.set_target(target)
            existing = creature.powers.get(PowerId.SANDPIT)
            if isinstance(existing, SandpitPower):
                existing.add_instance(4, target)
            else:
                creature.powers[PowerId.SANDPIT] = sandpit
            combat.add_status_cards_to_draw(target, "FRANTIC_ESCAPE", 3, random_position=True)
            combat.add_status_cards_to_discard(target, "FRANTIC_ESCAPE", 3)

    def thrash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, thrash_dmg, hits=2)

    def lunging_bite(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bite_dmg)

    def salivate(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, salivate_str, applier=creature)

    states: dict[str, MonsterState] = {
        "LIQUIFY_GROUND_MOVE": MoveState(
            "LIQUIFY_GROUND_MOVE",
            liquify_ground,
            [buff_intent(), status_intent()],
            follow_up_id="THRASH_MOVE_1",
        ),
        "THRASH_MOVE_1": MoveState(
            "THRASH_MOVE_1",
            thrash,
            [multi_attack_intent(thrash_dmg, 2)],
            follow_up_id="LUNGING_BITE_MOVE",
        ),
        "LUNGING_BITE_MOVE": MoveState(
            "LUNGING_BITE_MOVE",
            lunging_bite,
            [attack_intent(bite_dmg)],
            follow_up_id="SALIVATE_MOVE",
        ),
        "SALIVATE_MOVE": MoveState(
            "SALIVATE_MOVE",
            salivate,
            [buff_intent()],
            follow_up_id="THRASH_MOVE_2",
        ),
        "THRASH_MOVE_2": MoveState(
            "THRASH_MOVE_2",
            thrash,
            [multi_attack_intent(thrash_dmg, 2)],
            follow_up_id="THRASH_MOVE_1",
        ),
    }
    return creature, MonsterAI(states, "LIQUIFY_GROUND_MOVE")


# ---- KnowledgeDemon (HP 379 / 399 asc) ----
# C# cycle: CURSE_OF_KNOWLEDGE -> SLAP(17) -> KNOWLEDGE_OVERWHELMING(8x3) -> PONDER(11+heal30+str2) -> conditional

def create_knowledge_demon(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 379
    creature = Creature(max_hp=hp, monster_id="KNOWLEDGE_DEMON")
    slap_dmg = 17
    overwhelming_dmg = 8
    overwhelming_hits = 3
    ponder_dmg = 11
    ponder_heal = 30
    ponder_str = 2

    _state = {"curse_counter": 0}
    curse_sets = (
        (make_disintegration, make_mind_rot),
        (make_disintegration, make_sloth_status),
        (make_disintegration, make_waste_away),
    )
    disintegration_damage_values = (6, 7, 8)

    def apply_knowledge_curse(combat: CombatState, target: Creature, card) -> None:
        if card.card_id == CardId.DISINTEGRATION:
            combat.apply_power_to(
                target,
                PowerId.DISINTEGRATION,
                card.effect_vars.get("disintegration_power", 6),
                applier=creature,
                source=card,
            )
        elif card.card_id == CardId.MIND_ROT:
            combat.apply_power_to(
                target,
                PowerId.MIND_ROT,
                card.effect_vars.get("mind_rot_power", 1),
                applier=creature,
                source=card,
            )
        elif card.card_id == CardId.SLOTH_STATUS:
            combat.apply_power_to(
                target,
                PowerId.SLOTH,
                card.effect_vars.get("sloth_power", 3),
                applier=creature,
                source=card,
            )
        elif card.card_id == CardId.WASTE_AWAY:
            combat.apply_power_to(
                target,
                PowerId.WASTE_AWAY,
                card.effect_vars.get("waste_away_power", 1),
                applier=creature,
                source=card,
            )

    def request_knowledge_choice(combat: CombatState, targets: list[Creature], index: int) -> None:
        if index >= len(targets):
            _state["curse_counter"] += 1
            return
        target = targets[index]
        counter = _state["curse_counter"]
        cards = [factory() for factory in curse_sets[counter]]
        for card in cards:
            card.owner = target
            if card.card_id == CardId.DISINTEGRATION:
                card.effect_vars["disintegration_power"] = disintegration_damage_values[counter]

        def resolver(selected) -> None:
            if selected is not None:
                apply_knowledge_curse(combat, target, selected)
            request_knowledge_choice(combat, targets, index + 1)

        combat.request_card_choice(
            prompt="Curse of Knowledge",
            cards=cards,
            source_pile="knowledge_demon",
            resolver=resolver,
            owner=target,
        )

    def curse_of_knowledge(combat: CombatState) -> None:
        counter = _state["curse_counter"]
        if counter >= len(curse_sets):
            raise RuntimeError(f"No Curse of Knowledge set at index {counter}")
        targets = [state.creature for state in combat.combat_player_states if state.creature.is_alive]
        request_knowledge_choice(combat, targets, 0)

    def slap(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, slap_dmg)

    def knowledge_overwhelming(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, overwhelming_dmg, hits=overwhelming_hits)

    def ponder(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, ponder_dmg)
        if combat.is_over:
            return
        creature.heal(ponder_heal)
        combat.apply_power_to(creature, PowerId.STRENGTH, ponder_str, applier=creature)

    # After Ponder: if curse_counter < 3, go back to CURSE_OF_KNOWLEDGE; else SLAP
    curse_check = ConditionalBranchState("CurseOfKnowledgeBranch")
    curse_check.add_branch(lambda: _state["curse_counter"] < 3, "CURSE_OF_KNOWLEDGE_MOVE")
    curse_check.add_branch(lambda: True, "SLAP_MOVE")

    states: dict[str, MonsterState] = {
        "CURSE_OF_KNOWLEDGE_MOVE": MoveState(
            "CURSE_OF_KNOWLEDGE_MOVE",
            curse_of_knowledge,
            [debuff_intent()],
            follow_up_id="SLAP_MOVE",
        ),
        "SLAP_MOVE": MoveState(
            "SLAP_MOVE",
            slap,
            [attack_intent(slap_dmg)],
            follow_up_id="KNOWLEDGE_OVERWHELMING_MOVE",
        ),
        "KNOWLEDGE_OVERWHELMING_MOVE": MoveState(
            "KNOWLEDGE_OVERWHELMING_MOVE",
            knowledge_overwhelming,
            [multi_attack_intent(overwhelming_dmg, overwhelming_hits)],
            follow_up_id="PONDER_MOVE",
        ),
        "PONDER_MOVE": MoveState(
            "PONDER_MOVE",
            ponder,
            [attack_intent(ponder_dmg), buff_intent()],
            follow_up_id="CurseOfKnowledgeBranch",
        ),
        "CurseOfKnowledgeBranch": curse_check,
    }
    return creature, MonsterAI(states, "CURSE_OF_KNOWLEDGE_MOVE")


# ---- KaiserCrab (Crusher + Rocket) ----

def create_crusher(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 199
    creature = Creature(max_hp=hp, monster_id="CRUSHER")
    thrash_dmg = 12
    enlarging_dmg = 4
    bug_sting_dmg = 6
    bug_sting_debuff = 2
    guarded_strike_dmg = 12
    guarded_block = 18

    def thrash(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, thrash_dmg)

    def enlarging_strike(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, enlarging_dmg)

    def bug_sting(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, bug_sting_dmg, hits=2)
        apply_power_to_living_player_targets(combat, PowerId.WEAK, bug_sting_debuff, applier=creature)
        apply_power_to_living_player_targets(combat, PowerId.FRAIL, bug_sting_debuff, applier=creature)

    def adapt(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 2)

    def guarded_strike(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, guarded_strike_dmg)
        _gain_block(creature, guarded_block, combat)

    states: dict[str, MonsterState] = {
        "THRASH_MOVE": MoveState("THRASH_MOVE", thrash, [attack_intent(thrash_dmg)], follow_up_id="ENLARGING_STRIKE_MOVE"),
        "ENLARGING_STRIKE_MOVE": MoveState(
            "ENLARGING_STRIKE_MOVE",
            enlarging_strike,
            [attack_intent(enlarging_dmg)],
            follow_up_id="BUG_STING_MOVE",
        ),
        "BUG_STING_MOVE": MoveState(
            "BUG_STING_MOVE",
            bug_sting,
            [multi_attack_intent(bug_sting_dmg, 2), debuff_intent()],
            follow_up_id="ADAPT_MOVE",
        ),
        "ADAPT_MOVE": MoveState("ADAPT_MOVE", adapt, [buff_intent()], follow_up_id="GUARDED_STRIKE_MOVE"),
        "GUARDED_STRIKE_MOVE": MoveState(
            "GUARDED_STRIKE_MOVE",
            guarded_strike,
            [attack_intent(guarded_strike_dmg), defend_intent()],
            follow_up_id="THRASH_MOVE",
        ),
    }

    creature.apply_power(PowerId.BACK_ATTACK_LEFT, 1)
    creature.apply_power(PowerId.CRAB_RAGE, 1)
    return creature, MonsterAI(states, "THRASH_MOVE")


def create_rocket(rng: Rng) -> tuple[Creature, MonsterAI]:
    hp = 189
    creature = Creature(max_hp=hp, monster_id="ROCKET")
    targeting_dmg = 3
    precision_dmg = 18
    laser_dmg = 31

    def targeting_reticle(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, targeting_dmg)

    def precision_beam(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, precision_dmg)

    def charge_up(combat: CombatState) -> None:
        creature.apply_power(PowerId.STRENGTH, 2)

    def laser(combat: CombatState) -> None:
        _deal_damage_to_player(combat, creature, laser_dmg)

    def recharge(combat: CombatState) -> None:
        return

    states: dict[str, MonsterState] = {
        "TARGETING_RETICLE_MOVE": MoveState(
            "TARGETING_RETICLE_MOVE",
            targeting_reticle,
            [attack_intent(targeting_dmg)],
            follow_up_id="PRECISION_BEAM_MOVE",
        ),
        "PRECISION_BEAM_MOVE": MoveState(
            "PRECISION_BEAM_MOVE",
            precision_beam,
            [attack_intent(precision_dmg)],
            follow_up_id="CHARGE_UP_MOVE",
        ),
        "CHARGE_UP_MOVE": MoveState("CHARGE_UP_MOVE", charge_up, [buff_intent()], follow_up_id="LASER_MOVE"),
        "LASER_MOVE": MoveState("LASER_MOVE", laser, [attack_intent(laser_dmg)], follow_up_id="RECHARGE_MOVE"),
        "RECHARGE_MOVE": MoveState(
            "RECHARGE_MOVE",
            recharge,
            [sleep_intent()],
            follow_up_id="TARGETING_RETICLE_MOVE",
        ),
    }

    creature.apply_power(PowerId.BACK_ATTACK_RIGHT, 1)
    creature.apply_power(PowerId.CRAB_RAGE, 1)
    return creature, MonsterAI(states, "TARGETING_RETICLE_MOVE")
