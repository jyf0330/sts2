"""Tests for potions system.

Verifies potion registry, rarity counts, pool filtering, and instance behavior.
"""

import pytest

import sts2_env.powers  # noqa: F401
from sts2_env.cards.silent import create_silent_starter_deck
from sts2_env.core.combat import CombatState
from sts2_env.core.enums import CardId, CombatSide, PowerId, PotionRarity, PotionUsageType, PotionTargetType
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


class _CannotHitPower(PowerInstance):
    def __init__(self):
        super().__init__(PowerId.COVERED, 1)

    def should_allow_hitting(self, owner, combat):
        return False


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
