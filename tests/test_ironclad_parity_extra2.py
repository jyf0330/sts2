"""Additional Ironclad parity tests for high-signal card mechanics."""

import sts2_env.powers  # noqa: F401

from sts2_env.cards.ironclad import (
    make_ashen_strike,
    create_ironclad_starter_deck,
    make_battle_trance,
    make_bash,
    make_bloodletting,
    make_bully,
    make_feel_no_pain,
    make_fiend_fire,
    make_inflame,
    make_juggernaut,
    make_perfected_strike,
    make_pommel_strike,
    make_rage,
    make_rampage,
    make_twin_strike,
)
from sts2_env.cards.ironclad_basic import make_defend_ironclad, make_strike_ironclad
from sts2_env.core.combat import CombatState
from sts2_env.core.enums import PowerId
from sts2_env.core.rng import Rng
from sts2_env.monsters.act1_weak import create_shrinker_beetle


def _make_combat() -> CombatState:
    combat = CombatState(
        player_hp=80,
        player_max_hp=80,
        deck=create_ironclad_starter_deck(),
        rng_seed=84,
        character_id="Ironclad",
    )
    creature, ai = create_shrinker_beetle(Rng(84))
    combat.add_enemy(creature, ai)
    combat.start_combat()
    return combat


class TestIroncladParityExtra2:
    def test_dynamic_damage_upgrades_only_increase_extra_damage(self):
        """Matches PerfectedStrike/AshenStrike/Bully: upgrade increases ExtraDamage, not CalculationBase."""
        assert make_perfected_strike(upgraded=True).effect_vars == {
            "calc_base": 6,
            "extra_damage": 3,
        }
        assert make_ashen_strike(upgraded=True).effect_vars == {
            "calc_base": 6,
            "extra_damage": 4,
        }
        assert make_bully(upgraded=True).effect_vars == {
            "calc_base": 4,
            "extra_damage": 3,
        }

    def test_battle_trance_draws_then_applies_no_draw_for_future_draws(self):
        """Matches BattleTrance.cs: draw first, then apply No Draw for later non-hand draws."""
        combat = _make_combat()
        draw_a = make_strike_ironclad()
        draw_b = make_defend_ironclad()
        draw_c = make_inflame()
        draw_d = make_rampage()
        combat.hand = [make_battle_trance()]
        combat.draw_pile = [draw_a, draw_b, draw_c, draw_d]
        combat.energy = 0

        assert combat.play_card(0)
        assert len(combat.hand) == 3
        assert draw_a in combat.hand
        assert draw_b in combat.hand
        assert draw_c in combat.hand
        assert combat.player.get_power_amount(PowerId.NO_DRAW) == 1

        combat.draw_cards(combat.player, 1)
        assert len(combat.hand) == 3
        assert combat.draw_pile[0] is draw_d

    def test_bloodletting_is_unblockable_self_hp_loss_then_energy_gain(self):
        """Matches Bloodletting.cs: lose 3 HP (unblockable/unpowered) and gain 2 energy."""
        combat = _make_combat()
        start_hp = combat.player.current_hp
        combat.player.gain_block(20)
        combat.hand = [make_bloodletting()]
        combat.energy = 0

        assert combat.play_card(0)
        assert combat.player.current_hp == start_hp - 3
        assert combat.player.block == 20
        assert combat.energy == 2

    def test_pommel_strike_deals_damage_and_draws_one(self):
        """Matches PommelStrike.cs: attack target, then draw the configured number of cards."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        start_hp = enemy.current_hp
        drawn = make_inflame()
        combat.hand = [make_pommel_strike()]
        combat.draw_pile = [drawn]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == start_hp - 9
        assert len(combat.hand) == 1
        assert combat.hand[0] is drawn

    def test_pommel_strike_does_not_draw_after_ending_combat(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = 9
        enemy.max_hp = 9
        drawn = make_inflame()
        combat.hand = [make_pommel_strike()]
        combat.draw_pile = [drawn]
        combat.energy = 1

        assert combat.play_card(0, 0)

        assert combat.is_over
        assert combat.hand == []
        assert combat.draw_pile == [drawn]

    def test_bash_does_not_apply_vulnerable_after_ending_combat(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = 8
        enemy.max_hp = 8
        combat.hand = [make_bash()]
        combat.energy = 2

        assert combat.play_card(0, 0)

        assert combat.is_over
        assert enemy.get_power_amount(PowerId.VULNERABLE) == 0

    def test_bash_does_not_apply_vulnerable_to_removed_target_while_combat_continues(self):
        combat = _make_combat()
        first = combat.enemies[0]
        second, second_ai = create_shrinker_beetle(Rng(85))
        combat.add_enemy(second, second_ai)
        first.current_hp = 8
        first.max_hp = 8
        second.current_hp = 30
        second.max_hp = 30
        combat.hand = [make_bash()]
        combat.energy = 2

        assert combat.play_card(0, 0)

        assert not combat.is_over
        assert first.escaped
        assert first.get_power_amount(PowerId.VULNERABLE) == 0
        assert second.get_power_amount(PowerId.VULNERABLE) == 0

    def test_inflame_applies_strength_power_amount(self):
        """Matches Inflame.cs: apply StrengthPower using the configured amount."""
        combat = _make_combat()
        combat.hand = [make_inflame(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.STRENGTH) == 3

    def test_perfected_strike_counts_all_strike_cards_including_itself(self):
        """Matches PerfectedStrike.cs: scale from all owner strike cards in combat state."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        start_hp = enemy.current_hp
        perfected = make_perfected_strike()
        combat.hand = [perfected, make_pommel_strike(), make_inflame()]
        combat.draw_pile = [make_strike_ironclad()]
        combat.discard_pile = [make_strike_ironclad()]
        combat.exhaust_pile = [make_strike_ironclad()]
        combat.play_pile = []
        combat.energy = 2

        assert combat.play_card(0, 0)
        # Strikes: Perfected Strike itself + Pommel Strike + draw + discard + exhaust = 5.
        assert enemy.current_hp == start_hp - 16

    def test_rampage_increases_its_own_base_damage_each_play(self):
        """Matches Rampage.cs: card mutates its own base damage after each play."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        start_hp = enemy.current_hp
        rampage = make_rampage()
        combat.hand = [rampage]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert enemy.current_hp == start_hp - 9
        assert rampage.base_damage == 14

        combat.hand = [combat.discard_pile.pop(0)]
        assert combat.play_card(0, 0)
        assert enemy.current_hp == start_hp - 23
        assert rampage.base_damage == 19

    def test_rampage_upgrade_preserves_grown_damage(self):
        combat = _make_combat()
        rampage = make_rampage()
        combat.hand = [rampage]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert rampage.base_damage == 14

        combat.upgrade_card(rampage)

        assert rampage.upgraded is True
        assert rampage.base_damage == 14
        assert rampage.effect_vars["increase"] == 9

    def test_feel_no_pain_gives_block_when_owner_card_is_exhausted(self):
        """Matches FeelNoPain.cs + FeelNoPainPower.cs: owner gains block per exhausted card."""
        combat = _make_combat()
        strike = make_strike_ironclad()
        combat.hand = [make_feel_no_pain(), strike]
        combat.energy = 2

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.FEEL_NO_PAIN) == 3

        combat.exhaust_card(strike)
        assert combat.player.block == 3

    def test_power_block_gains_trigger_after_block_gained_hooks(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.max_hp = 50
        enemy.current_hp = 50
        combat.hand = [make_feel_no_pain(), make_juggernaut(), make_rage(), make_strike_ironclad()]
        combat.energy = 4

        assert combat.play_card(0)
        assert combat.play_card(0)
        assert combat.play_card(0)
        assert combat.play_card(0, 0)

        assert combat.player.block == 3
        assert enemy.current_hp == 50 - 6 - 5

        combat.exhaust_card(combat.discard_pile[0])
        assert combat.player.block == 6
        assert enemy.current_hp == 50 - 6 - 10

    def test_fiend_fire_exhausts_hand_for_hits_and_triggers_feel_no_pain_per_exhaust(self):
        """Matches FiendFire.cs with exhaust hooks: exhaust all hand cards, one hit each, hooks fire."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        start_hp = enemy.current_hp
        strike = make_strike_ironclad()
        defend = make_defend_ironclad()
        combat.hand = [make_feel_no_pain(), make_fiend_fire(), strike, defend]
        combat.energy = 3

        assert combat.play_card(0)
        assert combat.play_card(0, 0)

        assert enemy.current_hp == start_hp - 14
        assert combat.player.block == 9
        assert strike in combat.exhaust_pile
        assert defend in combat.exhaust_pile
        assert len(combat.hand) == 0

    def test_fiend_fire_stops_followup_hits_if_attacker_dies_to_thorns(self):
        """Matches AttackCommand.cs: later hits stop when the attacker is dead."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = enemy.max_hp = 100
        enemy.apply_power(PowerId.THORNS, 5)
        combat.player.current_hp = 3
        combat.hand = [make_fiend_fire(), make_strike_ironclad(), make_defend_ironclad()]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert combat.player.current_hp == 0
        assert enemy.current_hp == 93
        assert combat.is_over
        assert combat.player_won is False

    def test_twin_strike_stops_second_hit_if_attacker_dies_to_thorns(self):
        """Matches AttackCommand.cs: the next hit is skipped if the attacker died."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = enemy.max_hp = 100
        enemy.apply_power(PowerId.THORNS, 5)
        combat.player.current_hp = 3
        combat.hand = [make_twin_strike()]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert combat.player.current_hp == 0
        assert enemy.current_hp == 95
        assert combat.is_over
        assert combat.player_won is False
