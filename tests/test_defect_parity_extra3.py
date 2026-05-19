"""Additional Defect parity tests for remaining high-signal card behaviors."""

import sts2_env.powers  # noqa: F401

from sts2_env.cards.defect import (
    create_defect_starter_deck,
    make_all_for_one,
    make_biased_cognition,
    make_boost_away,
    make_claw,
    make_cold_snap,
    make_consuming_shadow,
    make_creative_ai,
    make_darkness,
    make_defend_defect,
    make_fight_through,
    make_flak_cannon,
    make_ftl,
    make_genetic_algorithm,
    make_go_for_the_eyes,
    make_gunk_up,
    make_hyperbeam,
    make_ice_lance,
    make_lightning_rod,
    make_machine_learning,
    make_overclock,
    make_refract,
    make_reboot,
    make_shatter,
    make_signal_boost,
    make_strike_defect,
    make_sweeping_beam,
    make_tempest,
    make_thunder,
)
from sts2_env.cards.factory import create_card
from sts2_env.cards.status import make_burn, make_dazed, make_slimed
from sts2_env.core.combat import CombatState
from sts2_env.core.enums import CardId, OrbType, PowerId, ValueProp
from sts2_env.core.rng import Rng
from sts2_env.monsters.act1_weak import create_shrinker_beetle, create_twig_slime_s
from sts2_env.powers.base import PowerInstance


class _CannotHitPower(PowerInstance):
    def __init__(self):
        super().__init__(PowerId.COVERED, 1)

    def should_allow_hitting(self, owner, combat):
        return False


def _make_combat(monster_factory=create_shrinker_beetle, *, extra_enemies: int = 0) -> CombatState:
    combat = CombatState(
        player_hp=75,
        player_max_hp=75,
        deck=create_defect_starter_deck(),
        rng_seed=42,
        character_id="Defect",
    )
    creature, ai = monster_factory(Rng(42))
    combat.add_enemy(creature, ai)
    for i in range(extra_enemies):
        extra_creature, extra_ai = create_shrinker_beetle(Rng(100 + i))
        combat.add_enemy(extra_creature, extra_ai)
    combat.start_combat()
    return combat


class TestDefectParityExtra3:
    def test_cold_snap_deals_damage_and_channels_frost(self):
        """Matches ColdSnap.cs: attack target, then channel one Frost orb."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        starting_hp = enemy.current_hp
        combat.hand = [make_cold_snap()]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 6
        assert len(combat.orb_queue.orbs) == 1
        assert combat.orb_queue.orbs[0].orb_type == OrbType.FROST

    def test_sweeping_beam_hits_only_hittable_enemies_then_draws(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        drawn = make_strike_defect()
        combat.hand = [make_sweeping_beam()]
        combat.draw_pile = [drawn]
        combat.energy = 1

        assert combat.play_card(0)

        assert blocked.current_hp == 100
        assert hittable.current_hp == 94
        assert drawn in combat.hand

    def test_flak_cannon_random_hits_use_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.hand = [make_flak_cannon(), make_dazed(), make_strike_defect()]
        combat.draw_pile = [make_burn()]
        combat.energy = 2

        assert combat.play_card(0)

        assert blocked.current_hp == 100
        assert hittable.current_hp == 84

    def test_genetic_algorithm_starts_at_one_block_and_grows_after_play(self):
        """Matches GeneticAlgorithm.cs: CurrentBlock starts at 1 and grows by Increase after play."""
        combat = _make_combat()
        card = make_genetic_algorithm()
        combat.hand = [card]
        combat.energy = 1

        assert card.base_block == 1
        assert card.effect_vars["block"] == 1

        assert combat.play_card(0)

        assert combat.player.block == 1
        assert card.base_block == 4
        assert card.effect_vars["block"] == 4

    def test_upgraded_genetic_algorithm_grows_by_four(self):
        combat = _make_combat()
        card = create_card(CardId.GENETIC_ALGORITHM, upgraded=True)
        combat.hand = [card]
        combat.energy = 1

        assert card.effect_vars["increase"] == 4

        assert combat.play_card(0)

        assert combat.player.block == 1
        assert card.base_block == 5
        assert card.effect_vars["block"] == 5

    def test_genetic_algorithm_upgrade_preserves_grown_block(self):
        combat = _make_combat()
        card = make_genetic_algorithm()
        combat.hand = [card]
        combat.energy = 1

        assert combat.play_card(0)
        assert card.base_block == 4

        combat.upgrade_card(card)

        assert card.upgraded is True
        assert card.effect_vars["increase"] == 4
        assert card.base_block == 4
        assert card.effect_vars["block"] == 4

    def test_claw_upgrade_preserves_shared_growth_for_all_owner_copies(self):
        combat = _make_combat()
        played = make_claw()
        in_draw = make_claw()
        in_discard = make_claw()
        combat.hand = [played]
        combat.draw_pile = [in_draw]
        combat.discard_pile = [in_discard]

        assert combat.play_card(0, 0)

        assert played.base_damage == 5
        assert in_draw.base_damage == 5
        assert in_discard.base_damage == 5

        combat.upgrade_card(in_draw)

        assert in_draw.upgraded is True
        assert in_draw.base_damage == 6
        assert in_draw.effect_vars["increase"] == 3

    def test_hyperbeam_hits_only_hittable_enemies_and_loses_focus(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.apply_power_to(combat.player, PowerId.FOCUS, 4)
        combat.hand = [make_hyperbeam()]
        combat.energy = 2

        assert combat.play_card(0)

        assert blocked.current_hp == 100
        assert hittable.current_hp == 74
        assert combat.player.get_power_amount(PowerId.FOCUS) == 1

    def test_shatter_hits_only_hittable_enemies(self):
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.hand = [make_shatter()]
        combat.energy = 1

        assert combat.play_card(0)

        assert blocked.current_hp == 100
        assert hittable.current_hp == 89

    def test_go_for_the_eyes_applies_weak_only_if_target_intends_attack(self):
        """Matches GoForTheEyes.cs: Weak is conditional on target attack intent."""
        no_attack_combat = _make_combat(create_shrinker_beetle)
        no_attack_enemy = no_attack_combat.enemies[0]
        no_attack_hp = no_attack_enemy.current_hp
        no_attack_combat.hand = [make_go_for_the_eyes()]
        no_attack_combat.energy = 0

        assert no_attack_combat.play_card(0, 0)
        assert no_attack_enemy.current_hp == no_attack_hp - 3
        assert no_attack_enemy.get_power_amount(PowerId.WEAK) == 0

        attack_combat = _make_combat(create_twig_slime_s)
        attack_enemy = attack_combat.enemies[0]
        attack_hp = attack_enemy.current_hp
        attack_combat.hand = [make_go_for_the_eyes()]
        attack_combat.energy = 0

        assert attack_combat.play_card(0, 0)
        assert attack_enemy.current_hp == attack_hp - 3
        assert attack_enemy.get_power_amount(PowerId.WEAK) == 1

    def test_reboot_shuffles_current_hand_into_draw_and_redraws(self):
        """Matches Reboot.cs: move hand to draw, shuffle, then draw configured cards."""
        combat = _make_combat()
        reboot = make_reboot()
        held_a = make_strike_defect()
        held_b = make_defend_defect()
        draw_a = make_strike_defect()
        draw_b = make_defend_defect()
        combat.hand = [reboot, held_a, held_b]
        combat.draw_pile = [draw_a, draw_b]
        combat.discard_pile = []
        combat.energy = 0

        assert combat.play_card(0)
        assert reboot in combat.exhaust_pile
        assert len(combat.hand) == 4
        assert {id(card) for card in combat.hand} == {id(held_a), id(held_b), id(draw_a), id(draw_b)}
        assert combat.draw_pile == []

    def test_all_for_one_returns_only_zero_cost_non_x_attack_skill_power_cards(self):
        """Matches AllForOne.cs: discard filter is zero energy, non-X, Attack/Skill/Power only."""
        combat = _make_combat()
        zero_attack = make_strike_defect()
        zero_attack.cost = 0
        zero_skill = make_defend_defect()
        zero_skill.cost = 0
        x_attack = make_tempest()
        zero_status = make_slimed()
        zero_status.cost = 0
        costly_attack = make_strike_defect()
        for discarded in [zero_attack, zero_skill, x_attack, zero_status, costly_attack]:
            discarded.owner = combat.player
        combat.hand = [make_all_for_one()]
        combat.discard_pile = [zero_attack, zero_skill, x_attack, zero_status, costly_attack]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert zero_attack in combat.hand
        assert zero_skill in combat.hand
        assert x_attack in combat.discard_pile
        assert zero_status in combat.discard_pile
        assert costly_attack in combat.discard_pile

    def test_all_for_one_does_not_return_discard_cards_after_damage_ends_combat(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = 10
        zero_attack = make_strike_defect()
        zero_attack.cost = 0
        zero_skill = make_defend_defect()
        zero_skill.cost = 0
        for discarded in [zero_attack, zero_skill]:
            discarded.owner = combat.player
        combat.hand = [make_all_for_one()]
        combat.discard_pile = [zero_attack, zero_skill]
        combat.energy = 2

        assert combat.play_card(0, 0)
        assert combat.is_over
        assert zero_attack in combat.discard_pile
        assert zero_skill in combat.discard_pile
        assert zero_attack not in combat.hand
        assert zero_skill not in combat.hand

    def test_boost_away_adds_owned_generated_dazed_to_discard(self):
        """Matches BoostAway.cs: generated Dazed is added to the owner's discard pile."""
        combat = _make_combat()
        combat.hand = [make_boost_away()]
        combat.energy = 0

        assert combat.play_card(0)
        dazed = [card for card in combat.discard_pile if card.card_id.name == "DAZED"]
        assert len(dazed) == 1
        assert dazed[0].owner is combat.player

    def test_gunk_up_hits_three_times_and_adds_owned_slimed_to_discard(self):
        """Matches GunkUp.cs: 3 hits, then generated Slimed to discard."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        starting_hp = enemy.current_hp
        combat.hand = [make_gunk_up()]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 12
        slimed = [card for card in combat.discard_pile if card.card_id.name == "SLIMED"]
        assert len(slimed) == 1
        assert slimed[0].owner is combat.player

    def test_fight_through_adds_two_owned_wounds_to_discard(self):
        """Matches FightThrough.cs: gain block, then add 2 generated Wounds."""
        combat = _make_combat()
        combat.hand = [make_fight_through()]
        combat.energy = 1

        assert combat.play_card(0)
        wounds = [card for card in combat.discard_pile if card.card_id.name == "WOUND"]
        assert combat.player.block == 13
        assert len(wounds) == 2
        assert all(card.owner is combat.player for card in wounds)

    def test_overclock_draws_then_adds_owned_burn_to_discard(self):
        """Matches Overclock.cs: draw cards, then add generated Burn to discard."""
        combat = _make_combat()
        drawn_a = make_strike_defect()
        drawn_b = make_defend_defect()
        combat.hand = [make_overclock()]
        combat.draw_pile = [drawn_a, drawn_b]
        combat.energy = 0

        assert combat.play_card(0)
        assert drawn_a in combat.hand
        assert drawn_b in combat.hand
        burns = [card for card in combat.discard_pile if card.card_id.name == "BURN"]
        assert len(burns) == 1
        assert burns[0].owner is combat.player

    def test_darkness_triggers_only_dark_orb_passives(self):
        """Matches Darkness.cs: channel Dark, then trigger Dark orbs only."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        starting_hp = enemy.current_hp
        combat.channel_orb(combat.player, "LIGHTNING")
        combat.channel_orb(combat.player, "DARK")
        existing_dark = combat.orb_queue.orbs[1]
        combat.hand = [make_darkness()]
        combat.energy = 1

        assert combat.play_card(0)
        dark_orbs = [orb for orb in combat.orb_queue.orbs if orb.orb_type == OrbType.DARK]
        assert enemy.current_hp == starting_hp
        assert existing_dark.get_evoke_value(combat) == 12
        assert len(dark_orbs) == 2
        assert all(orb.get_evoke_value(combat) == 12 for orb in dark_orbs)

    def test_upgraded_darkness_triggers_dark_orb_passives_twice(self):
        """Matches Darkness.cs: upgraded Darkness passives Dark orbs twice."""
        combat = _make_combat()
        combat.channel_orb(combat.player, "DARK")
        existing_dark = combat.orb_queue.orbs[0]
        combat.hand = [make_darkness(upgraded=True)]
        combat.energy = 1

        assert combat.play_card(0)
        dark_orbs = [orb for orb in combat.orb_queue.orbs if orb.orb_type == OrbType.DARK]
        assert existing_dark.get_evoke_value(combat) == 18
        assert len(dark_orbs) == 2
        assert all(orb.get_evoke_value(combat) == 18 for orb in dark_orbs)

    def test_refract_hits_twice_and_channels_two_glass_orbs(self):
        """Matches Refract.cs: 2 damage hits, then channel 2 Glass."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        starting_hp = enemy.current_hp
        combat.hand = [make_refract()]
        combat.energy = 3

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 18
        assert len(combat.orb_queue.orbs) == 2
        assert all(orb.orb_type == OrbType.GLASS for orb in combat.orb_queue.orbs)

    def test_lightning_orb_damage_is_unpowered(self):
        """Matches LightningOrb.cs: orb damage uses ValueProp.Unpowered."""
        combat = _make_combat()
        combat.channel_orb(combat.player, "LIGHTNING")

        combat.orb_queue.trigger_before_turn_end(combat)

        assert combat._damage_events_combat[-1][2] == ValueProp.UNPOWERED

    def test_dark_orb_evoke_targets_lowest_hittable_enemy(self):
        """Matches DarkOrb.cs: evoke picks the lowest-HP hittable enemy."""
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 10
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.channel_orb(combat.player, "DARK")

        combat.orb_queue.evoke_front(combat)

        assert blocked.current_hp == 10
        assert hittable.current_hp == 94
        assert combat._damage_events_combat[-1][2] == ValueProp.UNPOWERED

    def test_glass_orb_passive_hits_only_hittable_enemies(self):
        """Matches GlassOrb.cs: passive damages HittableEnemies."""
        combat = _make_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.channel_orb(combat.player, "GLASS")

        combat.orb_queue.trigger_before_turn_end(combat)

        assert blocked.current_hp == 100
        assert hittable.current_hp == 96
        assert combat._damage_events_combat[-1][2] == ValueProp.UNPOWERED

    def test_ice_lance_channels_three_frost_orbs_after_damage(self):
        """Matches IceLance.cs: damage target, then channel 3 Frost."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        starting_hp = enemy.current_hp
        combat.hand = [make_ice_lance()]
        combat.energy = 3

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 19
        assert len(combat.orb_queue.orbs) == 3
        assert all(orb.orb_type == OrbType.FROST for orb in combat.orb_queue.orbs)

    def test_ftl_draws_only_before_owner_has_finished_three_card_plays(self):
        """Matches Ftl.cs: draw is gated by owner card plays finished this turn."""
        combat = _make_combat()
        previous = [make_strike_defect(), make_defend_defect(), make_strike_defect()]
        for card in previous:
            card.owner = combat.player
        drawn = make_strike_defect()
        combat._played_cards_this_turn = previous  # noqa: SLF001
        combat.hand = [make_ftl()]
        combat.draw_pile = [drawn]
        combat.energy = 0

        assert combat.play_card(0, 0)
        assert drawn in combat.draw_pile
        assert drawn not in combat.hand

    def test_tempest_uses_x_energy_and_upgrade_adds_one_channel(self):
        """Matches Tempest.cs: channel X Lightning, and X+1 when upgraded."""
        base_combat = _make_combat()
        base_combat.hand = [make_tempest()]
        base_combat.energy = 3

        assert base_combat.play_card(0)
        assert base_combat.energy == 0
        assert len(base_combat.orb_queue.orbs) == 3
        assert all(orb.orb_type == OrbType.LIGHTNING for orb in base_combat.orb_queue.orbs)

        upgraded_combat = _make_combat()
        upgraded = make_tempest()
        upgraded.upgraded = True
        upgraded_combat.hand = [upgraded]
        upgraded_combat.energy = 2

        assert upgraded_combat.play_card(0)
        assert upgraded_combat.energy == 0
        assert len(upgraded_combat.orb_queue.orbs) == 3
        assert all(orb.orb_type == OrbType.LIGHTNING for orb in upgraded_combat.orb_queue.orbs)

    def test_thunder_applies_thunder_power(self):
        """Matches Thunder.cs: apply ThunderPower to owner."""
        combat = _make_combat()
        combat.hand = [make_thunder()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.THUNDER) == 6

    def test_thunder_adds_damage_to_lightning_orb_evoke_targets(self):
        """Matches ThunderPower.cs: after Lightning evoke, damage the living evoke targets."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = enemy.max_hp = 100
        combat.player.apply_power(PowerId.THUNDER, 6)
        combat.channel_orb(combat.player, "LIGHTNING")

        combat.orb_queue.evoke_front(combat)

        assert enemy.current_hp == 86

    def test_thunder_does_not_damage_dark_orb_evoke_targets(self):
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = enemy.max_hp = 100
        combat.player.apply_power(PowerId.THUNDER, 6)
        combat.channel_orb(combat.player, "DARK")

        combat.orb_queue.evoke_front(combat)

        assert enemy.current_hp == 94

    def test_lightning_rod_grants_block_and_channels_lightning_each_turn_while_decrementing(self):
        """Matches LightningRod.cs + LightningRodPower: block now, channel Lightning at turn start."""
        combat = _make_combat()
        combat.hand = [make_lightning_rod()]
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.block == 4
        assert combat.player.get_power_amount(PowerId.LIGHTNING_ROD) == 2

        combat.end_player_turn()

        assert len(combat.orb_queue.orbs) == 1
        assert combat.orb_queue.orbs[0].orb_type == OrbType.LIGHTNING
        assert combat.player.get_power_amount(PowerId.LIGHTNING_ROD) == 1

    def test_machine_learning_increases_next_turn_hand_draw(self):
        """Matches MachineLearning.cs + MachineLearningPower: ModifyHandDraw by +Cards each turn."""
        combat = _make_combat()
        draw_cards = [make_strike_defect() for _ in range(8)]
        combat.hand = [make_machine_learning()]
        combat.draw_pile = list(draw_cards)
        combat.discard_pile = []
        combat.energy = 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.MACHINE_LEARNING) == 1

        combat.end_player_turn()

        assert len(combat.hand) == 6
        assert combat.hand == draw_cards[:6]

    def test_signal_boost_replays_next_power_card_once(self):
        """Matches SignalBoost.cs + SignalBoostPower: next Power card gets +1 play count."""
        combat = _make_combat()
        combat.hand = [make_signal_boost(), make_machine_learning()]
        combat.energy = 2

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.SIGNAL_BOOST) == 1

        assert combat.play_card(0)
        assert combat.player.get_power_amount(PowerId.MACHINE_LEARNING) == 2
        assert combat.player.get_power_amount(PowerId.SIGNAL_BOOST) == 0

    def test_biased_cognition_applies_focus_then_delayed_focus_loss(self):
        """Matches BiasedCognition.cs: apply Focus(4), then BiasedCognition(1)."""
        combat = _make_combat()
        combat.hand = [make_biased_cognition()]
        combat.energy = 1

        assert combat.play_card(0)

        assert combat.player.get_power_amount(PowerId.FOCUS) == 4
        assert combat.player.get_power_amount(PowerId.BIASED_COGNITION) == 1

        combat.end_player_turn()

        assert combat.player.get_power_amount(PowerId.FOCUS) == 3

    def test_creative_ai_applies_power(self):
        """Matches CreativeAI.cs: apply CreativeAiPower(1)."""
        combat = _make_combat()
        combat.hand = [make_creative_ai()]
        combat.energy = 3

        assert combat.play_card(0)

        assert combat.player.get_power_amount(PowerId.CREATIVE_AI) == 1

    def test_consuming_shadow_channels_dark_orbs_then_applies_power(self):
        """Matches ConsumingShadow.cs: channel Repeat Dark orbs, then apply its power."""
        combat = _make_combat()
        combat.hand = [make_consuming_shadow()]
        combat.energy = 2

        assert combat.play_card(0)

        assert [orb.orb_type for orb in combat.orb_queue.orbs] == [OrbType.DARK, OrbType.DARK]
        assert combat.player.get_power_amount(PowerId.CONSUMING_SHADOW) == 1

    def test_upgraded_consuming_shadow_channels_three_dark_orbs(self):
        """Matches ConsumingShadow.cs OnUpgrade: Repeat increases from 2 to 3."""
        combat = _make_combat()
        combat.hand = [create_card(CardId.CONSUMING_SHADOW, upgraded=True)]
        combat.energy = 2

        assert combat.play_card(0)

        assert [orb.orb_type for orb in combat.orb_queue.orbs] == [
            OrbType.DARK,
            OrbType.DARK,
            OrbType.DARK,
        ]
        assert combat.player.get_power_amount(PowerId.CONSUMING_SHADOW) == 1

    def test_consuming_shadow_evokes_last_orb_at_turn_end(self):
        """Matches ConsumingShadowPower.cs: evoke the last orb Amount times on owner turn end."""
        combat = _make_combat()
        enemy = combat.enemies[0]
        enemy.current_hp = enemy.max_hp = 100
        combat.hand = [make_consuming_shadow()]
        combat.energy = 2

        assert combat.play_card(0)
        front, last = combat.orb_queue.orbs
        front._accumulated_evoke = 20
        last._accumulated_evoke = 6

        combat.end_player_turn()

        assert enemy.current_hp == 88
        assert combat.orb_queue.orbs == [front]

    def test_defect_power_card_upgrades_match_original(self):
        """Matches BiasedCognition, CreativeAI, and MachineLearning OnUpgrade methods."""
        biased = create_card(CardId.BIASED_COGNITION_CARD, upgraded=True)
        creative_ai = create_card(CardId.CREATIVE_AI_CARD, upgraded=True)
        machine_learning = create_card(CardId.MACHINE_LEARNING_CARD, upgraded=True)

        assert biased.effect_vars["focus_power"] == 5
        assert biased.cost == 1
        assert creative_ai.cost == 2
        assert creative_ai.effect_vars["creative_ai"] == 1
        assert machine_learning.cost == 1
        assert machine_learning.is_innate is True
