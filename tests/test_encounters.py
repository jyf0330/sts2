"""Tests for encounter setup functions across all 4 acts.

Verifies each encounter factory:
- Returns the correct number of monsters
- HP values are within expected ranges
- Monsters have valid state machines (current_move is accessible)
- Each act has the expected number of encounters per tier
"""

from __future__ import annotations

import pytest

from sts2_env.cards.ironclad_basic import create_ironclad_starter_deck
from sts2_env.core.combat import CombatState
from sts2_env.core.rng import Rng
from sts2_env.encounters.events import setup_punch_off

# Act 1
from sts2_env.encounters.act1 import (
    setup_shrinker_beetle_weak,
    setup_fuzzy_wurm_crawler_weak,
    setup_nibbits_weak,
    setup_slimes_weak,
    WEAK_ENCOUNTERS as ACT1_WEAK,
    setup_cubex_construct_normal,
    setup_flyconid_normal,
    setup_fogmog_normal,
    setup_inklets_normal,
    setup_mawler_normal,
    setup_nibbits_normal,
    setup_overgrowth_crawlers,
    setup_ruby_raiders_normal,
    setup_slimes_normal,
    setup_slithering_strangler_normal,
    setup_snapping_jaxfruit_normal,
    setup_vine_shambler_normal,
    NORMAL_ENCOUNTERS as ACT1_NORMAL,
    setup_bygone_effigy_elite,
    setup_byrdonis_elite,
    setup_phrog_parasite_elite,
    ELITE_ENCOUNTERS as ACT1_ELITE,
    setup_vantom_boss,
    setup_ceremonial_beast_boss,
    setup_the_kin_boss,
    BOSS_ENCOUNTERS as ACT1_BOSS,
    ALL_ACT1_ENCOUNTERS,
)

# Act 2
from sts2_env.encounters.act2 import (
    WEAK_ENCOUNTERS as ACT2_WEAK,
    NORMAL_ENCOUNTERS as ACT2_NORMAL,
    ELITE_ENCOUNTERS as ACT2_ELITE,
    BOSS_ENCOUNTERS as ACT2_BOSS,
    ALL_ACT2_ENCOUNTERS,
    setup_bowlbugs_normal,
    setup_bowlbugs_weak,
    setup_chompers_normal,
    setup_decimillipede_elite,
    setup_entomancer_elite,
    setup_exoskeletons_normal,
    setup_exoskeletons_weak,
    setup_hunter_killer_normal,
    setup_knowledge_demon_boss,
    setup_louse_progenitor_normal,
    setup_ovicopter_normal,
    setup_slumbering_beetle_normal,
    setup_spiny_toad_normal,
    setup_the_insatiable_boss,
    setup_the_obscura_normal,
    setup_thieving_hopper_weak,
    setup_tunneler_weak,
)

# Act 3
from sts2_env.encounters.act3 import (
    WEAK_ENCOUNTERS as ACT3_WEAK,
    NORMAL_ENCOUNTERS as ACT3_NORMAL,
    ELITE_ENCOUNTERS as ACT3_ELITE,
    BOSS_ENCOUNTERS as ACT3_BOSS,
    ALL_ACT3_ENCOUNTERS,
)

# Act 4
from sts2_env.encounters.act4 import (
    WEAK_ENCOUNTERS as ACT4_WEAK,
    NORMAL_ENCOUNTERS as ACT4_NORMAL,
    ELITE_ENCOUNTERS as ACT4_ELITE,
    BOSS_ENCOUNTERS as ACT4_BOSS,
    ALL_ACT4_ENCOUNTERS,
    setup_cultists_normal,
    setup_fossil_stalker_normal,
    setup_gremlin_merc_normal,
    setup_haunted_ship_normal,
    setup_living_fog_normal,
    setup_punch_construct_normal,
    setup_sewer_clam_normal,
    setup_skulking_colony_elite,
    setup_terror_eel_elite,
)
from sts2_env.encounters.events import (
    setup_battleworn_dummy_v1,
    setup_dense_vegetation,
    setup_fake_merchant,
    setup_mysterious_knight,
    setup_the_architect,
)


def _make_combat(rng_seed: int = 42) -> CombatState:
    """Create a fresh CombatState for encounter testing."""
    deck = create_ironclad_starter_deck()
    return CombatState(player_hp=80, player_max_hp=80, deck=deck, rng_seed=rng_seed)


class _ExclusiveHighRng:
    def next_int_exclusive(self, low: int, high: int) -> int:
        return high - 1


def test_punch_off_hp_reduction_uses_exclusive_upper_bound():
    combat = _make_combat()

    setup_punch_off(combat, _ExclusiveHighRng())

    assert [enemy.current_hp for enemy in combat.enemies] == [46, 46]


CS_ENCOUNTER_PARITY_CASES = [
    ("BattlewornDummyEventEncounter", setup_battleworn_dummy_v1, ("BATTLE_FRIEND_V1",)),
    ("BowlbugsNormal", setup_bowlbugs_normal, ("BOWLBUG_EGG", "BOWLBUG_ROCK", "BOWLBUG_SILK")),
    ("BowlbugsWeak", setup_bowlbugs_weak, ("BOWLBUG_EGG", "BOWLBUG_NECTAR")),
    ("ChompersNormal", setup_chompers_normal, ("CHOMPER", "CHOMPER")),
    ("CultistsNormal", setup_cultists_normal, ("CALCIFIED_CULTIST", "DAMP_CULTIST")),
    (
        "DecimillipedeElite",
        setup_decimillipede_elite,
        ("DECIMILLIPEDE_SEGMENT", "DECIMILLIPEDE_SEGMENT", "DECIMILLIPEDE_SEGMENT"),
    ),
    ("DenseVegetationEventEncounter", setup_dense_vegetation, ("WRIGGLER", "WRIGGLER", "WRIGGLER", "WRIGGLER")),
    ("EntomancerElite", setup_entomancer_elite, ("ENTOMANCER",)),
    ("ExoskeletonsNormal", setup_exoskeletons_normal, ("EXOSKELETON", "EXOSKELETON", "EXOSKELETON")),
    ("ExoskeletonsWeak", setup_exoskeletons_weak, ("EXOSKELETON", "EXOSKELETON")),
    ("FakeMerchantEventEncounter", setup_fake_merchant, ("FAKE_MERCHANT_MONSTER",)),
    ("FossilStalkerNormal", setup_fossil_stalker_normal, ("FOSSIL_STALKER",)),
    ("GremlinMercNormal", setup_gremlin_merc_normal, ("GREMLIN_MERC", "SNEAKY_GREMLIN", "FAT_GREMLIN")),
    ("HauntedShipNormal", setup_haunted_ship_normal, ("HAUNTED_SHIP",)),
    ("HunterKillerNormal", setup_hunter_killer_normal, ("HUNTER_KILLER",)),
    ("KnowledgeDemonBoss", setup_knowledge_demon_boss, ("KNOWLEDGE_DEMON",)),
    ("LivingFogNormal", setup_living_fog_normal, ("LIVING_FOG",)),
    ("LouseProgenitorNormal", setup_louse_progenitor_normal, ("LOUSE_PROGENITOR",)),
    ("MysteriousKnightEventEncounter", setup_mysterious_knight, ("MYSTERIOUS_KNIGHT",)),
    ("OvicopterNormal", setup_ovicopter_normal, ("OVICOPTER",)),
    ("PunchConstructNormal", setup_punch_construct_normal, ("PUNCH_CONSTRUCT",)),
    ("PunchOffEventEncounter", setup_punch_off, ("PUNCH_CONSTRUCT", "PUNCH_CONSTRUCT")),
    ("SewerClamNormal", setup_sewer_clam_normal, ("SEWER_CLAM",)),
    ("SkulkingColonyElite", setup_skulking_colony_elite, ("SKULKING_COLONY",)),
    ("SlumberingBeetleNormal", setup_slumbering_beetle_normal, ("SLUMBERING_BEETLE",)),
    ("SpinyToadNormal", setup_spiny_toad_normal, ("SPINY_TOAD",)),
    ("TerrorEelElite", setup_terror_eel_elite, ("TERROR_EEL",)),
    ("TheArchitectEventEncounter", setup_the_architect, ("ARCHITECT",)),
    ("TheInsatiableBoss", setup_the_insatiable_boss, ("THE_INSATIABLE",)),
    ("TheObscuraNormal", setup_the_obscura_normal, ("THE_OBSCURA",)),
    ("ThievingHopperWeak", setup_thieving_hopper_weak, ("THIEVING_HOPPER",)),
    ("TunnelerWeak", setup_tunneler_weak, ("TUNNELER",)),
]


@pytest.mark.parametrize(
    "cs_name, setup, expected_monster_ids",
    CS_ENCOUNTER_PARITY_CASES,
    ids=[case[0] for case in CS_ENCOUNTER_PARITY_CASES],
)
def test_cs_named_encounter_setup_maps_to_expected_monsters(cs_name, setup, expected_monster_ids):
    combat = _make_combat()

    setup(combat, Rng(42))

    assert cs_name
    assert tuple(enemy.monster_id for enemy in combat.enemies) == expected_monster_ids
    assert all(combat.enemy_ais[enemy.combat_id].current_move.is_move for enemy in combat.enemies)


# ========================================================================
# Act 1: Weak Encounters
# ========================================================================

class TestAct1WeakEncounters:
    def test_shrinker_beetle_count_and_hp(self):
        for seed in range(5):
            combat = _make_combat(seed)
            rng = Rng(seed)
            setup_shrinker_beetle_weak(combat, rng)
            assert len(combat.enemies) == 1
            e = combat.enemies[0]
            assert 38 <= e.max_hp <= 40
            assert e.monster_id == "SHRINKER_BEETLE"

    def test_fuzzy_wurm_crawler_count_and_hp(self):
        for seed in range(5):
            combat = _make_combat(seed)
            rng = Rng(seed)
            setup_fuzzy_wurm_crawler_weak(combat, rng)
            assert len(combat.enemies) == 1
            e = combat.enemies[0]
            assert 55 <= e.max_hp <= 57
            assert e.monster_id == "FUZZY_WURM_CRAWLER"

    def test_nibbits_weak_count_and_hp(self):
        for seed in range(5):
            combat = _make_combat(seed)
            rng = Rng(seed)
            setup_nibbits_weak(combat, rng)
            assert len(combat.enemies) == 1
            e = combat.enemies[0]
            assert 42 <= e.max_hp <= 46
            assert e.monster_id == "NIBBIT"

    def test_slimes_weak_count(self):
        for seed in range(5):
            combat = _make_combat(seed)
            rng = Rng(seed)
            setup_slimes_weak(combat, rng)
            assert len(combat.enemies) == 3  # 2 small + 1 medium
            for e in combat.enemies:
                assert e.max_hp > 0


# ========================================================================
# Act 1: Normal Encounters
# ========================================================================

class TestAct1NormalEncounters:
    def test_cubex_construct_count(self):
        combat = _make_combat()
        setup_cubex_construct_normal(combat, Rng(42))
        assert len(combat.enemies) == 1
        assert combat.enemies[0].max_hp == 65

    def test_flyconid_count_and_hp(self):
        for seed in range(5):
            combat = _make_combat(seed)
            setup_flyconid_normal(combat, Rng(seed))
            assert len(combat.enemies) == 1
            assert 47 <= combat.enemies[0].max_hp <= 49

    def test_fogmog_count(self):
        combat = _make_combat()
        setup_fogmog_normal(combat, Rng(42))
        assert len(combat.enemies) == 1

    def test_inklets_count(self):
        combat = _make_combat()
        setup_inklets_normal(combat, Rng(42))
        assert len(combat.enemies) == 2

    def test_mawler_count(self):
        combat = _make_combat()
        setup_mawler_normal(combat, Rng(42))
        assert len(combat.enemies) == 1

    def test_nibbits_normal_count(self):
        combat = _make_combat()
        setup_nibbits_normal(combat, Rng(42))
        assert len(combat.enemies) == 2
        for e in combat.enemies:
            assert e.monster_id == "NIBBIT"

    def test_overgrowth_crawlers_count(self):
        combat = _make_combat()
        setup_overgrowth_crawlers(combat, Rng(42))
        assert len(combat.enemies) == 2

    def test_ruby_raiders_count(self):
        combat = _make_combat()
        setup_ruby_raiders_normal(combat, Rng(42))
        assert len(combat.enemies) == 3

    def test_slimes_normal_count(self):
        combat = _make_combat()
        setup_slimes_normal(combat, Rng(42))
        assert len(combat.enemies) == 2

    def test_slithering_strangler_count(self):
        combat = _make_combat()
        setup_slithering_strangler_normal(combat, Rng(42))
        assert len(combat.enemies) == 1

    def test_snapping_jaxfruit_count(self):
        combat = _make_combat()
        setup_snapping_jaxfruit_normal(combat, Rng(42))
        assert len(combat.enemies) == 1

    def test_vine_shambler_count(self):
        combat = _make_combat()
        setup_vine_shambler_normal(combat, Rng(42))
        assert len(combat.enemies) == 1


# ========================================================================
# Act 1: Elite Encounters
# ========================================================================

class TestAct1EliteEncounters:
    def test_bygone_effigy_count(self):
        combat = _make_combat()
        setup_bygone_effigy_elite(combat, Rng(42))
        assert len(combat.enemies) == 1

    def test_byrdonis_count(self):
        combat = _make_combat()
        setup_byrdonis_elite(combat, Rng(42))
        assert len(combat.enemies) == 1

    def test_phrog_parasite_count(self):
        combat = _make_combat()
        setup_phrog_parasite_elite(combat, Rng(42))
        assert len(combat.enemies) == 1


# ========================================================================
# Act 1: Boss Encounters
# ========================================================================

class TestAct1BossEncounters:
    def test_vantom_count(self):
        combat = _make_combat()
        setup_vantom_boss(combat, Rng(42))
        assert len(combat.enemies) == 1

    def test_ceremonial_beast_count(self):
        combat = _make_combat()
        setup_ceremonial_beast_boss(combat, Rng(42))
        assert len(combat.enemies) == 1

    def test_the_kin_count(self):
        combat = _make_combat()
        setup_the_kin_boss(combat, Rng(42))
        assert len(combat.enemies) == 3  # priest + 2 followers


# ========================================================================
# Act 1: Pool Counts
# ========================================================================

class TestAct1Pools:
    def test_weak_encounter_count(self):
        assert len(ACT1_WEAK) == 4

    def test_normal_encounter_count(self):
        assert len(ACT1_NORMAL) == 12

    def test_elite_encounter_count(self):
        assert len(ACT1_ELITE) == 3

    def test_boss_encounter_count(self):
        assert len(ACT1_BOSS) == 3

    def test_all_act1_total(self):
        assert len(ALL_ACT1_ENCOUNTERS) == 4 + 12 + 3 + 3  # 22


# ========================================================================
# Act 2: Pool Counts
# ========================================================================

class TestAct2Pools:
    def test_weak_encounter_count(self):
        assert len(ACT2_WEAK) == 4

    def test_normal_encounter_count(self):
        assert len(ACT2_NORMAL) == 11

    def test_elite_encounter_count(self):
        assert len(ACT2_ELITE) == 3

    def test_boss_encounter_count(self):
        assert len(ACT2_BOSS) == 3

    def test_all_act2_total(self):
        assert len(ALL_ACT2_ENCOUNTERS) == 4 + 11 + 3 + 3  # 21


# ========================================================================
# Act 3: Pool Counts
# ========================================================================

class TestAct3Pools:
    def test_weak_encounter_count(self):
        assert len(ACT3_WEAK) == 3

    def test_normal_encounter_count(self):
        assert len(ACT3_NORMAL) == 9

    def test_elite_encounter_count(self):
        assert len(ACT3_ELITE) == 3

    def test_boss_encounter_count(self):
        assert len(ACT3_BOSS) == 3

    def test_all_act3_total(self):
        assert len(ALL_ACT3_ENCOUNTERS) == 3 + 9 + 3 + 3  # 18

    def test_act3_order_matches_original_glory_lists(self):
        assert [encounter.__name__ for encounter in ACT3_BOSS] == [
            "setup_queen_boss",
            "setup_test_subject_boss",
            "setup_doormaker_boss",
        ]
        assert [encounter.__name__ for encounter in ALL_ACT3_ENCOUNTERS] == [
            "setup_axebots_normal",
            "setup_construct_menagerie_normal",
            "setup_devoted_sculptor_weak",
            "setup_doormaker_boss",
            "setup_fabricator_normal",
            "setup_frog_knight_normal",
            "setup_globe_head_normal",
            "setup_knights_elite",
            "setup_mecha_knight_elite",
            "setup_owl_magistrate_normal",
            "setup_queen_boss",
            "setup_scrolls_of_biting_normal",
            "setup_scrolls_of_biting_weak",
            "setup_slimed_berserker_normal",
            "setup_soul_nexus_elite",
            "setup_test_subject_boss",
            "setup_the_lost_and_forgotten_normal",
            "setup_turret_operator_weak",
        ]


# ========================================================================
# Act 4: Pool Counts
# ========================================================================

class TestAct4Pools:
    def test_weak_encounter_count(self):
        assert len(ACT4_WEAK) == 4

    def test_normal_encounter_count(self):
        assert len(ACT4_NORMAL) == 10

    def test_elite_encounter_count(self):
        assert len(ACT4_ELITE) == 3

    def test_boss_encounter_count(self):
        assert len(ACT4_BOSS) == 3

    def test_all_act4_total(self):
        assert len(ALL_ACT4_ENCOUNTERS) == 4 + 10 + 3 + 3  # 20


# ========================================================================
# Cross-act: All encounters can be set up and produce valid AI
# ========================================================================

ALL_ENCOUNTERS_BY_ACT = [
    ("act1", ALL_ACT1_ENCOUNTERS),
    ("act2", ALL_ACT2_ENCOUNTERS),
    ("act3", ALL_ACT3_ENCOUNTERS),
    ("act4", ALL_ACT4_ENCOUNTERS),
]


class TestAllEncountersSetup:
    @pytest.mark.parametrize("act_name, encounters", ALL_ENCOUNTERS_BY_ACT)
    def test_every_encounter_creates_enemies_with_valid_ai(self, act_name, encounters):
        """Every encounter across all 4 acts should set up enemies with valid AI."""
        for idx, encounter in enumerate(encounters):
            rng = Rng(42)
            combat = _make_combat(42)
            encounter(combat, rng)

            assert len(combat.enemies) >= 1, (
                f"{act_name} encounter {idx} added no enemies"
            )
            for enemy in combat.enemies:
                assert enemy.max_hp > 0
                assert enemy.is_alive
                ai = combat.enemy_ais[enemy.combat_id]
                move = ai.current_move
                assert move.is_move
                assert len(move.intents) >= 1

    @pytest.mark.parametrize("act_name, encounters", ALL_ENCOUNTERS_BY_ACT)
    def test_hp_values_within_bounds(self, act_name, encounters):
        """All monster HP values should be between 1 and 500."""
        for seed in range(10):
            rng = Rng(seed)
            for encounter in encounters:
                combat = _make_combat(seed)
                encounter(combat, rng)
                for enemy in combat.enemies:
                    assert 1 <= enemy.max_hp <= 500, (
                        f"{act_name}: unreasonable HP {enemy.max_hp} for {enemy.monster_id}"
                    )
                    assert enemy.current_hp == enemy.max_hp

    @pytest.mark.parametrize("act_name, encounters", ALL_ENCOUNTERS_BY_ACT)
    def test_multiple_seeds_all_succeed(self, act_name, encounters):
        """All encounters should set up successfully across different seeds."""
        for seed in range(10):
            rng = Rng(seed)
            for encounter in encounters:
                combat = _make_combat(seed)
                encounter(combat, rng)
                assert len(combat.enemies) >= 1


class TestAllActsHaveEncounters:
    def test_all_4_acts_present(self):
        """Verify all 4 acts have encounter lists defined."""
        assert len(ALL_ACT1_ENCOUNTERS) > 0
        assert len(ALL_ACT2_ENCOUNTERS) > 0
        assert len(ALL_ACT3_ENCOUNTERS) > 0
        assert len(ALL_ACT4_ENCOUNTERS) > 0

    def test_total_encounter_count(self):
        """Verify total encounters across all acts."""
        total = (
            len(ALL_ACT1_ENCOUNTERS) +
            len(ALL_ACT2_ENCOUNTERS) +
            len(ALL_ACT3_ENCOUNTERS) +
            len(ALL_ACT4_ENCOUNTERS)
        )
        # 22 + 21 + 18 + 20 = 81
        assert total == 81

    def test_each_act_has_all_tiers(self):
        """Each act should have weak, normal, elite, and boss encounters."""
        for name, weak, normal, elite, boss in [
            ("act1", ACT1_WEAK, ACT1_NORMAL, ACT1_ELITE, ACT1_BOSS),
            ("act2", ACT2_WEAK, ACT2_NORMAL, ACT2_ELITE, ACT2_BOSS),
            ("act3", ACT3_WEAK, ACT3_NORMAL, ACT3_ELITE, ACT3_BOSS),
            ("act4", ACT4_WEAK, ACT4_NORMAL, ACT4_ELITE, ACT4_BOSS),
        ]:
            assert len(weak) >= 2, f"{name} has too few weak encounters"
            assert len(normal) >= 5, f"{name} has too few normal encounters"
            assert len(elite) >= 2, f"{name} has too few elite encounters"
            assert len(boss) >= 2, f"{name} has too few boss encounters"
