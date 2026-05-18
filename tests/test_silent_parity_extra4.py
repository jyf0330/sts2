"""Additional focused parity tests for remaining Silent cards."""

import sts2_env.cards.silent as silent_cards
import sts2_env.powers  # noqa: F401

from sts2_env.cards.silent import (
    make_blade_of_ink,
    make_bullet_time,
    make_cloak_and_dagger,
    make_dagger_spray,
    make_deflect,
    make_expose,
    make_finisher,
    make_flanking,
    make_follow_through,
    make_haze,
    make_hidden_daggers,
    make_infinite_blades,
    make_memento_mori,
    make_murder,
    make_pinpoint,
    make_poisoned_stab,
    make_precise_cut,
    make_skewer,
    make_slice,
    make_sucker_punch,
    make_defend_silent,
)
from sts2_env.cards.ironclad import create_ironclad_starter_deck
from sts2_env.cards.ironclad_basic import make_strike_ironclad
from sts2_env.core.combat import CombatState
from sts2_env.core.enums import CardId, CombatSide, PowerId
from sts2_env.core.hooks import fire_after_side_turn_start, fire_after_turn_end
from sts2_env.core.rng import Rng
from sts2_env.monsters.act1_weak import create_shrinker_beetle
from sts2_env.powers.base import PowerInstance


class _CannotHitPower(PowerInstance):
    def __init__(self):
        super().__init__(PowerId.COVERED, 1)

    def should_allow_hitting(self, owner, combat):
        return False


def _make_combat(*, extra_enemies: int = 0, seed: int = 4243) -> CombatState:
    combat = CombatState(
        player_hp=70,
        player_max_hp=70,
        deck=create_ironclad_starter_deck(),
        rng_seed=seed,
        character_id="Silent",
    )
    creature, ai = create_shrinker_beetle(Rng(seed))
    combat.add_enemy(creature, ai)
    for i in range(extra_enemies):
        extra_creature, extra_ai = create_shrinker_beetle(Rng(seed + 100 + i))
        combat.add_enemy(extra_creature, extra_ai)
    combat.start_combat()
    return combat


class TestSilentParityExtra4:
    def test_deflect_base_and_upgrade_block_values_match_reference(self):
        combat = _make_combat()
        from sts2_env.cards.silent import make_deflect as make_deflect_factory

        combat.hand = [make_deflect_factory(), make_deflect_factory(upgraded=True)]
        combat.energy = 0

        assert combat.play_card(0)
        assert combat.player.block == 4

        assert combat.play_card(0)
        assert combat.player.block == 11

    def test_cloak_and_dagger_grants_block_and_creates_expected_shivs(self):
        combat = _make_combat()
        combat.hand = [make_cloak_and_dagger(), make_cloak_and_dagger(upgraded=True)]
        combat.energy = 2

        assert combat.play_card(0)
        assert combat.player.block == 6
        assert sum(1 for card in combat.hand if card.card_id == CardId.SHIV) == 1

        assert combat.play_card(0)
        assert combat.player.block == 12
        assert sum(1 for card in combat.hand if card.card_id == CardId.SHIV) == 3

    def test_cloak_and_dagger_does_not_create_shiv_after_block_ends_combat(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = 5
        combat.player.apply_power(PowerId.JUGGERNAUT, 5)
        combat.hand = [make_cloak_and_dagger()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.is_over
        assert all(card.card_id != CardId.SHIV for card in combat.hand)

    def test_dagger_spray_hits_all_enemies_twice(self):
        combat = _make_combat(extra_enemies=1)
        starts = [enemy.current_hp for enemy in combat.enemies]
        combat.hand = [make_dagger_spray()]
        combat.energy = 1

        assert combat.play_card(0)
        total_damage = sum(before - enemy.current_hp for before, enemy in zip(starts, combat.enemies, strict=True))
        assert total_damage == 16

    def test_dagger_spray_finishes_current_aoe_hit_but_stops_next_hit_if_attacker_dies(self):
        combat = _make_combat(extra_enemies=1)
        first, second = combat.enemies
        first.current_hp = first.max_hp = 100
        second.current_hp = second.max_hp = 100
        first.apply_power(PowerId.THORNS, 5)
        combat.player.current_hp = 3
        combat.hand = [make_dagger_spray()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.current_hp == 0
        assert first.current_hp == 96
        assert second.current_hp == 96
        assert combat.is_over
        assert combat.player_won is False

    def test_haze_applies_poison_only_to_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.hand = [make_haze()]
        combat.energy = 3

        assert combat.play_card(0)
        assert blocked.get_power_amount(PowerId.POISON) == 0
        assert hittable.get_power_amount(PowerId.POISON) == 4

    def test_poisoned_stab_deals_damage_and_applies_poison(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_poisoned_stab(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 92
        assert enemy.get_power_amount(PowerId.POISON) == 4

    def test_slice_base_and_upgrade_damage_values_match_reference(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        from sts2_env.cards.silent import make_slice as make_slice_factory

        combat.hand = [make_slice_factory(), make_slice_factory(upgraded=True)]
        combat.energy = 0

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 94

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 85

    def test_sucker_punch_deals_damage_and_applies_weak(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_sucker_punch(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 90
        assert enemy.get_power_amount(PowerId.WEAK) == 2

    def test_finisher_hits_once_per_prior_attack_played_this_turn(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_finisher()]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 100

        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_slice(), make_slice(), make_finisher()]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert combat.play_card(0, 0)
        assert combat.play_card(0, 0)
        assert enemy.current_hp == 76

    def test_expose_removes_block_and_artifact_then_applies_vulnerable(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.block = 12
        enemy.apply_power(PowerId.ARTIFACT, 2)
        combat.hand = [make_expose(upgraded=True)]
        combat.energy = 0

        assert combat.play_card(0, 0)
        assert enemy.block == 0
        assert enemy.get_power_amount(PowerId.ARTIFACT) == 0
        assert enemy.get_power_amount(PowerId.VULNERABLE) == 3

    def test_flanking_applies_flanking_power_not_no_block(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        combat.hand = [make_flanking(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.get_power_amount(PowerId.FLANKING) == 2
        assert enemy.get_power_amount(PowerId.NO_BLOCK) == 0
        assert enemy.powers[PowerId.FLANKING].applier is combat.player

    def test_memento_mori_scales_with_cards_discarded_this_turn(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        first = make_defend_silent()
        second = make_strike_ironclad()
        card = make_memento_mori(upgraded=True)
        combat.hand = [first, second, card]
        combat.energy = 1

        combat.discard_cards([first, second])

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 80

    def test_precise_cut_loses_damage_for_each_other_card_in_hand(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_precise_cut(), make_defend_silent(), make_strike_ironclad()]
        combat.energy = 0

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 91

    def test_follow_through_only_applies_weak_after_owner_skill(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_follow_through(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0)
        assert enemy.current_hp == 92
        assert enemy.get_power_amount(PowerId.WEAK) == 0

        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_deflect(), make_follow_through(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.play_card(0)
        assert enemy.current_hp == 92
        assert enemy.get_power_amount(PowerId.WEAK) == 2

    def test_murder_scales_with_cards_drawn_this_combat(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        card = make_murder(upgraded=True)
        combat.hand = [card]
        combat.draw_pile = [make_defend_silent(), make_strike_ironclad()]
        combat.exhaust_pile = [make_slice() for _ in range(4)]
        combat.energy = 2

        before_draws = combat.count_cards_drawn_this_combat(combat.player)
        combat.draw_cards(combat.player, 2)

        assert card.cost == 2
        assert combat.play_card(0, 0)
        assert enemy.current_hp == 100 - before_draws - 2

    def test_upgraded_hidden_daggers_creates_upgraded_shivs(self):
        combat = _make_combat()
        combat.hand = [make_hidden_daggers(upgraded=True)]
        combat.energy = 0

        assert combat.play_card(0)
        shivs = [card for card in combat.hand if card.card_id == CardId.SHIV]
        assert len(shivs) == 2
        assert all(card.upgraded and card.base_damage == 6 for card in shivs)

    def test_upgraded_infinite_blades_is_innate(self):
        assert not make_infinite_blades().is_innate
        assert make_infinite_blades(upgraded=True).is_innate

    def test_fan_of_knives_creates_reference_shiv_counts(self):
        combat = _make_combat()
        combat.hand = [silent_cards.make_fan_of_knives(upgraded=True)]
        combat.energy = 2

        assert combat.play_card(0)
        shivs = [card for card in combat.hand if card.card_id == CardId.SHIV]
        assert len(shivs) == 5
        assert combat.player.get_power_amount(PowerId.FAN_OF_KNIVES) == 1

    def test_shiv_hits_all_enemies_while_fan_of_knives_is_active(self):
        combat = _make_combat(extra_enemies=1)
        for enemy in combat.enemies:
            enemy.max_hp = 100
            enemy.current_hp = 100
        combat.hand = [silent_cards.make_fan_of_knives()]
        combat.energy = 2

        assert combat.play_card(0)
        shiv_index = next(i for i, card in enumerate(combat.hand) if card.card_id == CardId.SHIV)
        assert combat.play_card(shiv_index, 0)
        assert [enemy.current_hp for enemy in combat.enemies] == [96, 96]

    def test_upgraded_storm_of_steel_discards_hand_and_creates_upgraded_shivs(self):
        combat = _make_combat()
        first = make_defend_silent()
        second = make_strike_ironclad()
        combat.hand = [silent_cards.make_storm_of_steel(upgraded=True), first, second]
        combat.energy = 1

        assert combat.play_card(0)
        shivs = [card for card in combat.hand if card.card_id == CardId.SHIV]
        assert len(shivs) == 2
        assert all(card.upgraded and card.base_damage == 6 for card in shivs)
        assert first in combat.discard_pile
        assert second in combat.discard_pile
        assert combat.count_cards_discarded_this_turn(combat.player) == 2

    def test_knife_trap_only_replays_exhausted_shivs_and_upgrades_them(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        shiv = silent_cards._make_shiv()
        non_shiv = make_defend_silent()
        combat.exhaust_pile = [shiv, non_shiv]
        combat.hand = [silent_cards.make_knife_trap(upgraded=True)]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 94
        assert shiv.upgraded
        assert non_shiv.upgraded is False

    def test_tracking_adds_two_first_then_one_when_already_active(self):
        combat = _make_combat()
        combat.hand = [silent_cards.make_tracking(), silent_cards.make_tracking()]
        combat.energy = 4

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.TRACKING) == 2
        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.TRACKING) == 3

    def test_echoing_slash_repeats_once_for_each_enemy_killed(self):
        combat = _make_combat(extra_enemies=2)
        combat.enemies[0].current_hp = 5
        combat.enemies[0].max_hp = 5
        combat.enemies[1].current_hp = 5
        combat.enemies[1].max_hp = 5
        combat.enemies[2].current_hp = 100
        combat.enemies[2].max_hp = 100
        combat.hand = [silent_cards.make_echoing_slash()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.enemies[0].is_dead
        assert combat.enemies[1].is_dead
        assert combat.enemies[2].current_hp == 70

    def test_up_my_sleeve_reduces_its_own_cost_this_combat(self):
        combat = _make_combat()
        card = silent_cards.make_up_my_sleeve()
        combat.hand = [card]
        combat.energy = 2

        assert combat.play_card(0)
        assert card.cost == 1
        shivs = [card for card in combat.hand if card.card_id == CardId.SHIV]
        assert len(shivs) == 3
        assert all(shiv.cost == 0 for shiv in shivs)

    def test_master_planner_permanently_adds_sly_to_played_skills(self):
        combat = _make_combat()
        skill = make_defend_silent()
        combat.hand = [silent_cards.make_master_planner(), skill]
        combat.energy = 3

        assert combat.play_card(0)
        assert combat.play_card(0)
        assert "sly" in skill.keywords
        assert skill in combat.discard_pile

    def test_phantom_blades_adds_retain_to_existing_shivs(self):
        combat = _make_combat()
        shiv = silent_cards._make_shiv()
        combat.hand = [shiv, silent_cards.make_phantom_blades()]
        combat.energy = 1

        assert combat.play_card(1)
        assert shiv.is_retain

    def test_corrosive_wave_poison_uses_owner_applier_triggers_outbreak(self):
        combat = _make_combat(extra_enemies=2)
        for enemy in combat.enemies:
            enemy.max_hp = 100
            enemy.current_hp = 100
        combat.apply_power_to(combat.player, PowerId.OUTBREAK, 11)
        combat.apply_power_to(combat.player, PowerId.CORROSIVE_WAVE, 3)
        combat.draw_pile = [make_defend_silent()]
        combat.hand = []

        combat.draw_cards(combat.player, 1)

        assert [enemy.get_power_amount(PowerId.POISON) for enemy in combat.enemies] == [3, 3, 3]
        assert [enemy.current_hp for enemy in combat.enemies] == [89, 89, 89]

    def test_corrosive_wave_applies_poison_only_to_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.apply_power_to(combat.player, PowerId.CORROSIVE_WAVE, 3)
        combat.draw_pile = [make_defend_silent()]
        combat.hand = []

        combat.draw_cards(combat.player, 1)

        assert blocked.get_power_amount(PowerId.POISON) == 0
        assert hittable.get_power_amount(PowerId.POISON) == 3

    def test_noxious_fumes_applies_poison_only_to_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.hand = [silent_cards.make_noxious_fumes()]
        combat.energy = 1

        assert combat.play_card(0)
        fire_after_side_turn_start(CombatSide.PLAYER, combat)

        assert blocked.get_power_amount(PowerId.POISON) == 0
        assert hittable.get_power_amount(PowerId.POISON) == 2

    def test_outbreak_damage_hits_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.max_hp = blocked.current_hp = 100
        hittable.max_hp = hittable.current_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.apply_power_to(combat.player, PowerId.OUTBREAK, 11)

        for _ in range(3):
            combat.apply_power_to(hittable, PowerId.POISON, 1, applier=combat.player)

        assert blocked.current_hp == 100
        assert hittable.current_hp == 89

    def test_speedster_damage_hits_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.max_hp = blocked.current_hp = 100
        hittable.max_hp = hittable.current_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.apply_power_to(combat.player, PowerId.SPEEDSTER, 2)
        combat.draw_pile = [make_defend_silent()]
        combat.hand = []

        combat.draw_cards(combat.player, 1)

        assert blocked.current_hp == 100
        assert hittable.current_hp == 98

    def test_envenom_poison_uses_owner_applier_triggers_outbreak(self):
        combat = _make_combat(extra_enemies=2)
        for enemy in combat.enemies:
            enemy.max_hp = 100
            enemy.current_hp = 100
        combat.apply_power_to(combat.player, PowerId.OUTBREAK, 11)
        combat.hand = [silent_cards.make_envenom(), make_dagger_spray()]
        combat.energy = 3

        assert combat.play_card(0)
        assert combat.play_card(0)
        assert [enemy.get_power_amount(PowerId.POISON) for enemy in combat.enemies] == [2, 2, 2]
        assert [enemy.current_hp for enemy in combat.enemies] == [70, 70, 70]

    def test_bubble_bubble_only_adds_poison_to_already_poisoned_target(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        combat.hand = [
            silent_cards.make_bubble_bubble(upgraded=True),
            silent_cards.make_bubble_bubble(upgraded=True),
        ]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert enemy.get_power_amount(PowerId.POISON) == 0

        combat.apply_power_to(enemy, PowerId.POISON, 1)

        assert combat.play_card(0, 0)
        assert enemy.get_power_amount(PowerId.POISON) == 13

    def test_silent_upgrade_factory_values_match_reference_batch(self):
        assert silent_cards.make_acrobatics(upgraded=True).effect_vars["cards"] == 4
        assert silent_cards.make_backflip(upgraded=True).base_block == 8
        assert silent_cards.make_blade_dance(upgraded=True).effect_vars["cards"] == 4
        assert silent_cards.make_dagger_throw(upgraded=True).base_damage == 12
        assert silent_cards.make_deadly_poison(upgraded=True).effect_vars["poison_power"] == 7
        assert silent_cards.make_dodge_and_roll(upgraded=True).base_block == 6
        assert silent_cards.make_prepared(upgraded=True).effect_vars["cards"] == 2
        assert silent_cards.make_snakebite(upgraded=True).effect_vars["poison_power"] == 10
        assert silent_cards.make_accuracy(upgraded=True).effect_vars["accuracy_power"] == 6
        assert silent_cards.make_backstab(upgraded=True).base_damage == 15
        assert silent_cards.make_calculated_gamble(upgraded=True).is_retain
        assert silent_cards.make_afterimage(upgraded=True).is_innate
        assert silent_cards.make_bullet_time(upgraded=True).cost == 2
        assert silent_cards.make_master_planner(upgraded=True).cost == 1
        assert silent_cards.make_nightmare(upgraded=True).cost == 2
        assert silent_cards.make_tools_of_the_trade(upgraded=True).cost == 0
        assert silent_cards.make_tracking(upgraded=True).cost == 1
        assert silent_cards.make_wraith_form(upgraded=True).effect_vars["intangible_power"] == 3

    def test_bullet_time_sets_non_x_hand_cards_to_zero_and_applies_no_draw(self):
        combat = _make_combat()
        strike = make_strike_ironclad()
        combat.hand = [make_bullet_time(), strike]
        combat.energy = 3

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.NO_DRAW) == 1
        assert strike.cost == 0

    def test_blade_of_ink_grants_temporary_strength_for_attack_plays_only(self):
        combat = _make_combat()
        strike = make_strike_ironclad()
        combat.hand = [make_blade_of_ink(), strike, make_deflect()]
        combat.energy = 2

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.BLADE_OF_INK) == 2

        assert combat.play_card(0, 0)
        assert combat.player.get_power_amount(PowerId.STRENGTH) == 2

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.STRENGTH) == 2

        fire_after_turn_end(CombatSide.PLAYER, combat)
        assert combat.player.get_power_amount(PowerId.STRENGTH) == 0

    def test_pinpoint_cost_drops_for_owner_skills_played_this_turn(self):
        combat = _make_combat()
        pinpoint = make_pinpoint()
        combat.hand = [make_deflect(), make_deflect()]
        combat.energy = 0

        assert combat.play_card(0)
        combat.move_card_to_creature_hand(combat.player, pinpoint)
        assert pinpoint.cost == 2

        assert combat.play_card(0)
        assert pinpoint.cost == 1

    def test_skewer_uses_full_x_value_and_allows_zero_energy_play(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_skewer()]
        combat.energy = 3

        assert combat.play_card(0, 0)
        assert combat.energy == 0
        assert enemy.current_hp == 79

        zero = make_skewer()
        combat.hand = [zero]
        combat.energy = 0
        hp_before = enemy.current_hp

        assert combat.can_play_card(zero) is True
        assert combat.play_card(0, 0)
        assert enemy.current_hp == hp_before
