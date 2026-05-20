"""Tests for potions system.

Verifies potion registry, rarity counts, pool filtering, and instance behavior.
"""

import pytest

import sts2_env.powers  # noqa: F401
from sts2_env.cards.defect import create_defect_starter_deck, make_tempest
from sts2_env.cards.ironclad import make_bash
from sts2_env.cards.necrobinder import create_necrobinder_starter_deck
from sts2_env.cards.regent import create_regent_starter_deck
from sts2_env.cards.silent import create_silent_starter_deck
from sts2_env.cards.silent import make_defend_silent, make_neutralize, make_strike_silent
from sts2_env.cards.status import make_ascenders_bane, make_byrd_swoop, make_wound
from sts2_env.core.combat import CombatState
from sts2_env.core.enums import CardId, CardType, CombatSide, OrbType, PowerId, PotionRarity, PotionUsageType, PotionTargetType
from sts2_env.core.hooks import fire_after_turn_end
from sts2_env.core.rng import Rng
from sts2_env.monsters.act1_weak import create_shrinker_beetle
from sts2_env.powers.base import PowerInstance
from sts2_env.potions.base import (
    PotionModel,
    PotionInstance,
    all_potion_models,
    create_potion,
    get_potion_model,
    normal_pool_models,
    roll_random_potion_model,
)
from sts2_env.run.run_state import PlayerState
import sts2_env.potions.all  # noqa: F401 -- register all potions


class _FirstRng:
    def sample(self, lst, k):
        return list(lst)[:k]

    def choice(self, lst):
        return list(lst)[0]


def _make_silent_combat(
    relics: list[str] | None = None,
    *,
    seed: int = 1810,
    extra_enemies: int = 0,
) -> CombatState:
    combat = CombatState(
        player_hp=70,
        player_max_hp=70,
        deck=create_silent_starter_deck(),
        rng_seed=seed,
        character_id="Silent",
        relics=relics or [],
    )
    creature, ai = create_shrinker_beetle(Rng(seed))
    combat.add_enemy(creature, ai)
    for i in range(extra_enemies):
        extra_creature, extra_ai = create_shrinker_beetle(Rng(seed + i + 1))
        combat.add_enemy(extra_creature, extra_ai)
    combat.start_combat()
    return combat


def _make_combat_for_character(
    character_id: str,
    deck,
    *,
    seed: int = 1810,
) -> CombatState:
    combat = CombatState(
        player_hp=70,
        player_max_hp=70,
        deck=deck,
        rng_seed=seed,
        character_id=character_id,
    )
    creature, ai = create_shrinker_beetle(Rng(seed))
    combat.add_enemy(creature, ai)
    combat.start_combat()
    return combat


class _CannotHitPower(PowerInstance):
    def __init__(self):
        super().__init__(PowerId.COVERED, 1)

    def should_allow_hitting(self, owner, combat):
        return False


FIRST_ALLY_PLAYER_TARGET_INDEX = 1
INVALID_PLAYER_TARGET_INDEX = 2


class TestPotionRegistry:
    def test_total_count(self):
        assert len(all_potion_models()) == 63

    def test_normal_pool_excludes_event_token(self):
        pool = normal_pool_models()
        for m in pool:
            assert m.rarity not in (PotionRarity.EVENT, PotionRarity.TOKEN, PotionRarity.NONE)

    def test_normal_pool_count(self):
        """63 total - 2 Event (FoulPotion, GlowwaterPotion) - 1 Token (PotionShapedRock) = 60."""
        assert len(normal_pool_models()) == 60

    def test_character_filtered_pool_excludes_other_character_potions(self):
        ironclad_pool = {model.potion_id for model in normal_pool_models(character_id="Ironclad")}
        assert "BloodPotion" in ironclad_pool
        assert "SoldiersStew" in ironclad_pool
        assert "FocusPotion" not in ironclad_pool
        assert "StarPotion" not in ironclad_pool

    def test_in_combat_pool_excludes_out_of_combat_only_potions(self):
        in_combat_pool = {model.potion_id for model in normal_pool_models(in_combat=True)}
        assert "FairyInABottle" not in in_combat_pool
        assert "FruitJuice" not in in_combat_pool
        assert "RegenPotion" not in in_combat_pool

    def test_combat_pool_excludes_noncombat_generation_potions(self):
        combat_pool_ids = {m.potion_id for m in normal_pool_models(in_combat=True)}
        assert len(combat_pool_ids) == 57
        assert "FairyInABottle" not in combat_pool_ids
        assert "FruitJuice" not in combat_pool_ids
        assert "RegenPotion" not in combat_pool_ids

    def test_lookup_by_id(self):
        model = get_potion_model("FirePotion")
        assert model is not None
        assert model.potion_id == "FirePotion"

    def test_nonexistent_returns_none(self):
        assert get_potion_model("NonexistentPotion") is None


class TestRarityCounts:
    def test_common_count(self):
        common = [m for m in all_potion_models() if m.rarity == PotionRarity.COMMON]
        assert len(common) == 20

    def test_uncommon_count(self):
        uncommon = [m for m in all_potion_models() if m.rarity == PotionRarity.UNCOMMON]
        assert len(uncommon) == 20

    def test_rare_count(self):
        rare = [m for m in all_potion_models() if m.rarity == PotionRarity.RARE]
        assert len(rare) == 20

    def test_event_count(self):
        event = [m for m in all_potion_models() if m.rarity == PotionRarity.EVENT]
        assert len(event) == 2

    def test_token_count(self):
        token = [m for m in all_potion_models() if m.rarity == PotionRarity.TOKEN]
        assert len(token) == 1


class TestPotionUsageTypes:
    def test_combat_only_potions(self):
        combat = [m for m in all_potion_models() if m.usage_type == PotionUsageType.COMBAT_ONLY]
        assert len(combat) >= 50  # majority are combat only

    def test_any_time_potions(self):
        """BloodPotion, EntropicBrew, FruitJuice, FoulPotion."""
        any_time = [m for m in all_potion_models() if m.usage_type == PotionUsageType.ANY_TIME]
        any_time_ids = {m.potion_id for m in any_time}
        assert "BloodPotion" in any_time_ids
        assert "EntropicBrew" in any_time_ids
        assert "FruitJuice" in any_time_ids
        assert "FoulPotion" in any_time_ids

    def test_automatic_potions(self):
        """FairyInABottle is the only automatic potion."""
        auto = [m for m in all_potion_models() if m.usage_type == PotionUsageType.AUTOMATIC]
        assert len(auto) == 1
        assert auto[0].potion_id == "FairyInABottle"


class TestPotionTargetTypes:
    def test_self_targeting(self):
        m = get_potion_model("AttackPotion")
        assert m.target_type == PotionTargetType.SELF

    def test_any_enemy_targeting(self):
        m = get_potion_model("FirePotion")
        assert m.target_type == PotionTargetType.ANY_ENEMY

    def test_all_enemies_targeting(self):
        m = get_potion_model("ExplosiveAmpoule")
        assert m.target_type == PotionTargetType.ALL_ENEMIES

    def test_any_player_targeting(self):
        m = get_potion_model("BlockPotion")
        assert m.target_type == PotionTargetType.ANY_PLAYER


class TestPotionInstance:
    def test_create_potion(self):
        p = create_potion("FirePotion")
        assert p.potion_id == "FirePotion"
        assert p.rarity == PotionRarity.COMMON
        assert p.usage_type == PotionUsageType.COMBAT_ONLY
        assert p.target_type == PotionTargetType.ANY_ENEMY

    def test_can_use_in_combat(self):
        combat_only = create_potion("FirePotion")
        assert combat_only.can_use_in_combat()
        assert not combat_only.can_use_out_of_combat()

        any_time = create_potion("BloodPotion")
        assert any_time.can_use_in_combat()
        assert any_time.can_use_out_of_combat()

    def test_automatic_usage(self):
        fairy = create_potion("FairyInABottle")
        assert fairy.usage_type == PotionUsageType.AUTOMATIC

    def test_fairy_in_a_bottle_prevents_player_death_and_is_consumed(self):
        combat = _make_silent_combat(seed=1818)
        fairy = create_potion("FairyInABottle")
        assert combat.add_potion(fairy)
        combat.player.current_hp = 1

        assert combat.kill_creature(combat.player)
        assert combat.player.current_hp == 21
        assert fairy not in combat.held_potions()
        assert combat.is_over is False

    def test_repr(self):
        p = create_potion("StrengthPotion")
        assert "StrengthPotion" in repr(p)

    def test_create_nonexistent_raises(self):
        with pytest.raises(KeyError):
            create_potion("NonexistentPotion")

    def test_poison_potion_uses_owner_applier_for_snecko_skull(self):
        combat = _make_silent_combat(["SneckoSkull"])
        enemy = combat.enemies[0]
        combat.potions = [create_potion("PoisonPotion"), None, None]

        assert combat.use_potion(0, target_index=0)
        assert enemy.get_power_amount(PowerId.POISON) == 7

    def test_potion_of_doom_uses_owner_applier_for_shroud(self):
        combat = _make_silent_combat()
        player = combat.player
        enemy = combat.enemies[0]
        player.apply_power(PowerId.SHROUD, 3)
        combat.potions = [create_potion("PotionOfDoom"), None, None]

        assert combat.use_potion(0, target_index=0)
        assert enemy.get_power_amount(PowerId.DOOM) == 33
        assert player.block == 3

    def test_attack_potion_uses_combat_generation_pool(self):
        combat = _make_silent_combat()
        combat.potions = [create_potion("AttackPotion"), None, None]
        combat.rng = _FirstRng()

        assert combat.use_potion(0)
        assert combat.pending_choice is not None

        generated_ids = {option.card.card_id for option in combat.pending_choice.options}
        assert CardId.STRIKE_SILENT not in generated_ids

    def test_powdered_demise_uses_owner_applier_for_sleight_of_flesh(self):
        combat = _make_silent_combat()
        player = combat.player
        enemy = combat.enemies[0]
        enemy.max_hp = 50
        enemy.current_hp = 50
        player.apply_power(PowerId.SLEIGHT_OF_FLESH, 2)
        combat.potions = [create_potion("PowderedDemise"), None, None]

        assert combat.use_potion(0, target_index=0)
        assert enemy.get_power_amount(PowerId.DEMISE) == 9
        assert enemy.current_hp == 48

    def test_temporary_stat_potions_apply_now_and_restore_at_turn_end(self):
        combat = _make_silent_combat()
        player = combat.player
        combat.potions = [create_potion("FlexPotion"), create_potion("SpeedPotion"), None]

        assert combat.use_potion(0)
        assert player.get_power_amount(PowerId.FLEX_POTION) == 5
        assert player.get_power_amount(PowerId.STRENGTH) == 5

        assert combat.use_potion(1)
        assert player.get_power_amount(PowerId.SPEED_POTION) == 5
        assert player.get_power_amount(PowerId.DEXTERITY) == 5

        fire_after_turn_end(CombatSide.PLAYER, combat)
        assert player.get_power_amount(PowerId.STRENGTH) == 0
        assert player.get_power_amount(PowerId.DEXTERITY) == 0

    def test_shackling_potion_applies_and_restores_temporary_strength_loss(self):
        combat = _make_silent_combat()
        enemy = combat.enemies[0]
        combat.potions = [create_potion("ShacklingPotion"), None, None]

        assert combat.use_potion(0)
        assert enemy.get_power_amount(PowerId.SHACKLING_POTION) == 7
        assert enemy.get_power_amount(PowerId.STRENGTH) == -7

        fire_after_turn_end(CombatSide.ENEMY, combat)
        assert enemy.get_power_amount(PowerId.STRENGTH) == 0

    def test_any_enemy_potion_targets_only_hittable_enemies(self):
        combat = _make_silent_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.potions = [create_potion("FirePotion"), create_potion("FirePotion"), None]

        assert combat.use_potion(0, target_index=0) is False
        assert blocked.current_hp == 100
        assert hittable.current_hp == 100
        assert combat.potions[0] is not None

        assert combat.use_potion(1)
        assert blocked.current_hp == 100
        assert hittable.current_hp == 80

    def test_all_enemy_potions_affect_only_hittable_enemies(self):
        combat = _make_silent_combat(extra_enemies=1)
        blocked, hittable = combat.enemies
        blocked.current_hp = blocked.max_hp = 100
        hittable.current_hp = hittable.max_hp = 100
        blocked.powers[PowerId.COVERED] = _CannotHitPower()
        combat.potions = [create_potion("ExplosiveAmpoule"), create_potion("PotionOfBinding"), None]

        assert combat.use_potion(0)
        assert blocked.current_hp == 100
        assert hittable.current_hp == 90

        assert combat.use_potion(1)
        assert blocked.get_power_amount(PowerId.WEAK) == 0
        assert blocked.get_power_amount(PowerId.VULNERABLE) == 0
        assert hittable.get_power_amount(PowerId.WEAK) == 1
        assert hittable.get_power_amount(PowerId.VULNERABLE) == 1

    def test_foul_potion_damages_player_and_enemies_in_combat(self):
        combat = _make_silent_combat()
        enemy = combat.enemies[0]
        player_hp = combat.player.current_hp
        enemy_hp = enemy.current_hp
        combat.potions = [create_potion("FoulPotion"), None, None]

        assert combat.use_potion(0)
        assert combat.player.current_hp == player_hp - 12
        assert enemy.current_hp == enemy_hp - 12

    def test_star_potion_uses_combat_gain_stars_gate(self):
        combat = _make_silent_combat()
        combat.stars = 0
        combat.player.stars = 0
        combat.is_over = True

        create_potion("StarPotion").use(combat, combat.player)

        assert combat.stars == 0
        assert combat.player.stars == 0

    def test_clarity_draws_from_selected_player_pile_like_reference(self):
        """Matches Clarity.cs: draw and ClarityPower apply to the targeted player."""
        combat = _make_silent_combat()
        ally = combat.add_ally_player(PlayerState(player_id=2, character_id="Silent", max_hp=70, current_hp=70))
        ally_state = combat.combat_player_state_for(ally)
        assert ally_state is not None
        primary_marker = make_strike_silent()
        ally_draw = make_defend_silent()
        combat.hand = []
        combat.draw_pile = [primary_marker]
        ally_state.hand = []
        ally_state.draw = [ally_draw]
        combat.potions = [create_potion("Clarity"), None, None]

        assert combat.use_potion(0, target_index=INVALID_PLAYER_TARGET_INDEX) is False
        assert combat.potions[0] is not None
        assert combat.use_potion(0, target_index=FIRST_ALLY_PLAYER_TARGET_INDEX)

        assert ally_state.hand == [ally_draw]
        assert ally_state.draw == []
        assert combat.hand == []
        assert combat.draw_pile == [primary_marker]
        assert ally.get_power_amount(PowerId.CLARITY) == 3
        assert combat.player.get_power_amount(PowerId.CLARITY) == 0

    def test_block_potion_block_triggers_after_block_gained_hooks(self):
        combat = _make_silent_combat()
        enemy = combat.enemies[0]
        start_hp = enemy.current_hp
        combat.player.apply_power(PowerId.JUGGERNAUT, 5)
        combat.potions = [create_potion("BlockPotion"), None, None]

        assert combat.use_potion(0)

        assert combat.player.block == 12
        assert enemy.current_hp == start_hp - 5

    def test_fortifier_uses_original_block_amount_and_triggers_hooks(self):
        combat = _make_silent_combat()
        enemy = combat.enemies[0]
        start_hp = enemy.current_hp
        combat.player.block = 4
        combat.player.apply_power(PowerId.JUGGERNAUT, 5)
        combat.potions = [create_potion("Fortifier"), None, None]

        assert combat.use_potion(0)

        assert combat.player.block == 12
        assert enemy.current_hp == start_hp - 5

    def test_ship_in_a_bottle_block_triggers_after_block_gained_hooks(self):
        combat = _make_silent_combat()
        enemy = combat.enemies[0]
        start_hp = enemy.current_hp
        combat.player.apply_power(PowerId.JUGGERNAUT, 5)
        combat.potions = [create_potion("ShipInABottle"), None, None]

        assert combat.use_potion(0)

        assert combat.player.block == 10
        assert combat.player.get_power_amount(PowerId.BLOCK_NEXT_TURN) == 10
        assert enemy.current_hp == start_hp - 5

    def test_direct_stat_and_power_potion_effects_match_source_values(self):
        cases = [
            ("DexterityPotion", PowerId.DEXTERITY, 2),
            ("LiquidBronze", PowerId.THORNS, 3),
            ("HeartOfIron", PowerId.PLATING, 7),
            ("StableSerum", PowerId.RETAIN_HAND, 2),
            ("GhostInAJar", PowerId.INTANGIBLE, 1),
            ("GigantificationPotion", PowerId.GIGANTIFICATION, 1),
            ("LuckyTonic", PowerId.BUFFER, 1),
            ("MazalethsGift", PowerId.RITUAL, 1),
            ("Duplicator", PowerId.DUPLICATION, 1),
        ]
        for potion_id, power_id, amount in cases:
            combat = _make_silent_combat()
            combat.potions = [create_potion(potion_id), None, None]

            assert combat.use_potion(0)

            assert combat.player.get_power_amount(power_id) == amount

    def test_direct_enemy_debuff_potion_effects_match_source_values(self):
        cases = [
            ("VulnerablePotion", PowerId.VULNERABLE, 3),
            ("WeakPotion", PowerId.WEAK, 3),
            ("BeetleJuice", PowerId.SHRINK, 4),
        ]
        for potion_id, power_id, amount in cases:
            combat = _make_silent_combat()
            enemy = combat.enemies[0]
            combat.potions = [create_potion(potion_id), None, None]

            assert combat.use_potion(0, target_index=0)

            assert enemy.get_power_amount(power_id) == amount

    def test_fysh_oil_and_radiant_tincture_match_source_values(self):
        combat = _make_silent_combat()
        combat.potions = [create_potion("FyshOil"), create_potion("RadiantTincture"), None]

        assert combat.use_potion(0)
        assert combat.player.get_power_amount(PowerId.STRENGTH) == 1
        assert combat.player.get_power_amount(PowerId.DEXTERITY) == 1

        start_energy = combat.energy
        assert combat.use_potion(1)
        assert combat.energy == start_energy + 1
        assert combat.player.get_power_amount(PowerId.RADIANCE) == 3

    def test_blessing_of_the_forge_upgrades_all_upgradable_hand_cards(self):
        combat = _make_silent_combat()
        strike = make_strike_silent()
        defend = make_defend_silent(upgraded=True)
        combat.hand = [strike, defend]
        combat.potions = [create_potion("BlessingOfTheForge"), None, None]

        assert combat.use_potion(0)

        assert strike.upgraded
        assert defend.upgraded

    def test_droplet_of_precognition_uses_only_current_draw_pile(self):
        combat = _make_silent_combat()
        discarded = make_strike_silent()
        combat.hand = []
        combat.draw_pile = []
        combat.discard_pile = [discarded]
        combat.potions = [create_potion("DropletOfPrecognition"), None, None]

        assert combat.use_potion(0)

        assert combat.pending_choice is None
        assert combat.hand == []
        assert combat.draw_pile == []
        assert combat.discard_pile == [discarded]

    def test_droplet_of_precognition_sorts_draw_pile_like_source(self):
        combat = _make_silent_combat()
        strike = make_strike_silent()
        neutralize = make_neutralize()
        bash = make_bash()
        wound = make_wound()
        curse = make_ascenders_bane()
        event = make_byrd_swoop()
        combat.hand = []
        combat.draw_pile = [event, wound, bash, curse, strike, neutralize]
        combat.potions = [create_potion("DropletOfPrecognition"), None, None]

        assert combat.use_potion(0)

        assert combat.pending_choice is not None
        assert [option.card for option in combat.pending_choice.options] == [
            bash,
            neutralize,
            strike,
            wound,
            curse,
            event,
        ]

    def test_snecko_oil_randomizes_non_x_costs_for_this_turn_only(self):
        combat = _make_silent_combat()
        hand_card = make_strike_silent()
        drawn_card = make_defend_silent()
        x_cost = make_tempest()
        hand_card.cost = hand_card.original_cost = 2
        drawn_card.cost = drawn_card.original_cost = 1
        x_cost.cost = x_cost.original_cost = 0
        combat.hand = [hand_card, x_cost]
        combat.draw_pile = [drawn_card]
        combat.discard_pile = []
        combat.potions = [create_potion("SneckoOil"), None, None]

        assert combat.use_potion(0)

        assert "_turn_cost_override" in hand_card.combat_vars
        assert "_turn_cost_override" in drawn_card.combat_vars
        assert "_turn_cost_override" not in x_cost.combat_vars
        assert x_cost.cost == 0

        hand_card.end_of_turn_cleanup()
        drawn_card.end_of_turn_cleanup()
        assert hand_card.cost == 2
        assert drawn_card.cost == 1

    def test_swift_potion_draws_three_cards(self):
        combat = _make_silent_combat()
        first = make_strike_silent()
        second = make_defend_silent()
        third = make_neutralize()
        combat.hand = []
        combat.draw_pile = [first, second, third]
        combat.discard_pile = []
        combat.potions = [create_potion("SwiftPotion"), None, None]

        assert combat.use_potion(0)

        assert combat.hand == [first, second, third]
        assert combat.draw_pile == []

    def test_cure_all_gains_energy_and_draws_two_cards(self):
        combat = _make_silent_combat()
        first = make_strike_silent()
        second = make_defend_silent()
        combat.energy = 0
        combat.hand = []
        combat.draw_pile = [first, second]
        combat.discard_pile = []
        combat.potions = [create_potion("CureAll"), None, None]

        assert combat.use_potion(0)

        assert combat.energy == 1
        assert combat.hand == [first, second]
        assert combat.draw_pile == []

    def test_bottled_potential_moves_hand_into_draw_pile_then_draws_five(self):
        combat = _make_silent_combat()
        hand_cards = [make_strike_silent() for _ in range(3)]
        draw_cards = [make_defend_silent() for _ in range(2)]
        combat.hand = list(hand_cards)
        combat.draw_pile = list(draw_cards)
        combat.discard_pile = []
        combat.potions = [create_potion("BottledPotential"), None, None]

        assert combat.use_potion(0)

        assert len(combat.hand) == 5
        assert {id(card) for card in combat.hand} == {id(card) for card in hand_cards + draw_cards}
        assert combat.draw_pile == []

    def test_bone_brew_summons_osty_with_source_value(self):
        combat = _make_combat_for_character("Necrobinder", create_necrobinder_starter_deck())
        combat.potions = [create_potion("BoneBrew"), None, None]

        assert combat.use_potion(0)

        osty = combat.get_osty(combat.player)
        assert osty is not None
        assert osty.max_hp == 15
        assert osty.current_hp == 15

    def test_kings_courage_forges_sovereign_blade_by_source_value(self):
        combat = _make_combat_for_character("Regent", create_regent_starter_deck())
        combat.hand = []
        combat.potions = [create_potion("KingsCourage"), None, None]

        assert combat.use_potion(0)

        blade = next(card for card in combat.hand if card.card_id == CardId.SOVEREIGN_BLADE)
        assert blade.base_damage == 25

    def test_potion_of_capacity_adds_two_orb_slots_up_to_cap(self):
        combat = _make_combat_for_character("Defect", create_defect_starter_deck())
        combat.orb_queue.capacity = 9
        combat.potions = [create_potion("PotionOfCapacity"), None, None]

        assert combat.use_potion(0)

        assert combat.orb_queue.capacity == 10

    def test_essence_of_darkness_channels_dark_orbs_equal_to_capacity(self):
        combat = _make_combat_for_character("Defect", create_defect_starter_deck())
        combat.orb_queue.capacity = 4
        combat.potions = [create_potion("EssenceOfDarkness"), None, None]

        assert combat.use_potion(0)

        assert len(combat.orb_queue.orbs) == 4
        assert all(orb.orb_type == OrbType.DARK for orb in combat.orb_queue.orbs)

    def test_skill_potion_generates_three_free_skill_choices(self):
        combat = _make_silent_combat()
        combat.rng = _FirstRng()
        combat.potions = [create_potion("SkillPotion"), None, None]

        assert combat.use_potion(0)

        assert combat.pending_choice is not None
        assert len(combat.pending_choice.options) == 3
        assert all(option.card.card_type == CardType.SKILL for option in combat.pending_choice.options)
        assert all(option.card.cost == 0 for option in combat.pending_choice.options)
        assert all(
            "_turn_cost_override" in option.card.combat_vars
            for option in combat.pending_choice.options
        )

    def test_power_potion_generates_three_free_power_choices(self):
        combat = _make_silent_combat()
        combat.rng = _FirstRng()
        combat.potions = [create_potion("PowerPotion"), None, None]

        assert combat.use_potion(0)

        assert combat.pending_choice is not None
        assert len(combat.pending_choice.options) == 3
        assert all(option.card.card_type == CardType.POWER for option in combat.pending_choice.options)
        assert all(option.card.cost == 0 for option in combat.pending_choice.options)
        assert all(
            "_turn_cost_override" in option.card.combat_vars
            for option in combat.pending_choice.options
        )


class TestSpecificPotions:
    """Verify specific notable potions have correct attributes."""

    def test_fairy_in_a_bottle(self):
        m = get_potion_model("FairyInABottle")
        assert m.rarity == PotionRarity.RARE
        assert m.usage_type == PotionUsageType.AUTOMATIC
        assert m.target_type == PotionTargetType.SELF

    def test_foul_potion(self):
        m = get_potion_model("FoulPotion")
        assert m.rarity == PotionRarity.EVENT
        assert m.usage_type == PotionUsageType.ANY_TIME

    def test_glowwater_potion(self):
        m = get_potion_model("GlowwaterPotion")
        assert m.rarity == PotionRarity.EVENT
        assert m.usage_type == PotionUsageType.COMBAT_ONLY

    def test_potion_shaped_rock(self):
        m = get_potion_model("PotionShapedRock")
        assert m.rarity == PotionRarity.TOKEN
        assert m.target_type == PotionTargetType.ANY_ENEMY

    def test_entropic_brew(self):
        m = get_potion_model("EntropicBrew")
        assert m.rarity == PotionRarity.RARE
        assert m.usage_type == PotionUsageType.ANY_TIME

    def test_fruit_juice(self):
        m = get_potion_model("FruitJuice")
        assert m.rarity == PotionRarity.RARE
        assert m.usage_type == PotionUsageType.ANY_TIME
        assert m.target_type == PotionTargetType.ANY_PLAYER

    def test_energy_potion(self):
        m = get_potion_model("EnergyPotion")
        assert m.rarity == PotionRarity.COMMON
        assert m.usage_type == PotionUsageType.COMBAT_ONLY
        assert m.target_type == PotionTargetType.ANY_PLAYER

    def test_distilled_chaos(self):
        m = get_potion_model("DistilledChaos")
        assert m.rarity == PotionRarity.RARE
        assert m.usage_type == PotionUsageType.COMBAT_ONLY
        assert m.target_type == PotionTargetType.SELF


class TestPotionModelBehavior:
    def test_is_in_normal_pool_common(self):
        m = get_potion_model("FirePotion")
        assert m.is_in_normal_pool()

    def test_is_in_normal_pool_event(self):
        m = get_potion_model("FoulPotion")
        assert not m.is_in_normal_pool()

    def test_is_in_normal_pool_token(self):
        m = get_potion_model("PotionShapedRock")
        assert not m.is_in_normal_pool()

    def test_slot_index_default(self):
        p = create_potion("FirePotion")
        assert p.slot_index == -1

    def test_slot_index_assigned(self):
        p = create_potion("FirePotion", slot=2)
        assert p.slot_index == 2


class _StubPotionRng:
    def __init__(self, roll: float):
        self._roll = roll

    def next_float(self) -> float:
        return self._roll

    def choice(self, items):
        return items[0]


class TestPotionGenerationRolls:
    def test_roll_random_potion_model_uses_rarity_bands(self):
        rare = roll_random_potion_model(_StubPotionRng(0.05), character_id="Ironclad", in_combat=True)
        uncommon = roll_random_potion_model(_StubPotionRng(0.20), character_id="Ironclad", in_combat=True)
        common = roll_random_potion_model(_StubPotionRng(0.90), character_id="Ironclad", in_combat=True)

        assert rare is not None and rare.rarity == PotionRarity.RARE
        assert uncommon is not None and uncommon.rarity == PotionRarity.UNCOMMON
        assert common is not None and common.rarity == PotionRarity.COMMON
