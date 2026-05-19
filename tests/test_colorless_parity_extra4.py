"""Additional focused parity tests for remaining Colorless cards."""

import sts2_env.powers  # noqa: F401

from sts2_env.cards.base import CardInstance
from sts2_env.cards.colorless import (
    make_beacon_of_hope,
    make_catastrophe,
    make_coordinate_card,
    make_dark_shackles,
    make_equilibrium,
    make_eternal_armor,
    make_finesse,
    make_fisticuffs,
    make_gold_axe,
    make_hidden_gem,
    make_impatience,
    make_intercept_card,
    make_jackpot,
    make_prep_time,
    make_production,
    make_prolong,
    make_prowess,
    make_rend,
    make_salvo,
)
from sts2_env.cards.ironclad import create_ironclad_starter_deck
from sts2_env.cards.ironclad_basic import make_defend_ironclad, make_strike_ironclad
from sts2_env.core.combat import CombatState
from sts2_env.core.enums import CardId, CardRarity, CardType, CombatSide, PowerId, TargetType, ValueProp
from sts2_env.core.hooks import fire_after_turn_end
from sts2_env.core.rng import Rng
from sts2_env.monsters.act1_weak import create_shrinker_beetle
from sts2_env.run.run_state import PlayerState


def _make_combat() -> CombatState:
    combat = CombatState(
        player_hp=80,
        player_max_hp=80,
        deck=create_ironclad_starter_deck(),
        rng_seed=4242,
        character_id="Ironclad",
    )
    creature, ai = create_shrinker_beetle(Rng(4242))
    combat.add_enemy(creature, ai)
    combat.start_combat()
    return combat


class TestColorlessParityExtra4:
    def test_catastrophe_autoplays_two_draw_pile_cards_preferring_playable(self):
        combat = _make_combat()
        first = make_strike_ironclad()
        second = make_defend_ironclad()
        combat.hand = [make_catastrophe()]
        combat.draw_pile = [first, second]
        combat.energy = 2

        assert combat.play_card(0)

        assert first in combat.discard_pile
        assert second in combat.discard_pile
        assert combat.draw_pile == []

    def test_eternal_armor_applies_plating(self):
        combat = _make_combat()
        combat.hand = [make_eternal_armor()]
        combat.energy = 3

        assert combat.play_card(0)

        assert combat.player.get_power_amount(PowerId.PLATING) == 7

    def test_jackpot_deals_damage_and_adds_three_zero_cost_cards(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = enemy.max_hp = 100
        combat.hand = [make_jackpot()]
        combat.energy = 3

        assert combat.play_card(0, 0)

        assert enemy.current_hp == 75
        assert len(combat.hand) == 3
        assert all(card.cost == 0 and not card.has_energy_cost_x for card in combat.hand)

    def test_upgraded_jackpot_upgrades_generated_cards(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = enemy.max_hp = 100
        combat.hand = [make_jackpot(upgraded=True)]
        combat.energy = 3

        assert combat.play_card(0, 0)

        assert enemy.current_hp == 70
        assert len(combat.hand) == 3
        assert all(card.upgraded for card in combat.hand)

    def test_prep_time_applies_start_of_turn_vigor_power(self):
        combat = _make_combat()
        combat.hand = [make_prep_time()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.PREP_TIME) == 4

        combat.end_player_turn()

        assert combat.player.get_power_amount(PowerId.VIGOR) == 4

    def test_prowess_grants_strength_and_dexterity(self):
        combat = _make_combat()
        combat.hand = [make_prowess()]
        combat.energy = 1

        assert combat.play_card(0)

        assert combat.player.get_power_amount(PowerId.STRENGTH) == 1
        assert combat.player.get_power_amount(PowerId.DEXTERITY) == 1

    def test_salvo_deals_damage_and_retains_remaining_hand(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        starting_hp = enemy.current_hp
        retained = make_strike_ironclad()
        combat.hand = [make_salvo(), retained]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 12
        assert combat.player.get_power_amount(PowerId.RETAIN_HAND) == 1

        combat.end_player_turn()

        assert retained in combat.hand

    def test_dark_shackles_applies_temporary_strength_loss_then_restores(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.apply_power(PowerId.STRENGTH, 5)
        combat.hand = [make_dark_shackles()]
        combat.energy = 0

        assert combat.play_card(0, 0)
        assert enemy.get_power_amount(PowerId.STRENGTH) == -4
        assert enemy.get_power_amount(PowerId.DARK_SHACKLES) == 9

        fire_after_turn_end(CombatSide.ENEMY, combat)
        assert enemy.get_power_amount(PowerId.STRENGTH) == 5
        assert enemy.get_power_amount(PowerId.DARK_SHACKLES) == 0

    def test_equilibrium_gains_block_and_retains_remaining_hand(self):
        combat = _make_combat()
        retained = make_strike_ironclad()
        combat.hand = [make_equilibrium(), retained]
        combat.energy = 2

        assert combat.play_card(0)
        assert combat.player.block == 13
        assert combat.player.get_power_amount(PowerId.RETAIN_HAND) == 1

        combat.end_player_turn()
        assert retained in combat.hand

    def test_impatience_draws_only_when_no_attack_remains_in_hand(self):
        combat = _make_combat()
        skill_draw = make_defend_ironclad()
        combat.hand = [make_impatience()]
        combat.draw_pile = [skill_draw]
        combat.energy = 0

        assert combat.play_card(0)
        assert skill_draw in combat.hand

        combat = _make_combat()
        attack = make_strike_ironclad()
        skill_draw = make_defend_ironclad()
        combat.hand = [make_impatience(), attack]
        combat.draw_pile = [skill_draw]
        combat.energy = 0

        assert combat.play_card(0)
        assert skill_draw not in combat.hand
        assert combat.draw_pile[0] is skill_draw

    def test_intercept_grants_block_and_covered_to_target_ally(self):
        combat = _make_combat()
        ally = combat.add_ally_player(
            PlayerState(player_id=2, character_id="Ironclad", max_hp=60, current_hp=60)
        )
        ally_state = combat.combat_player_state_for(ally)
        assert ally_state is not None

        card = make_intercept_card()
        card.owner = ally
        ally_state.hand = [card]
        ally_state.zone_map["hand"] = ally_state.hand
        ally_state.energy = 1

        assert combat.play_card_from_creature(ally, 0, 0)
        assert ally.block == 9
        assert combat.primary_player.block == 0
        assert combat.primary_player.get_power_amount(PowerId.COVERED) == 1
        intercept = ally.powers.get(PowerId.INTERCEPT)
        assert intercept is not None
        assert getattr(intercept, "_covered_creatures", []) == [combat.primary_player]

        enemy = combat.enemies[0]
        hp_before = combat.primary_player.current_hp
        combat.primary_player.block = 0
        combat.deal_damage(enemy, combat.primary_player, 10, ValueProp.MOVE)
        assert combat.primary_player.current_hp == hp_before

    def test_production_base_exhausts_and_upgrade_does_not(self):
        combat = _make_combat()
        base = make_production()
        upgraded = make_production(upgraded=True)
        combat.hand = [base, upgraded]
        combat.energy = 0

        assert combat.play_card(0)
        assert combat.energy == 2
        assert any(card.card_id == base.card_id for card in combat.exhaust_pile)

        assert combat.play_card(0)
        assert combat.energy == 4
        assert any(card.card_id == upgraded.card_id for card in combat.discard_pile)

    def test_prolong_carries_current_block_to_next_player_turn(self):
        combat = _make_combat()
        combat.player.gain_block(11)
        combat.hand = [make_prolong()]
        combat.energy = 0

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.BLOCK_NEXT_TURN) == 11

        combat.end_player_turn()
        assert combat.player.block == 11

    def test_rend_scales_damage_with_non_duration_debuff_count(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 200
        enemy.current_hp = 200
        combat.apply_power_to(enemy, PowerId.WEAK, 1)
        combat.apply_power_to(enemy, PowerId.FRAIL, 1)
        combat.hand = [make_rend()]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 175

    def test_rend_counts_negative_strength_but_ignores_temporary_debuffs(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 200
        enemy.current_hp = 200
        combat.apply_power_to(enemy, PowerId.STRENGTH, -2, applier=combat.player)
        combat.apply_power_to(enemy, PowerId.DARK_SHACKLES, 9, applier=combat.player)
        combat.hand = [make_rend()]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 180

    def test_rend_uses_normal_attack_damage_modifiers(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 200
        enemy.current_hp = 200
        combat.player.apply_power(PowerId.STRENGTH, 3)
        combat.hand = [make_rend()]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 182

    def test_gold_axe_scales_with_finished_owner_card_plays_only(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        ally = combat.add_ally_player(
            PlayerState(player_id=2, character_id="Ironclad", max_hp=60, current_hp=60)
        )
        ally_state = combat.combat_player_state_for(ally)
        assert ally_state is not None

        ally_strike = make_strike_ironclad()
        ally_strike.owner = ally
        ally_state.hand = [ally_strike]
        ally_state.zone_map["hand"] = ally_state.hand
        ally_state.energy = 1

        combat.hand = [make_strike_ironclad(), make_strike_ironclad(), make_gold_axe()]
        combat.energy = 3

        assert combat.play_card(0, 0)
        assert combat.play_card(0, 0)
        assert combat.play_card_from_creature(ally, 0, 0)
        before_gold_axe = enemy.current_hp

        assert combat.play_card(0, 0)
        assert enemy.current_hp == before_gold_axe - 2
        assert make_gold_axe(upgraded=True).is_retain

    def test_fisticuffs_block_uses_normal_block_modifiers(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.apply_power_to(combat.player, PowerId.DEXTERITY, 3)
        combat.apply_power_to(combat.player, PowerId.FRAIL, 1)
        combat.hand = [make_fisticuffs()]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == 93
        assert combat.player.block == 7

    def test_fisticuffs_does_not_gain_block_after_combat_ending(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = 7
        combat.hand = [make_fisticuffs()]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert combat.is_over
        assert combat.player.block == 0

    def test_beacon_of_hope_triggers_from_colorless_block_cards(self):
        combat = _make_combat()
        ally = combat.add_ally_player(
            PlayerState(player_id=2, character_id="Ironclad", max_hp=60, current_hp=60)
        )
        combat.hand = [make_beacon_of_hope(), make_finesse()]
        combat.draw_pile = []
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.play_card(0)
        assert combat.player.block == 4
        assert ally.block == 2

    def test_beacon_of_hope_triggers_from_fisticuffs_block(self):
        combat = _make_combat()
        ally = combat.add_ally_player(
            PlayerState(player_id=2, character_id="Ironclad", max_hp=60, current_hp=60)
        )
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        combat.hand = [make_beacon_of_hope(), make_fisticuffs()]
        combat.energy = 2

        assert combat.play_card(0)
        assert combat.play_card(0, 0)
        assert enemy.current_hp == 93
        assert combat.player.block == 7
        assert ally.block == 3

    def test_coordinate_applies_temporary_strength_to_target_ally_then_expires(self):
        combat = _make_combat()
        ally = combat.add_ally_player(
            PlayerState(player_id=2, character_id="Ironclad", max_hp=60, current_hp=60)
        )
        ally_state = combat.combat_player_state_for(ally)
        assert ally_state is not None

        card = make_coordinate_card(upgraded=True)
        card.owner = ally
        ally_state.hand = [card]
        ally_state.zone_map["hand"] = ally_state.hand
        ally_state.energy = 1

        assert combat.play_card_from_creature(ally, 0, 0)
        assert combat.primary_player.get_power_amount(PowerId.COORDINATE) == 8
        assert combat.primary_player.get_power_amount(PowerId.STRENGTH) == 8

        fire_after_turn_end(CombatSide.PLAYER, combat)
        assert combat.primary_player.get_power_amount(PowerId.COORDINATE) == 0
        assert combat.primary_player.get_power_amount(PowerId.STRENGTH) == 0

    def test_hidden_gem_does_not_apply_replay_to_curse_or_quest_cards(self):
        combat = _make_combat()
        curse = CardInstance(
            card_id=CardId.CURSE_OF_THE_BELL,
            cost=0,
            card_type=CardType.CURSE,
            target_type=TargetType.NONE,
            rarity=CardRarity.CURSE,
        )
        quest = CardInstance(
            card_id=CardId.SPOILS_MAP,
            cost=0,
            card_type=CardType.QUEST,
            target_type=TargetType.NONE,
            rarity=CardRarity.QUEST,
        )
        combat.hand = [make_hidden_gem()]
        combat.draw_pile = [curse, quest]
        combat.energy = 1

        assert combat.play_card(0)
        assert curse.base_replay_count == 0
        assert quest.base_replay_count == 0
