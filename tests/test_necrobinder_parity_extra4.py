"""Additional focused parity tests for remaining Necrobinder cards."""

import sts2_env.powers  # noqa: F401

from sts2_env.cards.factory import create_card
from sts2_env.cards.necrobinder import (
    make_banshees_cry,
    create_necrobinder_starter_deck,
    make_blight_strike,
    make_bodyguard,
    make_call_of_the_void,
    make_deathbringer,
    make_deaths_door,
    make_defend_necrobinder,
    make_end_of_days,
    make_fear,
    make_fetch,
    make_flatten,
    make_friendship,
    make_high_five,
    make_invoke,
    make_negative_pulse,
    make_neurosurge,
    make_pagestorm,
    make_poke,
    make_sculpting_strike,
    make_sentry_mode,
    make_sic_em,
    make_unleash,
    make_veilpiercer,
)
from sts2_env.cards.status import make_soul, make_void
from sts2_env.core.combat import CombatState
from sts2_env.core.enums import CardId, CombatSide, PowerId, ValueProp
from sts2_env.core.hooks import fire_after_side_turn_start
from sts2_env.core.rng import Rng
from sts2_env.monsters.act1_weak import create_shrinker_beetle
from sts2_env.powers.base import PowerInstance


class _CannotHitPower(PowerInstance):
    def __init__(self):
        super().__init__(PowerId.COVERED, 1)

    def should_allow_hitting(self, owner, combat):
        return False


def _make_combat(*, extra_enemies: int = 0) -> CombatState:
    combat = CombatState(
        player_hp=70,
        player_max_hp=70,
        deck=create_necrobinder_starter_deck(),
        rng_seed=9090,
        character_id="Necrobinder",
    )
    creature, ai = create_shrinker_beetle(Rng(9090))
    combat.add_enemy(creature, ai)
    for i in range(extra_enemies):
        extra_creature, extra_ai = create_shrinker_beetle(Rng(9200 + i))
        combat.add_enemy(extra_creature, extra_ai)
    combat.start_combat()
    return combat


class TestNecrobinderParityExtra4:
    def test_blight_strike_applies_doom_equal_to_damage_dealt(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_blight_strike()]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 92
        assert enemy.get_power_amount(PowerId.DOOM) == 8

    def test_call_of_the_void_generates_ethereal_cards_next_turn_start(self):
        combat = _make_combat()
        combat.hand = [make_call_of_the_void()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.CALL_OF_THE_VOID) == 1

        combat.end_player_turn()
        generated = [card for card in combat.hand if card.is_ethereal]
        assert generated
        assert len({card.card_id for card in generated}) == len(generated)
        assert all(card.rarity.name not in {"BASIC", "ANCIENT"} for card in generated)

    def test_banshees_cry_hits_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.hand = [make_banshees_cry()]
        combat.energy = 6

        assert combat.play_card(0)

        assert blocked.current_hp == 100
        assert hittable.current_hp == 67

    def test_deathbringer_applies_doom_and_weak_to_all_enemies(self):
        combat = _make_combat()
        extra_enemy, extra_ai = create_shrinker_beetle(Rng(9091))
        combat.add_enemy(extra_enemy, extra_ai)
        combat.hand = [make_deathbringer()]
        combat.energy = 2

        assert combat.play_card(0)
        for enemy in combat.enemies:
            assert enemy.get_power_amount(PowerId.DOOM) == 21
            assert enemy.get_power_amount(PowerId.WEAK) == 1

    def test_deaths_door_repeats_after_owner_applies_doom_this_turn(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        combat.apply_power_to(enemy, PowerId.DOOM, 1, applier=combat.player)
        combat.hand = [make_deaths_door()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.block == 18

    def test_deaths_door_does_not_repeat_for_non_owner_doom_applier(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        combat.apply_power_to(combat.player, PowerId.DOOM, 1, applier=enemy)
        combat.hand = [make_deaths_door()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.block == 6

    def test_deaths_door_stops_repeated_block_after_combat_ends(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = 5
        combat.apply_power_to(enemy, PowerId.DOOM, 1, applier=combat.player)
        combat.player.apply_power(PowerId.JUGGERNAUT, 5)
        combat.hand = [make_deaths_door()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.is_over
        assert combat.player.block == 6

    def test_negative_pulse_debuffs_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.hand = [make_negative_pulse()]
        combat.energy = 1

        assert combat.play_card(0)

        assert combat.player.block == 5
        assert blocked.get_power_amount(PowerId.DOOM) == 0
        assert hittable.get_power_amount(PowerId.DOOM) == 7

    def test_deathbringer_debuffs_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.hand = [make_deathbringer()]
        combat.energy = 2

        assert combat.play_card(0)

        assert blocked.get_power_amount(PowerId.DOOM) == 0
        assert blocked.get_power_amount(PowerId.WEAK) == 0
        assert hittable.get_power_amount(PowerId.DOOM) == 21
        assert hittable.get_power_amount(PowerId.WEAK) == 1

    def test_high_five_hits_and_debuffs_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.summon_osty(combat.player, 5)
        combat.hand = [make_high_five()]
        combat.energy = 2

        assert combat.play_card(0)

        assert blocked.current_hp == 100
        assert blocked.get_power_amount(PowerId.VULNERABLE) == 0
        assert hittable.current_hp == 89
        assert hittable.get_power_amount(PowerId.VULNERABLE) == 2

    def test_end_of_days_doom_kills_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 20
        hittable.current_hp = hittable.max_hp = 20
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.hand = [make_end_of_days()]
        combat.energy = 3

        assert combat.play_card(0)

        assert blocked.is_alive
        assert blocked.get_power_amount(PowerId.DOOM) == 0
        assert hittable.is_dead

    def test_countdown_doom_uses_owner_applier_for_shroud(self):
        combat = _make_combat()
        player = combat.player
        enemy = combat.enemies[0]
        player.apply_power(PowerId.SHROUD, 4)
        player.apply_power(PowerId.COUNTDOWN, 5)

        fire_after_side_turn_start(CombatSide.PLAYER, combat)

        assert enemy.get_power_amount(PowerId.DOOM) == 5
        assert player.block == 4

    def test_countdown_random_target_uses_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        hittable, blocked = combat.enemies
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.apply_power_to(combat.player, PowerId.COUNTDOWN, 5)

        fire_after_side_turn_start(CombatSide.PLAYER, combat)

        assert blocked.get_power_amount(PowerId.DOOM) == 0
        assert hittable.get_power_amount(PowerId.DOOM) == 5

    def test_neurosurge_doom_uses_owner_applier_for_shroud(self):
        combat = _make_combat()
        player = combat.player
        player.apply_power(PowerId.SHROUD, 4)
        player.apply_power(PowerId.NEUROSURGE, 3)

        fire_after_side_turn_start(CombatSide.PLAYER, combat)

        assert player.get_power_amount(PowerId.DOOM) == 3
        assert player.block == 4

    def test_neurosurge_gains_energy_before_drawing_void(self):
        """Matches Neurosurge.cs: gain energy before Draw, so drawn Void removes one."""
        combat = _make_combat()
        combat.hand = [make_neurosurge()]
        combat.draw_pile = [make_void()]
        combat.energy = 0

        assert combat.play_card(0)

        assert combat.energy == 2
        assert combat.player.get_power_amount(PowerId.NEUROSURGE) == 3

    def test_reaper_form_doom_uses_owner_applier_for_shroud(self):
        combat = _make_combat()
        player = combat.player
        enemy = combat.enemies[0]
        player.apply_power(PowerId.SHROUD, 2)
        player.apply_power(PowerId.REAPER_FORM, 1)

        combat.deal_damage(dealer=player, target=enemy, amount=5, props=ValueProp.MOVE)

        assert enemy.get_power_amount(PowerId.DOOM) == 5
        assert player.block == 2

    def test_reaper_form_doom_counts_blocked_damage(self):
        combat = _make_combat()
        player = combat.player
        enemy = combat.enemies[0]
        enemy.block = 3
        player.apply_power(PowerId.REAPER_FORM, 2)

        combat.deal_damage(dealer=player, target=enemy, amount=5, props=ValueProp.MOVE)

        assert enemy.get_power_amount(PowerId.DOOM) == 10

    def test_necro_mastery_damage_hits_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.summon_osty(combat.player, 5)
        osty = combat.get_osty(combat.player)
        assert osty is not None
        combat.apply_power_to(combat.player, PowerId.NECRO_MASTERY, 2)

        combat.deal_damage(dealer=blocked, target=osty, amount=3, props=ValueProp.MOVE)

        assert blocked.current_hp == 100
        assert hittable.current_hp == 94

    def test_necro_mastery_triggers_when_osty_is_killed_by_hit(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.summon_osty(combat.player, 5)
        osty = combat.get_osty(combat.player)
        assert osty is not None
        combat.apply_power_to(combat.player, PowerId.NECRO_MASTERY, 2)

        combat.deal_damage(dealer=blocked, target=osty, amount=5, props=ValueProp.MOVE)

        assert osty.is_dead
        assert blocked.current_hp == 100
        assert hittable.current_hp == 90

    def test_necro_mastery_triggers_when_osty_is_directly_killed(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.summon_osty(combat.player, 5)
        osty = combat.get_osty(combat.player)
        assert osty is not None
        combat.apply_power_to(combat.player, PowerId.NECRO_MASTERY, 2)

        assert combat.kill_osty(combat.player)

        assert osty.is_dead
        assert blocked.current_hp == 100
        assert hittable.current_hp == 90

    def test_oblivion_records_cards_before_triggering_doom(self):
        combat = _make_combat()
        player = combat.player
        enemy = combat.enemies[0]
        player.apply_power(PowerId.SHROUD, 2)
        combat.hand = [create_card(CardId.OBLIVION)]
        combat.energy = 0

        assert combat.play_card(0, 0)
        assert enemy.get_power_amount(PowerId.OBLIVION) == 3
        assert enemy.get_power_amount(PowerId.DOOM) == 0
        assert player.block == 0

        combat.hand = [make_soul()]
        combat.draw_pile = []

        assert combat.play_card(0)
        assert enemy.get_power_amount(PowerId.DOOM) == 3
        assert player.block == 2

    def test_pagestorm_draws_extra_when_ethereal_card_is_drawn(self):
        combat = _make_combat()
        soul = make_soul()
        soul.keywords = frozenset(set(soul.keywords) | {"ethereal"})
        extra = make_defend_necrobinder()
        combat.hand = [make_pagestorm()]
        combat.draw_pile = [soul, extra]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.PAGESTORM) == 1

        combat.draw_cards(combat.player, 1)
        assert soul in combat.hand
        assert extra in combat.hand

    def test_sculpting_strike_attacks_then_makes_selected_hand_card_ethereal(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        starting_hp = enemy.current_hp
        target_card = make_defend_necrobinder()
        combat.hand = [make_sculpting_strike(), target_card]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 8
        assert combat.pending_choice is None
        assert target_card.is_ethereal

    def test_sentry_mode_generates_sweeping_gaze_next_turn(self):
        combat = _make_combat()
        combat.hand = [make_sentry_mode()]
        combat.energy = 2

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.SENTRY_MODE) == 1

        combat.end_player_turn()
        assert any(card.card_id == CardId.SWEEPING_GAZE for card in combat.hand)

    def test_unleash_uses_osty_current_hp_in_damage_formula(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        combat.hand = [make_bodyguard(), make_unleash()]
        combat.energy = 2

        assert combat.play_card(0)
        osty = combat.get_osty(combat.player)
        assert osty is not None
        osty.current_hp = 4
        starting_hp = enemy.current_hp

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 10

    def test_upgraded_invoke_applies_upgraded_summon_and_energy_next_turn(self):
        combat = _make_combat()
        combat.hand = [make_invoke(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.SUMMON_NEXT_TURN) == 3
        assert combat.player.get_power_amount(PowerId.ENERGY_NEXT_TURN) == 3

    def test_poke_uses_osty_damage_and_records_osty_dealer(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        combat.summon_osty(combat.player, 5)
        osty = combat.get_osty(combat.player)
        assert osty is not None
        starting_hp = enemy.current_hp
        combat.hand = [make_poke(upgraded=True)]

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 9
        assert combat.count_powered_hits_by_dealer_this_turn(osty) == 1
        assert combat.count_powered_hits_by_dealer_this_turn(combat.player) == 0

    def test_fetch_uses_osty_damage_and_records_osty_dealer(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        combat.summon_osty(combat.player, 5)
        osty = combat.get_osty(combat.player)
        assert osty is not None
        starting_hp = enemy.current_hp
        combat.hand = [make_fetch(upgraded=True)]
        combat.draw_pile = [make_soul()]

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 6
        assert combat.count_powered_hits_by_dealer_this_turn(osty) == 1

    def test_friendship_lowers_strength_and_grants_friendship_power(self):
        combat = _make_combat()
        combat.hand = [make_friendship()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.STRENGTH) == -2
        assert combat.player.get_power_amount(PowerId.FRIENDSHIP) == 1

    def test_upgraded_friendship_lowers_strength_by_reduced_amount(self):
        combat = _make_combat()
        combat.hand = [make_friendship(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.STRENGTH) == -1
        assert combat.player.get_power_amount(PowerId.FRIENDSHIP) == 1

    def test_sic_em_uses_osty_damage_and_power_values(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        combat.summon_osty(combat.player, 5)
        osty = combat.get_osty(combat.player)
        assert osty is not None
        starting_hp = enemy.current_hp
        combat.hand = [make_sic_em(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 6
        assert combat.count_powered_hits_by_dealer_this_turn(osty) == 1
        assert enemy.get_power_amount(PowerId.SIC_EM) == 3

    def test_sic_em_summons_even_when_osty_damage_is_fully_blocked(self):
        combat = _make_combat()
        player = combat.player
        enemy = combat.enemies[0]
        enemy.block = 10
        combat.summon_osty(player, 5)
        osty = combat.get_osty(player)
        assert osty is not None
        combat.apply_power_to(enemy, PowerId.SIC_EM, 3, applier=player)
        starting_max_hp = osty.max_hp

        combat.deal_damage(dealer=osty, target=enemy, amount=2, props=ValueProp.MOVE)

        assert enemy.current_hp == enemy.max_hp
        assert osty.max_hp == starting_max_hp + 3

    def test_veilpiercer_makes_ethereal_cards_cost_zero_then_ticks_down_on_play(self):
        combat = _make_combat()
        ethereal = make_defend_necrobinder()
        ethereal.keywords = frozenset(set(ethereal.keywords) | {"ethereal"})
        combat.hand = [make_veilpiercer(), ethereal]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert combat.player.get_power_amount(PowerId.VEILPIERCER) == 1

        assert combat.can_play_card(ethereal) is True
        assert combat.play_card(0, 0)
        assert combat.player.get_power_amount(PowerId.VEILPIERCER) == 0

    def test_banshees_cry_cost_drops_for_ethereal_cards_played_this_combat(self):
        combat = _make_combat()
        held = make_banshees_cry()
        later = make_banshees_cry()
        combat.hand = [make_fear(), held, make_fear()]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert held.cost == 4

        assert combat.play_card(1, 0)
        assert held.cost == 2

        combat.move_card_to_creature_hand(combat.player, later)
        assert later.cost == 2
        held.end_of_turn_cleanup()
        later.end_of_turn_cleanup()
        assert held.cost == 2
        assert later.cost == 2

    def test_flatten_uses_osty_damage_and_makes_other_flatten_free_this_turn(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.summon_osty(combat.player, 5)
        osty = combat.get_osty(combat.player)
        assert osty is not None
        other_flatten = make_flatten(upgraded=True)
        combat.hand = [make_flatten(), other_flatten]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 88
        assert combat.count_powered_hits_by_dealer_this_turn(osty) == 1
        assert other_flatten.cost == 0

    def test_flatten_entering_after_osty_attack_is_free_this_turn(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.summon_osty(combat.player, 5)
        osty = combat.get_osty(combat.player)
        assert osty is not None

        combat.deal_damage(osty, enemy, 4, ValueProp.MOVE)
        flatten = make_flatten()
        combat.move_card_to_creature_hand(combat.player, flatten)

        assert flatten.cost == 0
