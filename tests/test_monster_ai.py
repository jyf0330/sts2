"""Tests for monster AI state machine."""

import pytest

from sts2_env.cards.factory import create_card
from sts2_env.cards.ironclad import create_ironclad_starter_deck, make_battle_trance, make_thunderclap
from sts2_env.cards.ironclad_basic import make_strike_ironclad
from sts2_env.core.combat import CombatState
from sts2_env.core.damage import apply_damage
from sts2_env.core.enums import CardId, CombatSide, PowerId, RoomType, ValueProp
from sts2_env.core.enums import MoveRepeatType
from sts2_env.core.rng import Rng
from sts2_env.encounters.act2 import (
    setup_infested_prisms_elite,
    setup_kaiser_crab_boss,
    setup_mytes_normal,
    setup_tunneler_normal,
)
from sts2_env.encounters.act3 import (
    setup_construct_menagerie_normal,
    setup_doormaker_boss,
    setup_knights_elite,
    setup_queen_boss,
    setup_turret_operator_weak,
)
from sts2_env.encounters.act4 import (
    setup_corpse_slugs_normal,
    setup_corpse_slugs_weak,
    setup_lagavulin_matriarch_boss,
    setup_phantasmal_gardeners_elite,
    setup_seapunk_weak,
    setup_sludge_spinner_weak,
    setup_soul_fysh_boss,
    setup_toadpoles_normal,
    setup_toadpoles_weak,
    setup_two_tailed_rats_normal,
    setup_waterfall_giant_boss,
)
from sts2_env.encounters.events import setup_mysterious_knight
from sts2_env.monsters.act1 import (
    apply_cubex_construct_room_setup,
    create_axe_ruby_raider,
    create_assassin_ruby_raider,
    create_brute_ruby_raider,
    create_byrdonis,
    create_bygone_effigy,
    create_crossbow_ruby_raider,
    create_cubex_construct,
    create_ceremonial_beast,
    create_eye_with_teeth,
    create_flyconid,
    create_fogmog,
    create_inklet,
    create_kin_follower,
    create_kin_priest,
    create_mawler,
    create_parafright,
    create_phrog_parasite,
    create_slithering_strangler,
    create_tracker_ruby_raider,
)
from sts2_env.monsters.act1_weak import create_leaf_slime_m
from sts2_env.monsters.act4 import (
    create_calcified_cultist,
    create_corpse_slug,
    create_damp_cultist,
    create_fat_gremlin,
    create_fossil_stalker,
    create_gas_bomb,
    create_gremlin_merc,
    create_haunted_ship,
    create_lagavulin_matriarch,
    create_living_fog,
    create_phantasmal_gardener,
    create_punch_construct,
    create_seapunk,
    create_sewer_clam,
    create_sludge_spinner,
    create_skulking_colony,
    create_sneaky_gremlin,
    create_soul_fysh,
    create_terror_eel,
    create_toadpole,
    create_two_tailed_rat,
    create_waterfall_giant,
)
from sts2_env.monsters.act2 import (
    _steal_card_with_swipe,
    create_bowlbug_egg,
    create_bowlbug_nectar,
    create_bowlbug_rock,
    create_bowlbug_silk,
    create_chomper,
    create_crusher,
    create_decimillipede_segment,
    create_decimillipede_segment_back,
    create_decimillipede_segment_front,
    create_decimillipede_segment_middle,
    create_entomancer,
    create_exoskeleton,
    create_hunter_killer,
    create_infested_prism,
    create_knowledge_demon,
    create_louse_progenitor,
    create_myte,
    create_ovicopter,
    create_rocket,
    create_slumbering_beetle,
    create_spiny_toad,
    create_thieving_hopper,
    create_the_obscura,
    create_the_insatiable,
    create_tough_egg,
    create_tunneler,
    create_wriggler,
)
from sts2_env.monsters.shared import (
    create_battle_friend_v2,
    create_battle_friend_v3,
    create_big_dummy,
    create_battle_friend_v1,
    create_dense_vegetation_wriggler,
    create_fake_merchant_monster,
    create_multi_attack_move_monster,
    create_one_hp_monster,
    create_single_attack_move_monster,
    create_ten_hp_monster,
    create_the_adversary_mk_one,
    create_the_adversary_mk_two,
    create_the_adversary_mk_three,
)
from sts2_env.monsters.act3 import (
    create_axebot,
    create_devoted_sculptor,
    create_fabricator,
    create_flail_knight,
    create_frog_knight,
    create_globe_head,
    create_guardbot,
    create_living_shield,
    create_magi_knight,
    create_mecha_knight,
    create_noisebot,
    create_owl_magistrate,
    create_scroll_of_biting,
    create_slimed_berserker,
    create_soul_nexus,
    create_stabbot,
    create_spectral_knight,
    create_the_forgotten,
    create_the_lost,
    create_door,
    create_doormaker,
    create_turret_operator,
    create_zapbot,
)
from sts2_env.monsters.intents import attack_intent, buff_intent, debuff_intent
from sts2_env.monsters.state_machine import (
    MonsterAI, MoveState, RandomBranchState, ConditionalBranchState,
)
from sts2_env.powers.base import PowerInstance
from sts2_env.run.rooms import CombatRoom
from sts2_env.run.run_state import PlayerState


# ---- Helpers ----

class _BlockHookCounterPower(PowerInstance):
    def __init__(self):
        super().__init__(PowerId.JUGGERNAUT, 0)
        self.calls: list[int] = []

    def after_block_gained(self, owner, creature, amount, combat):
        if creature is owner:
            self.calls.append(amount)


def _noop(combat):
    """Dummy effect for test moves."""
    pass


def _make_move(state_id: str, follow_up_id: str, must_perform_once: bool = False) -> MoveState:
    return MoveState(state_id, _noop, [attack_intent(1)], follow_up_id=follow_up_id,
                     must_perform_once=must_perform_once)


def _run_ai(ai: MonsterAI, rng: Rng, n: int) -> list[str]:
    """Perform n moves and return list of state_ids."""
    moves = [ai.current_move.state_id]
    ai.on_move_performed()
    for _ in range(n - 1):
        ai.roll_move(rng)
        moves.append(ai.current_move.state_id)
        ai.on_move_performed()
    return moves


def _make_combat(seed: int = 7) -> CombatState:
    return CombatState(
        player_hp=80,
        player_max_hp=80,
        deck=create_ironclad_starter_deck(),
        rng_seed=seed,
        character_id="Ironclad",
    )


CS_MONSTER_FACTORY_PARITY_CASES = [
    ("BattleFriendV2", create_battle_friend_v2, "BATTLE_FRIEND_V2", "NOTHING_MOVE", 150, 150),
    ("BattleFriendV3", create_battle_friend_v3, "BATTLE_FRIEND_V3", "NOTHING_MOVE", 300, 300),
    ("BigDummy", create_big_dummy, "BIG_DUMMY", "NOTHING", 9999, 9999),
    ("DecimillipedeSegmentBack", create_decimillipede_segment_back, "DECIMILLIPEDE_SEGMENT_BACK", "WRITHE_MOVE", 42, 48),
    ("DecimillipedeSegmentFront", create_decimillipede_segment_front, "DECIMILLIPEDE_SEGMENT_FRONT", "WRITHE_MOVE", 42, 48),
    (
        "DecimillipedeSegmentMiddle",
        create_decimillipede_segment_middle,
        "DECIMILLIPEDE_SEGMENT_MIDDLE",
        "WRITHE_MOVE",
        42,
        48,
    ),
    ("FakeMerchantMonster", create_fake_merchant_monster, "FAKE_MERCHANT_MONSTER", "SWIPE", 165, 165),
    ("Inklet", create_inklet, "INKLET", "SPLATTER", 30, 33),
    ("KinFollower", create_kin_follower, "KIN_FOLLOWER", "BASH", 65, 71),
    ("KinPriest", create_kin_priest, "KIN_PRIEST", "CONVERSION", 119, 119),
    ("LeafSlimeM", create_leaf_slime_m, "LEAF_SLIME_M", "STICKY_SHOT", 32, 35),
    ("MultiAttackMoveMonster", create_multi_attack_move_monster, "MULTI_ATTACK_MOVE_MONSTER", "POKE", 999, 999),
    ("OneHpMonster", create_one_hp_monster, "ONE_HP_MONSTER", "NOTHING", 1, 1),
    ("SingleAttackMoveMonster", create_single_attack_move_monster, "SINGLE_ATTACK_MOVE_MONSTER", "POKE", 999, 999),
    ("TenHpMonster", create_ten_hp_monster, "TEN_HP_MONSTER", "NOTHING", 10, 10),
]


@pytest.mark.parametrize(
    "cs_name, factory, expected_monster_id, expected_initial_move, min_hp, max_hp",
    CS_MONSTER_FACTORY_PARITY_CASES,
    ids=[case[0] for case in CS_MONSTER_FACTORY_PARITY_CASES],
)
def test_cs_named_monster_factory_maps_to_expected_model(
    cs_name,
    factory,
    expected_monster_id,
    expected_initial_move,
    min_hp,
    max_hp,
):
    creature, ai = factory(Rng(42))

    assert cs_name
    assert creature.monster_id == expected_monster_id
    assert min_hp <= creature.max_hp <= max_hp
    assert creature.current_hp == creature.max_hp
    assert ai.current_move.state_id == expected_initial_move


# ========================================================================
# 1. Fixed rotation (MoveState follow-up chains)
# ========================================================================

class TestFixedRotation:
    def test_three_state_cycle(self):
        """A->B->C->A produces A,B,C,A,B,C."""
        rng = Rng(0)
        states = {
            "A": _make_move("A", "B"),
            "B": _make_move("B", "C"),
            "C": _make_move("C", "A"),
        }
        ai = MonsterAI(states, "A")
        moves = _run_ai(ai, rng, 6)
        assert moves == ["A", "B", "C", "A", "B", "C"]

    def test_two_state_cycle(self):
        """A->B->A produces A,B,A,B."""
        rng = Rng(0)
        states = {
            "A": _make_move("A", "B"),
            "B": _make_move("B", "A"),
        }
        ai = MonsterAI(states, "A")
        moves = _run_ai(ai, rng, 4)
        assert moves == ["A", "B", "A", "B"]

    def test_shrinker_beetle_rotation(self, rng):
        """ShrinkerBeetle: SHRINKER_MOVE -> CHOMP_MOVE -> STOMP_MOVE -> CHOMP_MOVE -> STOMP_MOVE."""
        from sts2_env.monsters.act1_weak import create_shrinker_beetle
        _, ai = create_shrinker_beetle(rng)

        moves = _run_ai(ai, rng, 5)
        assert moves == ["SHRINKER_MOVE", "CHOMP_MOVE", "STOMP_MOVE", "CHOMP_MOVE", "STOMP_MOVE"]

    def test_act1_weak_slimes_use_original_move_ids(self, rng):
        from sts2_env.monsters.act1_weak import create_leaf_slime_s, create_twig_slime_m, create_twig_slime_s

        _, leaf_s_ai = create_leaf_slime_s(rng)
        assert {"BUTT_MOVE", "GOOP_MOVE"}.issubset(leaf_s_ai.states)
        assert leaf_s_ai.current_move.state_id in {"BUTT_MOVE", "GOOP_MOVE"}

        _, twig_s_ai = create_twig_slime_s(rng)
        assert twig_s_ai.current_move.state_id == "BUTT_MOVE"

        _, twig_m_ai = create_twig_slime_m(rng)
        assert {"STICKY_SHOT_MOVE", "CLUMP_SHOT_MOVE"}.issubset(twig_m_ai.states)
        assert twig_m_ai.current_move.state_id == "STICKY_SHOT_MOVE"

    def test_single_state_self_loop(self):
        """A->A stays on A forever."""
        rng = Rng(0)
        states = {
            "A": _make_move("A", "A"),
        }
        ai = MonsterAI(states, "A")
        moves = _run_ai(ai, rng, 5)
        assert moves == ["A", "A", "A", "A", "A"]

    def test_adversary_barrage_does_not_gain_strength_after_killing_player(self):
        cases = [
            (create_the_adversary_mk_one, "BARRAGE"),
            (create_the_adversary_mk_two, "BARRAGE"),
            (create_the_adversary_mk_three, "BARRAGE"),
        ]
        for idx, (factory, move_id) in enumerate(cases, start=1):
            combat = _make_combat(200 + idx)
            creature, ai = factory(Rng(200 + idx))
            combat.add_enemy(creature, ai)
            combat.player.current_hp = 8

            ai.states[move_id].perform(combat)

            assert combat.is_over
            assert combat.player_won is False
            assert creature.get_power_amount(PowerId.STRENGTH) == 0

    def test_the_insatiable_follows_liquify_to_fixed_cycle(self):
        rng = Rng(7)
        _, ai = create_the_insatiable(rng)

        moves = _run_ai(ai, rng, 6)
        assert moves == [
            "LIQUIFY_GROUND_MOVE",
            "THRASH_MOVE_1",
            "LUNGING_BITE_MOVE",
            "SALIVATE_MOVE",
            "THRASH_MOVE_2",
            "THRASH_MOVE_1",
        ]

    def test_the_insatiable_liquify_applies_sandpit_and_frantic_escape(self):
        rng = Rng(7)
        combat = CombatState(
            player_hp=80,
            player_max_hp=80,
            deck=create_ironclad_starter_deck(),
            rng_seed=7,
            character_id="Ironclad",
        )
        creature, ai = create_the_insatiable(rng)
        combat.add_enemy(creature, ai)

        ai.current_move.perform(combat)
        ai.on_move_performed()

        sandpit = creature.powers.get(PowerId.SANDPIT)
        assert sandpit is not None
        assert getattr(sandpit, "target", None) is combat.player
        draw_frantic = [card for card in combat.draw_pile if card.card_id == CardId.FRANTIC_ESCAPE]
        discard_frantic = [card for card in combat.discard_pile if card.card_id == CardId.FRANTIC_ESCAPE]
        assert len(draw_frantic) == 3
        assert len(discard_frantic) == 3

    def test_knowledge_demon_curse_choice_pauses_enemy_turn_and_resumes_after_choice(self):
        combat = CombatState(
            player_hp=250,
            player_max_hp=250,
            deck=create_ironclad_starter_deck(),
            rng_seed=11,
            character_id="Ironclad",
        )
        creature, ai = create_knowledge_demon(Rng(11))
        combat.add_enemy(creature, ai)
        combat.start_combat()

        combat.end_player_turn()

        assert combat.current_side == CombatSide.ENEMY
        assert combat.pending_choice is not None
        assert [option.card.card_id for option in combat.pending_choice.options] == [
            CardId.DISINTEGRATION,
            CardId.MIND_ROT,
        ]

        assert combat.resolve_pending_choice(1)

        assert combat.pending_choice is None
        assert combat.primary_player.get_power_amount(PowerId.MIND_ROT) == 1
        assert combat.current_side == CombatSide.PLAYER
        assert combat.round_number == 2
        assert ai.current_move.state_id == "SLAP_MOVE"

    def test_knowledge_demon_curse_sets_and_disintegration_scaling_match_original_cycle(self):
        combat = CombatState(
            player_hp=250,
            player_max_hp=250,
            deck=create_ironclad_starter_deck(),
            rng_seed=12,
            character_id="Ironclad",
        )
        creature, ai = create_knowledge_demon(Rng(12))
        combat.add_enemy(creature, ai)
        combat.start_combat()

        combat.end_player_turn()
        assert combat.resolve_pending_choice(1)

        for _ in range(3):
            combat.end_player_turn()
        combat.end_player_turn()

        assert combat.pending_choice is not None
        assert [option.card.card_id for option in combat.pending_choice.options] == [
            CardId.DISINTEGRATION,
            CardId.SLOTH_STATUS,
        ]
        assert combat.resolve_pending_choice(0)
        assert combat.primary_player.get_power_amount(PowerId.DISINTEGRATION) == 7

        for _ in range(3):
            combat.end_player_turn()
        combat.end_player_turn()

        assert combat.pending_choice is not None
        assert [option.card.card_id for option in combat.pending_choice.options] == [
            CardId.DISINTEGRATION,
            CardId.WASTE_AWAY,
        ]
        assert combat.resolve_pending_choice(1)
        assert combat.primary_player.get_power_amount(PowerId.WASTE_AWAY) == 1

    def test_construct_menagerie_uses_punch_and_two_cubex_constructs(self):
        combat = CombatState(
            player_hp=80,
            player_max_hp=80,
            deck=create_ironclad_starter_deck(),
            rng_seed=9,
            character_id="Ironclad",
        )

        setup_construct_menagerie_normal(combat, Rng(9))

        ids = [enemy.monster_id for enemy in combat.enemies]
        assert ids.count("PUNCH_CONSTRUCT") == 1
        assert ids.count("CUBEX_CONSTRUCT") == 2

        cubexes = [enemy for enemy in combat.enemies if enemy.monster_id == "CUBEX_CONSTRUCT"]
        assert [cubex.block for cubex in cubexes] == [13, 13]
        assert [cubex.get_power_amount(PowerId.ARTIFACT) for cubex in cubexes] == [1, 1]

    def test_fat_gremlin_flee_escapes_without_dying(self):
        combat = CombatState(
            player_hp=80,
            player_max_hp=80,
            deck=create_ironclad_starter_deck(),
            rng_seed=5,
            character_id="Ironclad",
        )
        creature, ai = create_fat_gremlin(Rng(5))
        combat.add_enemy(creature, ai)

        ai.current_move.perform(combat)
        ai.on_move_performed()
        ai.roll_move(Rng(5))
        ai.current_move.perform(combat)

        assert creature.escaped
        assert not creature.is_alive
        assert not creature.is_dead

    def test_battleworn_dummy_escapes_when_time_limit_expires(self):
        combat = CombatState(
            player_hp=80,
            player_max_hp=80,
            deck=create_ironclad_starter_deck(),
            rng_seed=5,
            character_id="Ironclad",
        )
        creature, ai = create_battle_friend_v1(Rng(5))
        combat.add_enemy(creature, ai)
        combat.start_combat()

        combat.end_player_turn()
        assert creature.get_power_amount(PowerId.BATTLEWORN_DUMMY_TIME_LIMIT) == 2

        combat.end_player_turn()
        assert creature.get_power_amount(PowerId.BATTLEWORN_DUMMY_TIME_LIMIT) == 1

        combat.end_player_turn()

        assert creature.escaped
        assert not creature.is_alive
        assert not creature.is_dead

    def test_punch_construct_supports_strong_punch_start_and_hp_reduction(self):
        creature, ai = create_punch_construct(
            Rng(5),
            starts_with_strong_punch=True,
            starting_hp_reduction=7,
        )

        assert creature.current_hp == creature.max_hp - 7
        assert ai.current_move.state_id == "STRONG_PUNCH_MOVE"

    def test_bygone_effigy_uses_original_move_ids_and_wake_buff(self):
        combat = _make_combat(10)
        creature, ai = create_bygone_effigy(Rng(10))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 127
        assert creature.get_power_amount(PowerId.SLOW) == 1
        assert _run_ai(ai, Rng(10), 4) == [
            "INITIAL_SLEEP_MOVE",
            "WAKE_MOVE",
            "SLASHES_MOVE",
            "SLASHES_MOVE",
        ]

        wake_creature, wake_ai = create_bygone_effigy(Rng(10))
        combat.add_enemy(wake_creature, wake_ai)
        assert wake_ai.current_move.state_id == "INITIAL_SLEEP_MOVE"
        wake_ai.on_move_performed()
        wake_ai.roll_move(Rng(10))
        wake_ai.current_move.perform(combat)

        assert wake_creature.get_power_amount(PowerId.STRENGTH) == 10

    def test_ceremonial_beast_attack_buffs_stop_after_killing_player(self):
        plow_combat = _make_combat(110)
        plow_beast, plow_ai = create_ceremonial_beast(Rng(110))
        plow_combat.add_enemy(plow_beast, plow_ai)
        plow_combat.player.current_hp = 18
        plow_ai.states["PLOW"].perform(plow_combat)
        assert plow_combat.is_over
        assert plow_combat.player_won is False
        assert plow_beast.get_power_amount(PowerId.STRENGTH) == 0

        crush_combat = _make_combat(111)
        crush_beast, crush_ai = create_ceremonial_beast(Rng(111))
        crush_combat.add_enemy(crush_beast, crush_ai)
        crush_combat.player.current_hp = 17
        crush_ai.states["CRUSH"].perform(crush_combat)
        assert crush_combat.is_over
        assert crush_combat.player_won is False
        assert crush_beast.get_power_amount(PowerId.STRENGTH) == 0

    def test_act1_normal_monsters_use_original_move_ids(self):
        cubex, cubex_ai = create_cubex_construct(Rng(11))
        assert cubex_ai.current_move.state_id == "CHARGE_UP_MOVE"
        assert {"REPEATER_MOVE", "REPEATER_MOVE_2", "EXPEL_BLAST", "SUBMERGE_MOVE"}.issubset(cubex_ai.states)
        assert cubex.block == 0
        assert cubex.get_power_amount(PowerId.ARTIFACT) == 0
        combat = _make_combat(11)
        combat.add_enemy(cubex, cubex_ai)
        apply_cubex_construct_room_setup(cubex, combat)
        assert cubex.block == 13
        assert cubex.get_power_amount(PowerId.ARTIFACT) == 1

        _, flyconid_ai = create_flyconid(Rng(12))
        assert {"VULNERABLE_SPORES_MOVE", "FRAIL_SPORES_MOVE", "SMASH_MOVE"}.issubset(flyconid_ai.states)
        assert flyconid_ai.current_move.state_id in {"FRAIL_SPORES_MOVE", "SMASH_MOVE"}

        _, eye_ai = create_eye_with_teeth(Rng(13))
        assert eye_ai.current_move.state_id == "DISTRACT_MOVE"

        _, fogmog_ai = create_fogmog(Rng(14))
        assert fogmog_ai.current_move.state_id == "ILLUSION_MOVE"
        assert {"SWIPE_MOVE", "SWIPE_RANDOM_MOVE", "HEADBUTT_MOVE"}.issubset(fogmog_ai.states)

        lethal_fogmog, lethal_fogmog_ai = create_fogmog(Rng(114))
        lethal_fogmog_combat = _make_combat(114)
        lethal_fogmog_combat.add_enemy(lethal_fogmog, lethal_fogmog_ai)
        lethal_fogmog_combat.player.current_hp = 8
        lethal_fogmog_ai.states["SWIPE_MOVE"].perform(lethal_fogmog_combat)
        assert lethal_fogmog_combat.is_over
        assert lethal_fogmog_combat.player_won is False
        assert lethal_fogmog.get_power_amount(PowerId.STRENGTH) == 0

        _, mawler_ai = create_mawler(Rng(15))
        assert mawler_ai.current_move.state_id == "CLAW_MOVE"
        assert {"RIP_AND_TEAR_MOVE", "ROAR_MOVE", "CLAW_MOVE"}.issubset(mawler_ai.states)

        _, assassin_ai = create_assassin_ruby_raider(Rng(16))
        assert assassin_ai.current_move.state_id == "KILLSHOT_MOVE"

        _, brute_ai = create_brute_ruby_raider(Rng(17))
        assert brute_ai.current_move.state_id == "BEAT_MOVE"
        assert brute_ai.states["BEAT_MOVE"].follow_up_id == "ROAR_MOVE"

        _, crossbow_ai = create_crossbow_ruby_raider(Rng(18))
        assert crossbow_ai.current_move.state_id == "RELOAD_MOVE"
        assert crossbow_ai.states["RELOAD_MOVE"].follow_up_id == "FIRE_MOVE"

        _, tracker_ai = create_tracker_ruby_raider(Rng(19))
        assert tracker_ai.current_move.state_id == "TRACK_MOVE"
        assert tracker_ai.states["HOUNDS_MOVE"].follow_up_id == "HOUNDS_MOVE"

        _, byrdonis_ai = create_byrdonis(Rng(20))
        assert byrdonis_ai.current_move.state_id == "SWOOP_MOVE"
        assert byrdonis_ai.states["SWOOP_MOVE"].follow_up_id == "PECK_MOVE"

    def test_slithering_strangler_uses_original_constrict_rotation(self):
        combat = _make_combat(21)
        creature, ai = create_slithering_strangler(Rng(21))
        combat.add_enemy(creature, ai)

        assert 53 <= creature.max_hp <= 55
        assert ai.current_move.state_id == "CONSTRICT"
        assert combat.player.get_power_amount(PowerId.CONSTRICT) == 0

        ai.current_move.perform(combat)
        assert combat.player.get_power_amount(PowerId.CONSTRICT) == 3

        ai.on_move_performed()
        ai.roll_move(Rng(21))
        assert ai.current_move.state_id in {"TWACK", "LASH"}

        combat.player.current_hp = 80
        creature.block = 0
        ai.states["TWACK"].perform(combat)
        assert combat.player.current_hp == 73
        assert creature.block == 5

        combat.player.current_hp = 80
        ai.states["LASH"].perform(combat)
        assert combat.player.current_hp == 68

    def test_act1_monster_block_moves_trigger_after_block_gained_hooks(self):
        from sts2_env.monsters.act1_weak import create_nibbit

        cases = [
            (create_nibbit(Rng(1)), "SLICE_MOVE", 5),
            (create_slithering_strangler(Rng(2)), "TWACK", 5),
            (create_axe_ruby_raider(Rng(3)), "SWING_1", 5),
            (create_crossbow_ruby_raider(Rng(4)), "RELOAD_MOVE", 3),
            (create_cubex_construct(Rng(5)), "SUBMERGE_MOVE", 15),
        ]

        for (creature, ai), state_id, expected_block in cases:
            combat = _make_combat(120)
            combat.add_enemy(creature, ai)
            creature.block = 0
            counter = _BlockHookCounterPower()
            creature.powers[PowerId.JUGGERNAUT] = counter

            ai.states[state_id].perform(combat)

            assert creature.block == expected_block
            assert counter.calls == [expected_block]

    def test_act1_attack_block_move_does_not_gain_block_after_killing_player(self):
        creature, ai = create_axe_ruby_raider(Rng(3))
        combat = _make_combat(120)
        combat.add_enemy(creature, ai)
        combat.player.current_hp = 5
        creature.block = 0

        ai.states["SWING_1"].perform(combat)
        combat._check_combat_end()  # noqa: SLF001

        assert combat.is_over
        assert combat.player_won is False
        assert creature.block == 0

    def test_act1_attack_buff_move_does_not_apply_power_after_killing_player(self):
        creature, ai = create_cubex_construct(Rng(11))
        combat = _make_combat(121)
        combat.add_enemy(creature, ai)
        combat.player.current_hp = 7

        ai.states["REPEATER_MOVE"].perform(combat)

        assert combat.is_over
        assert combat.player_won is False
        assert creature.get_power_amount(PowerId.STRENGTH) == 0

    def test_cubex_initial_room_setup_triggers_after_block_gained_hook(self):
        combat = _make_combat(121)
        creature, ai = create_cubex_construct(Rng(121))
        combat.add_enemy(creature, ai)
        counter = _BlockHookCounterPower()
        creature.powers[PowerId.JUGGERNAUT] = counter

        apply_cubex_construct_room_setup(creature, combat)

        assert creature.block == 13
        assert creature.get_power_amount(PowerId.ARTIFACT) == 1
        assert counter.calls == [13]

    def test_thieving_hopper_has_original_stats_and_fixed_escape_rotation(self):
        creature, ai = create_thieving_hopper(Rng(11))

        assert creature.max_hp == 79
        assert creature.get_power_amount(PowerId.ESCAPE_ARTIST) == 5
        assert PowerId.THIEVERY not in creature.powers
        assert ai.current_move.intents[1].intent_type.name == "CARD_DEBUFF"
        assert _run_ai(ai, Rng(11), 6) == [
            "THIEVERY_MOVE",
            "FLUTTER_MOVE",
            "HAT_TRICK_MOVE",
            "NAB_MOVE",
            "ESCAPE_MOVE",
            "ESCAPE_MOVE",
        ]

    def test_thieving_hopper_steals_card_not_gold_and_returns_it_on_death(self):
        combat = _make_combat(12)
        combat.room = CombatRoom(room_type=RoomType.MONSTER)
        creature, ai = create_thieving_hopper(Rng(12))
        combat.add_enemy(creature, ai)
        combat.start_combat()
        state = combat.combat_player_state_for(combat.primary_player)
        basic = make_strike_ironclad()
        common = make_thunderclap()
        uncommon = make_battle_trance()
        for card in (basic, common, uncommon):
            card.owner = combat.primary_player
        state.player_state.deck[:] = [basic, common, uncommon]
        state.hand.clear()
        state.draw[:] = [basic, common, uncommon]
        state.discard.clear()
        state.exhaust.clear()
        state.play.clear()
        combat.gold = 50

        ai.current_move.perform(combat)

        assert uncommon not in state.draw
        assert all(card is not uncommon for card in state.player_state.deck)
        assert combat.gold == 50
        assert creature.powers[PowerId.SWIPE].stolen_card is uncommon
        assert combat.primary_player.current_hp == 63

        assert combat.kill_creature(creature)
        assert any(card is uncommon for card in state.player_state.deck)
        rewards = combat.room.extra_rewards[combat.player_id]
        assert rewards[0].card is uncommon
        assert rewards[0].encounter_source == "THIEVING_HOPPER"

    def test_thieving_hopper_steals_from_pet_owner_when_targeting_pet(self):
        rng_seed = 1212
        osty_hp = 5
        combat = _make_combat(rng_seed)
        combat.room = CombatRoom(room_type=RoomType.MONSTER)
        creature, ai = create_thieving_hopper(Rng(rng_seed))
        combat.add_enemy(creature, ai)
        combat.start_combat()
        state = combat.combat_player_state_for(combat.primary_player)
        assert state is not None
        stolen_card = make_battle_trance()
        stolen_card.owner = combat.primary_player
        state.player_state.deck[:] = [stolen_card]
        state.hand.clear()
        state.draw[:] = [stolen_card]
        state.discard.clear()
        combat.summon_osty(combat.primary_player, osty_hp)
        assert combat.osty is not None

        _steal_card_with_swipe(combat, creature, combat.osty)

        assert stolen_card not in state.draw
        assert stolen_card not in state.player_state.deck
        assert creature.powers[PowerId.SWIPE].stolen_card is stolen_card

        assert combat.kill_creature(creature)
        assert stolen_card in state.player_state.deck
        rewards = combat.room.extra_rewards[combat.player_id]
        assert rewards[0].card is stolen_card

    def test_thieving_hopper_default_targets_do_not_steal_extra_card_from_osty_owner(self):
        rng_seed = 1213
        osty_hp = 5
        combat = _make_combat(rng_seed)
        combat.room = CombatRoom(room_type=RoomType.MONSTER)
        creature, ai = create_thieving_hopper(Rng(rng_seed))
        combat.add_enemy(creature, ai)
        combat.start_combat()
        state = combat.combat_player_state_for(combat.primary_player)
        assert state is not None
        first_card = make_battle_trance()
        second_card = make_thunderclap()
        for card in (first_card, second_card):
            card.owner = combat.primary_player
        state.player_state.deck[:] = [first_card, second_card]
        state.hand.clear()
        state.draw[:] = [first_card, second_card]
        state.discard.clear()
        combat.summon_osty(combat.primary_player, osty_hp)

        ai.current_move.perform(combat)

        assert len(state.player_state.deck) == 1
        assert len(state.draw) == 1
        assert creature.powers[PowerId.SWIPE].amount == 1

    def test_act2_tunneler_uses_original_burrow_cycle_and_unburrow_stun(self):
        combat = _make_combat(22)
        creature, ai = create_tunneler(Rng(22))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 87
        assert ai.current_move.state_id == "BITE_MOVE"
        assert {"BURROW_MOVE", "BELOW_MOVE_1", "DIZZY_MOVE"}.issubset(ai.states)
        assert _run_ai(ai, Rng(22), 4) == ["BITE_MOVE", "BURROW_MOVE", "BELOW_MOVE_1", "BELOW_MOVE_1"]

        creature, ai = create_tunneler(Rng(23))
        combat.add_enemy(creature, ai)
        ai.on_move_performed()
        ai.roll_move(Rng(23))
        assert ai.current_move.state_id == "BURROW_MOVE"

        ai.current_move.perform(combat)
        assert creature.get_power_amount(PowerId.BURROWED) == 1
        assert creature.block == 32

        ai.on_move_performed()
        ai.roll_move(Rng(23))
        assert ai.current_move.state_id == "BELOW_MOVE_1"

        apply_damage(creature, 40, ValueProp.MOVE, combat, combat.player)
        assert creature.get_power_amount(PowerId.BURROWED) == 0
        assert creature.block == 0
        assert ai.current_move.state_id == "DIZZY_MOVE"

        ai.current_move.perform(combat)
        ai.on_move_performed()
        ai.roll_move(Rng(23))
        assert ai.current_move.state_id == "BITE_MOVE"

    def test_act2_monster_block_moves_trigger_after_block_gained_hooks(self):
        cases = [
            (create_tunneler(Rng(1)), "BURROW_MOVE", 32),
            (create_bowlbug_egg(Rng(2)), "BITE_MOVE", 7),
            (create_louse_progenitor(Rng(3)), "CURL_AND_GROW_MOVE", 14),
            (create_the_obscura(Rng(4)), "HARDENING_STRIKE_MOVE", 6),
            (create_infested_prism(Rng(5)), "RADIATE_MOVE", 16),
            (create_infested_prism(Rng(6)), "PULSATE_MOVE", 20),
            (create_crusher(Rng(7)), "GUARDED_STRIKE_MOVE", 18),
        ]

        for (creature, ai), state_id, expected_block in cases:
            combat = _make_combat(121)
            combat.add_enemy(creature, ai)
            creature.block = 0
            counter = _BlockHookCounterPower()
            creature.powers[PowerId.JUGGERNAUT] = counter

            ai.states[state_id].perform(combat)

            assert creature.block == expected_block
            assert counter.calls == [expected_block]

    def test_act2_workbugs_use_original_move_ids_and_setup_powers(self):
        _, egg_ai = create_bowlbug_egg(Rng(24))
        assert egg_ai.current_move.state_id == "BITE_MOVE"

        _, nectar_ai = create_bowlbug_nectar(Rng(25))
        assert _run_ai(nectar_ai, Rng(25), 4) == [
            "THRASH_MOVE",
            "BUFF_MOVE",
            "THRASH2_MOVE",
            "THRASH2_MOVE",
        ]

        rock, rock_ai = create_bowlbug_rock(Rng(26))
        assert rock.get_power_amount(PowerId.IMBALANCED) == 1
        assert rock_ai.current_move.state_id == "HEADBUTT_MOVE"
        assert {"POST_HEADBUTT", "DIZZY_MOVE"}.issubset(rock_ai.states)

        combat = _make_combat(26)
        combat.add_enemy(rock, rock_ai)
        combat.player.gain_block(99)
        rock_ai.current_move.perform(combat)
        assert getattr(rock.powers[PowerId.IMBALANCED], "was_fully_blocked", False)

        rock_ai.on_move_performed()
        rock_ai.roll_move(Rng(26))
        assert rock_ai.current_move.state_id == "DIZZY_MOVE"

        rock_ai.current_move.perform(combat)
        assert not getattr(rock.powers[PowerId.IMBALANCED], "was_fully_blocked", False)

        _, silk_ai = create_bowlbug_silk(Rng(27))
        assert _run_ai(silk_ai, Rng(27), 3) == ["TOXIC_SPIT_MOVE", "TRASH_MOVE", "TOXIC_SPIT_MOVE"]

    def test_act2_exoskeletons_use_original_init_state_and_hard_to_kill(self):
        first, first_ai = create_exoskeleton(Rng(28), slot="first")
        assert first.get_power_amount(PowerId.HARD_TO_KILL) == 9
        assert first_ai.current_move.state_id == "SKITTER_MOVE"

        second, second_ai = create_exoskeleton(Rng(29), slot="second")
        assert second_ai.current_move.state_id == "MANDIBLE_MOVE"
        assert second_ai.states["MANDIBLE_MOVE"].follow_up_id == "ENRAGE_MOVE"

        third, third_ai = create_exoskeleton(Rng(30), slot="third")
        assert third_ai.current_move.state_id == "ENRAGE_MOVE"

        fourth_moves = {create_exoskeleton(Rng(seed), slot="fourth")[1].current_move.state_id for seed in range(31, 41)}
        assert fourth_moves == {"SKITTER_MOVE", "MANDIBLE_MOVE"}

    def test_act2_normal_chomper_and_hunter_killer_match_original_moves(self):
        chomper, chomper_ai = create_chomper(Rng(32))
        assert 60 <= chomper.max_hp <= 64
        assert chomper.get_power_amount(PowerId.ARTIFACT) == 2
        assert _run_ai(chomper_ai, Rng(32), 4) == [
            "CLAMP_MOVE",
            "SCREECH_MOVE",
            "CLAMP_MOVE",
            "SCREECH_MOVE",
        ]

        _, scream_ai = create_chomper(Rng(33), scream_first=True)
        assert scream_ai.current_move.state_id == "SCREECH_MOVE"

        combat = _make_combat(34)
        hunter, hunter_ai = create_hunter_killer(Rng(34))
        combat.add_enemy(hunter, hunter_ai)

        assert hunter.max_hp == 121
        assert hunter_ai.current_move.state_id == "TENDERIZING_GOOP_MOVE"
        assert {"BITE_MOVE", "PUNCTURE_MOVE", "RAND"}.issubset(hunter_ai.states)

        hunter_ai.current_move.perform(combat)
        assert combat.player.get_power_amount(PowerId.TENDER) == 1

        hunter_ai.on_move_performed()
        hunter_ai.roll_move(Rng(34))
        assert hunter_ai.current_move.state_id in {"BITE_MOVE", "PUNCTURE_MOVE"}

    def test_act2_ovicopter_and_tough_egg_match_original_opening_cycle(self):
        egg, egg_ai = create_tough_egg(Rng(35))
        assert 14 <= egg.max_hp <= 18
        assert egg.get_power_amount(PowerId.MINION) == 1
        assert egg.get_power_amount(PowerId.HATCH) == 1
        assert egg_ai.current_move.state_id == "HATCH_MOVE"

        egg_ai.current_move.perform(_make_combat(35))
        assert 19 <= egg.max_hp <= 22
        assert egg.current_hp == egg.max_hp
        assert egg.get_power_amount(PowerId.HATCH) == 0

        combat = _make_combat(36)
        ovicopter, ovicopter_ai = create_ovicopter(Rng(36))
        combat.add_enemy(ovicopter, ovicopter_ai)

        assert 124 <= ovicopter.max_hp <= 130
        assert ovicopter_ai.current_move.state_id == "LAY_EGGS_MOVE"

        ovicopter_ai.current_move.perform(combat)
        assert [enemy.monster_id for enemy in combat.enemies] == [
            "OVICOPTER",
            "TOUGH_EGG",
            "TOUGH_EGG",
            "TOUGH_EGG",
        ]

        expected_moves = ["SMASH_MOVE", "TENDERIZER_MOVE", "LAY_EGGS_MOVE"]
        actual_moves = []
        for _ in expected_moves:
            ovicopter_ai.on_move_performed()
            ovicopter_ai.roll_move(Rng(36))
            actual_moves.append(ovicopter_ai.current_move.state_id)
        assert actual_moves == expected_moves

        ovicopter_ai.current_move.perform(combat)
        assert len([enemy for enemy in combat.enemies if enemy.monster_id == "TOUGH_EGG"]) == 6

        ovicopter_ai.on_move_performed()
        ovicopter_ai.roll_move(Rng(36))
        assert ovicopter_ai.current_move.state_id == "SMASH_MOVE"
        ovicopter_ai.on_move_performed()
        ovicopter_ai.roll_move(Rng(36))
        assert ovicopter_ai.current_move.state_id == "TENDERIZER_MOVE"
        ovicopter_ai.on_move_performed()
        ovicopter_ai.roll_move(Rng(36))
        assert ovicopter_ai.current_move.state_id == "NUTRITIONAL_PASTE_MOVE"

    def test_act2_slumbering_beetle_and_spiny_toad_match_original_moves(self):
        beetle, beetle_ai = create_slumbering_beetle(Rng(37))
        assert beetle.max_hp == 86
        assert beetle.get_power_amount(PowerId.PLATING) == 15
        assert beetle.get_power_amount(PowerId.SLUMBER) == 3
        assert beetle_ai.current_move.state_id == "SNORE_MOVE"

        beetle_ai.on_move_performed()
        beetle_ai.roll_move(Rng(37))
        assert beetle_ai.current_move.state_id == "SNORE_MOVE"

        beetle.powers.pop(PowerId.SLUMBER)
        beetle_ai.on_move_performed()
        beetle_ai.roll_move(Rng(37))
        assert beetle_ai.current_move.state_id == "ROLL_OUT_MOVE"

        combat = _make_combat(37)
        combat.add_enemy(beetle, beetle_ai)
        beetle_ai.current_move.perform(combat)
        assert combat.player.current_hp == 64
        assert beetle.get_power_amount(PowerId.STRENGTH) == 2

        lethal_beetle, lethal_beetle_ai = create_slumbering_beetle(Rng(137))
        lethal_combat = _make_combat(137)
        lethal_combat.add_enemy(lethal_beetle, lethal_beetle_ai)
        lethal_beetle.powers.pop(PowerId.SLUMBER)
        lethal_combat.player.current_hp = 16
        lethal_beetle_ai.states["ROLL_OUT_MOVE"].perform(lethal_combat)
        assert lethal_combat.is_over
        assert lethal_combat.player_won is False
        assert lethal_beetle.get_power_amount(PowerId.STRENGTH) == 0

        toad, toad_ai = create_spiny_toad(Rng(38))
        combat.add_enemy(toad, toad_ai)

        assert 116 <= toad.max_hp <= 119
        assert _run_ai(toad_ai, Rng(38), 4) == [
            "PROTRUDING_SPIKES_MOVE",
            "SPIKE_EXPLOSION_MOVE",
            "TONGUE_LASH_MOVE",
            "PROTRUDING_SPIKES_MOVE",
        ]

        toad_ai.states["PROTRUDING_SPIKES_MOVE"].perform(combat)
        assert toad.get_power_amount(PowerId.THORNS) == 5

        toad_ai.states["SPIKE_EXPLOSION_MOVE"].perform(combat)
        assert toad.get_power_amount(PowerId.THORNS) == 0

    def test_act2_obscura_summons_original_parafright(self):
        parafright, parafright_ai = create_parafright(Rng(39))
        assert parafright.max_hp == 21
        assert parafright.get_power_amount(PowerId.ILLUSION) == 1
        assert parafright.get_power_amount(PowerId.MINION) == 1
        assert parafright_ai.current_move.state_id == "SLAM_MOVE"

        combat = _make_combat(39)
        obscura, obscura_ai = create_the_obscura(Rng(39))
        combat.add_enemy(obscura, obscura_ai)

        assert obscura.max_hp == 123
        assert obscura_ai.current_move.state_id == "ILLUSION_MOVE"
        assert {"PIERCING_GAZE_MOVE", "SAIL_MOVE", "HARDENING_STRIKE_MOVE"}.issubset(obscura_ai.states)

        obscura_ai.current_move.perform(combat)
        assert [enemy.monster_id for enemy in combat.enemies] == ["THE_OBSCURA", "PARAFRIGHT"]
        summoned = combat.enemies[1]
        assert summoned.max_hp == 21
        assert combat.enemy_ais[summoned.combat_id].current_move.state_id == "SLAM_MOVE"

        obscura_ai.states["SAIL_MOVE"].perform(combat)
        assert summoned.get_power_amount(PowerId.STRENGTH) == 3

        obscura_ai.states["HARDENING_STRIKE_MOVE"].perform(combat)
        assert obscura.block == 6
        assert combat.player.current_hp == 74

    def test_act2_elites_use_original_move_ids_and_entomancer_buff(self):
        assert create_decimillipede_segment(Rng(40), starter_idx=0)[1].current_move.state_id == "WRITHE_MOVE"
        assert create_decimillipede_segment(Rng(40), starter_idx=1)[1].current_move.state_id == "BULK_MOVE"
        segment, segment_ai = create_decimillipede_segment(Rng(40), starter_idx=2)
        assert segment_ai.current_move.state_id == "CONSTRICT_MOVE"
        assert {"DEAD_MOVE", "REATTACH_MOVE", "RAND"}.issubset(segment_ai.states)
        assert segment.get_power_amount(PowerId.REATTACH) == 25

        lethal_segment, lethal_segment_ai = create_decimillipede_segment(Rng(140), starter_idx=1)
        lethal_combat = _make_combat(140)
        lethal_combat.add_enemy(lethal_segment, lethal_segment_ai)
        lethal_combat.player.current_hp = 6
        lethal_segment_ai.states["BULK_MOVE"].perform(lethal_combat)
        assert lethal_combat.is_over
        assert lethal_combat.player_won is False
        assert lethal_segment.get_power_amount(PowerId.STRENGTH) == 0

        combat = _make_combat(41)
        entomancer, entomancer_ai = create_entomancer(Rng(41))
        combat.add_enemy(entomancer, entomancer_ai)

        assert entomancer.max_hp == 145
        assert entomancer.get_power_amount(PowerId.PERSONAL_HIVE) == 1
        assert _run_ai(entomancer_ai, Rng(41), 4) == [
            "BEES_MOVE",
            "SPEAR_MOVE",
            "PHEROMONE_SPIT_MOVE",
            "BEES_MOVE",
        ]

        entomancer_ai.states["PHEROMONE_SPIT_MOVE"].perform(combat)
        assert entomancer.get_power_amount(PowerId.PERSONAL_HIVE) == 2
        assert entomancer.get_power_amount(PowerId.STRENGTH) == 1

        entomancer_ai.states["PHEROMONE_SPIT_MOVE"].perform(combat)
        entomancer_ai.states["PHEROMONE_SPIT_MOVE"].perform(combat)
        assert entomancer.get_power_amount(PowerId.PERSONAL_HIVE) == 3
        assert entomancer.get_power_amount(PowerId.STRENGTH) == 4

    def test_act2_bosses_use_original_move_ids(self):
        knowledge, knowledge_ai = create_knowledge_demon(Rng(42))
        assert knowledge.max_hp == 379
        assert knowledge_ai.current_move.state_id == "CURSE_OF_KNOWLEDGE_MOVE"
        assert {"SLAP_MOVE", "KNOWLEDGE_OVERWHELMING_MOVE", "PONDER_MOVE"}.issubset(knowledge_ai.states)

        lethal_knowledge, lethal_knowledge_ai = create_knowledge_demon(Rng(142))
        lethal_knowledge.current_hp = 100
        lethal_combat = _make_combat(142)
        lethal_combat.add_enemy(lethal_knowledge, lethal_knowledge_ai)
        lethal_combat.player.current_hp = 11
        lethal_knowledge_ai.states["PONDER_MOVE"].perform(lethal_combat)
        assert lethal_combat.is_over
        assert lethal_combat.player_won is False
        assert lethal_knowledge.current_hp == 100
        assert lethal_knowledge.get_power_amount(PowerId.STRENGTH) == 0

        crusher, crusher_ai = create_crusher(Rng(43))
        assert crusher_ai.current_move.state_id == "THRASH_MOVE"
        assert _run_ai(crusher_ai, Rng(43), 5) == [
            "THRASH_MOVE",
            "ENLARGING_STRIKE_MOVE",
            "BUG_STING_MOVE",
            "ADAPT_MOVE",
            "GUARDED_STRIKE_MOVE",
        ]

        combat = _make_combat(44)
        rocket, rocket_ai = create_rocket(Rng(44))
        combat.add_enemy(rocket, rocket_ai)

        assert rocket_ai.current_move.state_id == "TARGETING_RETICLE_MOVE"
        assert _run_ai(rocket_ai, Rng(44), 6) == [
            "TARGETING_RETICLE_MOVE",
            "PRECISION_BEAM_MOVE",
            "CHARGE_UP_MOVE",
            "LASER_MOVE",
            "RECHARGE_MOVE",
            "TARGETING_RETICLE_MOVE",
        ]

        rocket_ai.states["TARGETING_RETICLE_MOVE"].perform(combat)
        assert combat.player.get_power_amount(PowerId.VULNERABLE) == 0

        rocket_ai.states["CHARGE_UP_MOVE"].perform(combat)
        assert rocket.get_power_amount(PowerId.STRENGTH) == 2

        crab_combat = _make_combat(45)
        setup_kaiser_crab_boss(crab_combat, Rng(45))
        assert [enemy.monster_id for enemy in crab_combat.enemies] == ["CRUSHER", "ROCKET"]
        assert crab_combat.player.get_power_amount(PowerId.SURROUNDED) == 1

    def test_tunneler_normal_uses_one_workbug_then_one_tunneler(self):
        combat = _make_combat(31)
        setup_tunneler_normal(combat, Rng(31))

        assert len(combat.enemies) == 2
        assert combat.enemies[0].monster_id in {"BOWLBUG_EGG", "BOWLBUG_SILK"}
        assert combat.enemies[1].monster_id == "TUNNELER"
        assert combat.enemy_ais[combat.enemies[1].combat_id].current_move.state_id == "BITE_MOVE"

    def test_phrog_parasite_infects_with_three_infections_then_lashes(self):
        combat = _make_combat(13)
        creature, ai = create_phrog_parasite(Rng(13))
        combat.add_enemy(creature, ai)

        assert 61 <= creature.max_hp <= 64
        assert creature.get_power_amount(PowerId.INFESTED) == 4
        assert ai.current_move.state_id == "INFECT_MOVE"

        ai.current_move.perform(combat)
        ai.on_move_performed()

        assert [card.card_id for card in combat.discard_pile] == [
            CardId.INFECTION,
            CardId.INFECTION,
            CardId.INFECTION,
        ]

        ai.roll_move(Rng(13))
        assert ai.current_move.state_id == "LASH_MOVE"

        before_hp = combat.player.current_hp
        ai.current_move.perform(combat)
        assert combat.player.current_hp == before_hp - 16

    def test_myte_slots_add_toxic_to_hand_and_start_on_expected_moves(self):
        combat = _make_combat(14)
        first, first_ai = create_myte(Rng(14), slot="first")
        combat.add_enemy(first, first_ai)

        assert 61 <= first.max_hp <= 67
        assert first_ai.current_move.state_id == "TOXIC_MOVE"

        rocket_punch = create_card(CardId.ROCKET_PUNCH)
        combat.hand = [rocket_punch]
        first_ai.current_move.perform(combat)
        assert [card.card_id for card in combat.hand] == [CardId.ROCKET_PUNCH, CardId.TOXIC, CardId.TOXIC]
        assert rocket_punch.cost == 0

        second, second_ai = create_myte(Rng(15), slot="second")
        combat.add_enemy(second, second_ai)

        assert 61 <= second.max_hp <= 67
        assert second_ai.current_move.state_id == "SUCK_MOVE"

        before_hp = combat.player.current_hp
        second_ai.current_move.perform(combat)
        assert combat.player.current_hp == before_hp - 4
        assert second.get_power_amount(PowerId.STRENGTH) == 2

        lethal_combat = _make_combat(16)
        lethal_myte, lethal_ai = create_myte(Rng(16), slot="second")
        lethal_combat.add_enemy(lethal_myte, lethal_ai)
        lethal_combat.player.current_hp = 4
        lethal_ai.current_move.perform(lethal_combat)
        assert lethal_combat.is_over
        assert lethal_combat.player_won is False
        assert lethal_myte.get_power_amount(PowerId.STRENGTH) == 0

        second_ai.on_move_performed()
        second_ai.roll_move(Rng(15))
        assert second_ai.current_move.state_id == "TOXIC_MOVE"

        encounter_combat = _make_combat(16)
        setup_mytes_normal(encounter_combat, Rng(16))
        assert [enemy.monster_id for enemy in encounter_combat.enemies] == ["MYTE", "MYTE"]
        assert [
            encounter_combat.enemy_ais[enemy.combat_id].current_move.state_id
            for enemy in encounter_combat.enemies
        ] == ["TOXIC_MOVE", "SUCK_MOVE"]

    def test_infested_prism_is_single_elite_with_fixed_rotation_and_no_statuses(self):
        combat = _make_combat(17)
        creature, ai = create_infested_prism(Rng(17))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 200
        assert creature.get_power_amount(PowerId.VITAL_SPARK) == 1
        assert ai.current_move.state_id == "JAB_MOVE"

        moves = []
        for _ in range(4):
            moves.append(ai.current_move.state_id)
            ai.current_move.perform(combat)
            ai.on_move_performed()
            ai.roll_move(Rng(17))

        assert moves == ["JAB_MOVE", "RADIATE_MOVE", "WHIRLWIND_MOVE", "PULSATE_MOVE"]
        assert creature.block == 36
        assert creature.get_power_amount(PowerId.STRENGTH) == 4
        assert all(card.card_id not in (CardId.INFECTION, CardId.PARASITE) for card in combat.discard_pile)

        encounter_combat = _make_combat(18)
        setup_infested_prisms_elite(encounter_combat, Rng(18))
        assert [enemy.monster_id for enemy in encounter_combat.enemies] == ["INFESTED_PRISM"]

    def test_wriggler_slots_and_spawned_stun_match_original(self):
        combat = _make_combat(19)

        first, first_ai = create_wriggler(Rng(19), slot="wriggler1")
        combat.add_enemy(first, first_ai)
        assert 17 <= first.max_hp <= 21
        assert first_ai.current_move.state_id == "NASTY_BITE_MOVE"

        second, second_ai = create_wriggler(Rng(20), slot="wriggler2")
        combat.add_enemy(second, second_ai)
        assert second_ai.current_move.state_id == "WRIGGLE_MOVE"

        second_ai.current_move.perform(combat)
        assert combat.discard_pile[-1].card_id == CardId.INFECTION
        assert second.get_power_amount(PowerId.STRENGTH) == 2

        spawned, spawned_ai = create_wriggler(
            Rng(21),
            slot="wriggler4",
            start_stunned=True,
        )
        combat.add_enemy(spawned, spawned_ai)
        assert spawned_ai.current_move.state_id == "SPAWNED_MOVE"

        spawned_ai.current_move.perform(combat)
        spawned_ai.on_move_performed()
        spawned_ai.roll_move(Rng(21))
        assert spawned_ai.current_move.state_id == "WRIGGLE_MOVE"

    def test_dense_vegetation_wriggler_wriggle_adds_infection(self):
        combat = _make_combat(22)
        creature, ai = create_dense_vegetation_wriggler(Rng(22), slot="wriggler2")
        combat.add_enemy(creature, ai)

        assert ai.current_move.state_id == "WRIGGLE_MOVE"
        ai.current_move.perform(combat)

        assert combat.discard_pile[-1].card_id == CardId.INFECTION
        assert creature.get_power_amount(PowerId.STRENGTH) == 2

    def test_louse_progenitor_uses_web_curl_pounce_cycle(self):
        combat = _make_combat(23)
        creature, ai = create_louse_progenitor(Rng(23))
        combat.add_enemy(creature, ai)

        assert 134 <= creature.max_hp <= 136
        assert creature.get_power_amount(PowerId.CURL_UP) == 14
        assert ai.current_move.state_id == "WEB_CANNON_MOVE"

        before_hp = combat.player.current_hp
        ai.current_move.perform(combat)
        assert combat.player.current_hp == before_hp - 9
        assert combat.player.get_power_amount(PowerId.FRAIL) == 2

        ai.on_move_performed()
        ai.roll_move(Rng(23))
        assert ai.current_move.state_id == "CURL_AND_GROW_MOVE"

        ai.current_move.perform(combat)
        assert creature.block == 14
        assert creature.get_power_amount(PowerId.STRENGTH) == 5

        ai.on_move_performed()
        ai.roll_move(Rng(23))
        assert ai.current_move.state_id == "POUNCE_MOVE"

    def test_devoted_sculptor_uses_original_opening_and_savage_loop(self):
        combat = _make_combat(40)
        creature, ai = create_devoted_sculptor(Rng(40))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 162
        assert ai.current_move.state_id == "FORBIDDEN_INCANTATION_MOVE"

        ai.current_move.perform(combat)
        assert creature.get_power_amount(PowerId.RITUAL) == 9

        ai.on_move_performed()
        ai.roll_move(Rng(40))
        assert ai.current_move.state_id == "SAVAGE_MOVE"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 68

        ai.on_move_performed()
        ai.roll_move(Rng(40))
        assert ai.current_move.state_id == "SAVAGE_MOVE"

    def test_frog_knight_uses_original_half_health_branch(self):
        combat = _make_combat(46)
        creature, ai = create_frog_knight(Rng(46))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 191
        assert creature.get_power_amount(PowerId.PLATING) == 15
        assert ai.current_move.state_id == "TONGUE_LASH"
        assert "HALF_HEALTH" in ai.states

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 67
        assert combat.player.get_power_amount(PowerId.FRAIL) == 2

        ai.on_move_performed()
        ai.roll_move(Rng(46))
        assert ai.current_move.state_id == "STRIKE_DOWN_EVIL"

        ai.on_move_performed()
        ai.roll_move(Rng(46))
        assert ai.current_move.state_id == "FOR_THE_QUEEN"

        creature.current_hp = 90
        ai.on_move_performed()
        ai.roll_move(Rng(46))
        assert ai.current_move.state_id == "BEETLE_CHARGE"

    def test_globe_head_uses_original_fixed_cycle(self):
        combat = _make_combat(47)
        creature, ai = create_globe_head(Rng(47))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 148
        assert creature.get_power_amount(PowerId.GALVANIC) == 6
        assert ai.current_move.state_id == "SHOCKING_SLAP"

        expected_moves = ["THUNDER_STRIKE", "GALVANIC_BURST", "SHOCKING_SLAP"]
        actual_moves = []
        for _ in expected_moves:
            ai.on_move_performed()
            ai.roll_move(Rng(47))
            actual_moves.append(ai.current_move.state_id)

        assert actual_moves == expected_moves

        lethal_combat = _make_combat(147)
        lethal_creature, lethal_ai = create_globe_head(Rng(147))
        lethal_combat.add_enemy(lethal_creature, lethal_ai)
        lethal_combat.player.current_hp = 16
        lethal_ai.states["GALVANIC_BURST"].perform(lethal_combat)
        assert lethal_combat.is_over
        assert lethal_combat.player_won is False
        assert lethal_creature.get_power_amount(PowerId.STRENGTH) == 0

    def test_flail_and_mysterious_knights_use_original_move_ids(self):
        creature, ai = create_flail_knight(Rng(41))
        assert creature.max_hp == 101
        assert ai.current_move.state_id == "RAM_MOVE"
        assert {"WAR_CHANT", "FLAIL_MOVE", "RAM_MOVE"}.issubset(ai.states)

        combat = _make_combat(42)
        setup_mysterious_knight(combat, Rng(42))
        mysterious = combat.enemies[0]
        mysterious_ai = combat.enemy_ais[mysterious.combat_id]

        assert mysterious_ai.current_move.state_id == "RAM_MOVE"
        assert {"WAR_CHANT", "FLAIL_MOVE", "RAM_MOVE"}.issubset(mysterious_ai.states)
        assert mysterious.get_power_amount(PowerId.STRENGTH) == 6
        assert mysterious.get_power_amount(PowerId.PLATING) == 6

    def test_knights_elite_uses_all_three_knights_in_original_order(self):
        combat = _make_combat(44)
        setup_knights_elite(combat, Rng(44))

        assert [enemy.monster_id for enemy in combat.enemies] == [
            "FLAIL_KNIGHT",
            "SPECTRAL_KNIGHT",
            "MAGI_KNIGHT",
        ]
        assert combat.enemy_ais[combat.enemies[0].combat_id].current_move.state_id == "RAM_MOVE"
        assert combat.enemy_ais[combat.enemies[1].combat_id].current_move.state_id == "HEX"
        assert combat.enemy_ais[combat.enemies[2].combat_id].current_move.state_id == "FIRST_POWER_SHIELD_MOVE"

    def test_magi_knight_uses_fixed_power_shield_dampen_cycle(self):
        combat = _make_combat(24)
        creature, ai = create_magi_knight(Rng(24))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 82
        assert ai.current_move.state_id == "FIRST_POWER_SHIELD_MOVE"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 74
        assert creature.block == 5

        ai.on_move_performed()
        ai.roll_move(Rng(24))
        assert ai.current_move.state_id == "DAMPEN_MOVE"

        ai.current_move.perform(combat)
        assert combat.player.get_power_amount(PowerId.DAMPEN) == 1

        expected_moves = ["RAM_MOVE", "PREP_MOVE", "MAGIC_BOMB", "RAM_MOVE"]
        actual_moves = []
        for _ in expected_moves:
            ai.on_move_performed()
            ai.roll_move(Rng(24))
            actual_moves.append(ai.current_move.state_id)

        assert actual_moves == expected_moves

    def test_spectral_knight_opens_with_hex_then_soul_slash(self):
        combat = _make_combat(25)
        creature, ai = create_spectral_knight(Rng(25))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 93
        assert ai.current_move.state_id == "HEX"

        ai.current_move.perform(combat)
        assert combat.player.get_power_amount(PowerId.HEX) == 2

        ai.on_move_performed()
        ai.roll_move(Rng(25))
        assert ai.current_move.state_id == "SOUL_SLASH"

        before_hp = combat.player.current_hp
        ai.current_move.perform(combat)
        assert combat.player.current_hp == before_hp - 15

    def test_mecha_knight_uses_charge_flamethrower_windup_cleave_cycle(self):
        combat = _make_combat(26)
        combat.hand = []
        creature, ai = create_mecha_knight(Rng(26))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 300
        assert creature.get_power_amount(PowerId.ARTIFACT) == 3
        assert ai.current_move.state_id == "CHARGE_MOVE"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 55

        ai.on_move_performed()
        ai.roll_move(Rng(26))
        assert ai.current_move.state_id == "FLAMETHROWER_MOVE"

        rocket_punch = create_card(CardId.ROCKET_PUNCH)
        combat.hand = [rocket_punch]
        ai.current_move.perform(combat)
        assert [card.card_id for card in combat.hand] == [CardId.ROCKET_PUNCH] + [CardId.BURN] * 4
        assert rocket_punch.cost == 0

        ai.on_move_performed()
        ai.roll_move(Rng(26))
        assert ai.current_move.state_id == "WINDUP_MOVE"

        ai.current_move.perform(combat)
        assert creature.block == 15
        assert creature.get_power_amount(PowerId.STRENGTH) == 5

        ai.on_move_performed()
        ai.roll_move(Rng(26))
        assert ai.current_move.state_id == "HEAVY_CLEAVE_MOVE"

        before_hp = combat.player.current_hp
        ai.current_move.perform(combat)
        assert combat.player.current_hp == before_hp - 40

        ai.on_move_performed()
        ai.roll_move(Rng(26))
        assert ai.current_move.state_id == "FLAMETHROWER_MOVE"

    def test_act3_monster_block_moves_trigger_after_block_gained_hooks(self):
        cases = [
            (create_axebot(Rng(1), start_with_boot_up=True), "BOOT_UP_MOVE", 10),
            (create_the_forgotten(Rng(2)), "MIASMA", 8),
            (create_magi_knight(Rng(3)), "FIRST_POWER_SHIELD_MOVE", 5),
            (create_magi_knight(Rng(4)), "PREP_MOVE", 5),
            (create_mecha_knight(Rng(5)), "WINDUP_MOVE", 15),
        ]

        for (creature, ai), state_id, expected_block in cases:
            combat = _make_combat(122)
            combat.add_enemy(creature, ai)
            creature.block = 0
            counter = _BlockHookCounterPower()
            creature.powers[PowerId.JUGGERNAUT] = counter

            ai.states[state_id].perform(combat)

            assert creature.block == expected_block
            assert counter.calls == [expected_block]

        combat = _make_combat(123)
        fabricator, fabricator_ai = create_fabricator(Rng(6))
        guardbot, guardbot_ai = create_guardbot(Rng(7))
        combat.add_enemy(fabricator, fabricator_ai)
        combat.add_enemy(guardbot, guardbot_ai)
        fabricator.block = 0
        counter = _BlockHookCounterPower()
        fabricator.powers[PowerId.JUGGERNAUT] = counter

        guardbot_ai.states["GUARD_MOVE"].perform(combat)

        assert fabricator.block == 15
        assert counter.calls == [15]

    def test_owl_magistrate_uses_original_flight_and_verdict_cycle(self):
        combat = _make_combat(27)
        creature, ai = create_owl_magistrate(Rng(27))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 234
        assert ai.current_move.state_id == "MAGISTRATE_SCRUTINY"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 64

        ai.on_move_performed()
        ai.roll_move(Rng(27))
        assert ai.current_move.state_id == "PECK_ASSAULT"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 40

        ai.on_move_performed()
        ai.roll_move(Rng(27))
        assert ai.current_move.state_id == "JUDICIAL_FLIGHT"

        ai.current_move.perform(combat)
        assert creature.get_power_amount(PowerId.SOAR) == 1

        ai.on_move_performed()
        ai.roll_move(Rng(27))
        assert ai.current_move.state_id == "VERDICT"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 7
        assert combat.player.get_power_amount(PowerId.VULNERABLE) == 4
        assert creature.get_power_amount(PowerId.SOAR) == 0

        ai.on_move_performed()
        ai.roll_move(Rng(27))
        assert ai.current_move.state_id == "MAGISTRATE_SCRUTINY"

    def test_slimed_berserker_uses_original_ichor_hug_smother_cycle(self):
        combat = _make_combat(28)
        creature, ai = create_slimed_berserker(Rng(28))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 266
        assert ai.current_move.state_id == "VOMIT_ICHOR_MOVE"

        rocket_punch = create_card(CardId.ROCKET_PUNCH)
        combat.hand = [rocket_punch]
        ai.current_move.perform(combat)
        assert [card.card_id for card in combat.discard_pile] == [CardId.SLIMED] * 10
        assert rocket_punch.cost == 0

        ai.on_move_performed()
        ai.roll_move(Rng(28))
        assert ai.current_move.state_id == "FURIOUS_PUMMELING_MOVE"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 64

        ai.on_move_performed()
        ai.roll_move(Rng(28))
        assert ai.current_move.state_id == "LEECHING_HUG_MOVE"

        ai.current_move.perform(combat)
        assert combat.player.get_power_amount(PowerId.WEAK) == 3
        assert creature.get_power_amount(PowerId.STRENGTH) == 3

        ai.on_move_performed()
        ai.roll_move(Rng(28))
        assert ai.current_move.state_id == "SMOTHER_MOVE"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 31

        ai.on_move_performed()
        ai.roll_move(Rng(28))
        assert ai.current_move.state_id == "VOMIT_ICHOR_MOVE"

    def test_the_lost_steals_strength_and_restores_it_on_death(self):
        combat = _make_combat(29)
        creature, ai = create_the_lost(Rng(29))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 93
        assert creature.get_power_amount(PowerId.POSSESS_STRENGTH) == 1
        assert ai.current_move.state_id == "DEBILITATING_SMOG"

        ai.current_move.perform(combat)
        assert combat.player.get_power_amount(PowerId.STRENGTH) == -2
        assert creature.get_power_amount(PowerId.STRENGTH) == 2

        ai.on_move_performed()
        ai.roll_move(Rng(29))
        assert ai.current_move.state_id == "EYE_LASERS"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 68

        combat.kill_creature(creature)
        assert combat.player.get_power_amount(PowerId.STRENGTH) == 0

    def test_the_forgotten_steals_dexterity_and_restores_it_on_death(self):
        combat = _make_combat(30)
        creature, ai = create_the_forgotten(Rng(30))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 106
        assert creature.get_power_amount(PowerId.POSSESS_SPEED) == 1
        assert ai.current_move.state_id == "MIASMA"

        ai.current_move.perform(combat)
        assert combat.player.get_power_amount(PowerId.DEXTERITY) == -2
        assert creature.block == 8
        assert creature.get_power_amount(PowerId.DEXTERITY) == 2

        ai.on_move_performed()
        ai.roll_move(Rng(30))
        assert ai.current_move.state_id == "DREAD"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 65

        combat.kill_creature(creature)
        assert combat.player.get_power_amount(PowerId.DEXTERITY) == 0

    def test_scroll_of_biting_supports_original_starter_moves_and_cycle(self):
        combat = _make_combat(31)
        creature, ai = create_scroll_of_biting(Rng(31), starter_move_idx=0)
        combat.add_enemy(creature, ai)

        assert 31 <= creature.max_hp <= 38
        assert creature.get_power_amount(PowerId.PAPER_CUTS) == 2
        assert ai.current_move.state_id == "CHOMP"
        assert create_scroll_of_biting(Rng(32), starter_move_idx=1)[1].current_move.state_id == "CHEW"
        assert create_scroll_of_biting(Rng(33), starter_move_idx=2)[1].current_move.state_id == "MORE_TEETH"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 66

        ai.on_move_performed()
        ai.roll_move(Rng(31))
        assert ai.current_move.state_id == "MORE_TEETH"

        ai.current_move.perform(combat)
        assert creature.get_power_amount(PowerId.STRENGTH) == 2

        ai.on_move_performed()
        ai.roll_move(Rng(31))
        assert ai.current_move.state_id == "CHEW"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 52

    def test_turret_operator_unloads_twice_then_reloads(self):
        combat = _make_combat(34)
        creature, ai = create_turret_operator(Rng(34))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 41
        assert ai.current_move.state_id == "UNLOAD_MOVE_1"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 65

        ai.on_move_performed()
        ai.roll_move(Rng(34))
        assert ai.current_move.state_id == "UNLOAD_MOVE_2"

        ai.current_move.perform(combat)
        assert combat.player.current_hp == 50

        ai.on_move_performed()
        ai.roll_move(Rng(34))
        assert ai.current_move.state_id == "RELOAD_MOVE"

        ai.current_move.perform(combat)
        assert creature.get_power_amount(PowerId.STRENGTH) == 1

        ai.on_move_performed()
        ai.roll_move(Rng(34))
        assert ai.current_move.state_id == "UNLOAD_MOVE_1"

    def test_turret_operator_weak_includes_living_shield_and_shield_switches_when_alone(self):
        combat = _make_combat(43)
        setup_turret_operator_weak(combat, Rng(43))

        assert [enemy.monster_id for enemy in combat.enemies] == ["LIVING_SHIELD", "TURRET_OPERATOR"]
        shield, turret = combat.enemies
        shield_ai = combat.enemy_ais[shield.combat_id]

        assert shield.get_power_amount(PowerId.RAMPART) == 25
        assert shield_ai.current_move.state_id == "SHIELD_SLAM_MOVE"

        shield_ai.on_move_performed()
        shield_ai.roll_move(Rng(43))
        assert shield_ai.current_move.state_id == "SHIELD_SLAM_MOVE"

        turret.current_hp = 0
        shield_ai.on_move_performed()
        shield_ai.roll_move(Rng(43))
        assert shield_ai.current_move.state_id == "SMASH_MOVE"

        shield_ai.current_move.perform(combat)
        assert combat.player.current_hp == 64
        assert shield.get_power_amount(PowerId.STRENGTH) == 3

        lethal_combat = _make_combat(143)
        lethal_shield, lethal_shield_ai = create_living_shield(Rng(143), get_ally_count=lambda: 0)
        lethal_combat.add_enemy(lethal_shield, lethal_shield_ai)
        lethal_combat.player.current_hp = 16
        lethal_shield_ai.states["SMASH_MOVE"].perform(lethal_combat)
        assert lethal_combat.is_over
        assert lethal_combat.player_won is False
        assert lethal_shield.get_power_amount(PowerId.STRENGTH) == 0

    def test_doormaker_boss_starts_with_door_and_spawns_doormaker_after_door_death(self):
        combat = _make_combat(45)
        setup_doormaker_boss(combat, Rng(45))

        assert [enemy.monster_id for enemy in combat.enemies] == ["DOOR"]

        door = combat.enemies[0]
        assert combat.kill_creature(door)

        assert [enemy.monster_id for enemy in combat.enemies] == ["DOOR", "DOORMAKER"]
        assert combat.enemy_ais[door.combat_id].current_move.state_id == "DEAD_MOVE"

        lethal_door_combat = _make_combat(145)
        lethal_door, lethal_door_ai = create_door(Rng(145))
        lethal_door_combat.add_enemy(lethal_door, lethal_door_ai)
        lethal_door_combat.player.current_hp = 20
        lethal_door_ai.states["ENFORCE_MOVE"].perform(lethal_door_combat)
        assert lethal_door_combat.is_over
        assert lethal_door_combat.player_won is False
        assert lethal_door.get_power_amount(PowerId.STRENGTH) == 0

        lethal_doormaker_combat = _make_combat(146)
        lethal_door_2, lethal_door_ai_2 = create_door(Rng(146))
        lethal_doormaker, lethal_doormaker_ai = create_doormaker(Rng(146))
        lethal_doormaker_combat.add_enemy(lethal_door_2, lethal_door_ai_2)
        lethal_doormaker_combat.add_enemy(lethal_doormaker, lethal_doormaker_ai)
        lethal_door_2.current_hp = 0
        lethal_doormaker_combat.player.current_hp = 40
        lethal_doormaker_ai.states["GET_BACK_IN_MOVE"].perform(lethal_doormaker_combat)
        assert lethal_doormaker_combat.is_over
        assert lethal_doormaker_combat.player_won is False
        assert lethal_doormaker.get_power_amount(PowerId.STRENGTH) == 0
        assert lethal_door_2.current_hp == 0
        assert lethal_doormaker.is_alive

    def test_axebot_stock_spawns_replacements_with_decremented_stock(self):
        combat = _make_combat(35)
        creature, ai = create_axebot(Rng(35))
        combat.add_enemy(creature, ai)

        assert creature.get_power_amount(PowerId.STOCK) == 2

        combat.kill_creature(creature)
        alive_axebots = [enemy for enemy in combat.enemies if enemy.monster_id == "AXEBOT" and enemy.is_alive]
        assert len(alive_axebots) == 1

        first_replacement = alive_axebots[0]
        first_ai = combat.enemy_ais[first_replacement.combat_id]
        assert first_replacement.get_power_amount(PowerId.STOCK) == 1
        assert first_ai.current_move.state_id == "BOOT_UP_MOVE"

        combat.kill_creature(first_replacement)
        alive_axebots = [enemy for enemy in combat.enemies if enemy.monster_id == "AXEBOT" and enemy.is_alive]
        assert len(alive_axebots) == 1

        second_replacement = alive_axebots[0]
        second_ai = combat.enemy_ais[second_replacement.combat_id]
        assert second_replacement.get_power_amount(PowerId.STOCK) == 0
        assert second_ai.current_move.state_id == "BOOT_UP_MOVE"

        combat.kill_creature(second_replacement)
        assert not [enemy for enemy in combat.enemies if enemy.monster_id == "AXEBOT" and enemy.is_alive]

    def test_initial_random_branch_uses_monster_rng(self):
        moves = [create_axebot(Rng(seed))[1].current_move.state_id for seed in range(10)]

        assert set(moves) == {"ONE_TWO_MOVE", "SHARPEN_MOVE", "HAMMER_UPPERCUT_MOVE"}

    def test_fabricator_bots_match_original_moves_and_powers(self):
        combat = _make_combat(36)
        fabricator, fabricator_ai = create_fabricator(Rng(36))
        combat.add_enemy(fabricator, fabricator_ai)

        zapbot, zapbot_ai = create_zapbot(Rng(36))
        combat.add_enemy(zapbot, zapbot_ai)
        assert zapbot.get_power_amount(PowerId.HIGH_VOLTAGE) == 2
        assert zapbot.get_power_amount(PowerId.MINION) == 0
        assert zapbot_ai.current_move.state_id == "ZAP"

        stabbot, stabbot_ai = create_stabbot(Rng(36))
        combat.add_enemy(stabbot, stabbot_ai)
        assert stabbot.get_power_amount(PowerId.MINION) == 0
        assert stabbot_ai.current_move.state_id == "STAB_MOVE"
        stabbot_ai.current_move.perform(combat)
        assert combat.player.current_hp == 69
        assert combat.player.get_power_amount(PowerId.FRAIL) == 1

        guardbot, guardbot_ai = create_guardbot(Rng(36))
        combat.add_enemy(guardbot, guardbot_ai)
        assert guardbot.get_power_amount(PowerId.MINION) == 0
        assert guardbot_ai.current_move.state_id == "GUARD_MOVE"
        guardbot_ai.current_move.perform(combat)
        assert fabricator.block == 15

        noisebot, noisebot_ai = create_noisebot(Rng(36))
        combat.add_enemy(noisebot, noisebot_ai)
        assert noisebot.get_power_amount(PowerId.MINION) == 0
        assert noisebot_ai.current_move.state_id == "NOISE_MOVE"
        rocket_punch = create_card(CardId.ROCKET_PUNCH)
        combat.hand = [rocket_punch]
        noisebot_ai.current_move.perform(combat)
        assert [card.card_id for card in combat.discard_pile] == [CardId.DAZED]
        assert [card.card_id for card in combat.draw_pile] == [CardId.DAZED]
        assert rocket_punch.cost == 0

        fabricator_ai.states["FABRICATE_MOVE"].perform(combat)
        assert len(combat.enemies) == 7
        assert combat.enemies[-2].get_power_amount(PowerId.MINION) == 1
        assert combat.enemies[-1].get_power_amount(PowerId.MINION) == 1

        lethal_combat = _make_combat(101)
        lethal_fabricator, lethal_fabricator_ai = create_fabricator(Rng(101))
        lethal_combat.add_enemy(lethal_fabricator, lethal_fabricator_ai)
        lethal_combat.player.current_hp = 18
        lethal_fabricator_ai.states["FABRICATING_STRIKE_MOVE"].perform(lethal_combat)
        assert lethal_combat.is_over
        assert lethal_combat.player_won is False
        assert len(lethal_combat.enemies) == 2
        assert lethal_combat.enemies[-1].get_power_amount(PowerId.HIGH_VOLTAGE) == 0
        assert lethal_combat.enemies[-1].get_power_amount(PowerId.MINION) == 0

    def test_noisebot_adds_dazed_to_each_living_player_not_osty(self):
        rng_seed = 1236
        osty_hp = 5
        ally_player_id = 2
        ally_character_id = "Silent"
        ally_hp = 70
        combat = _make_combat(rng_seed)
        ally = combat.add_ally_player(
            PlayerState(
                player_id=ally_player_id,
                character_id=ally_character_id,
                max_hp=ally_hp,
                current_hp=ally_hp,
            )
        )
        ally_state = combat.combat_player_state_for(ally)
        primary_state = combat.combat_player_state_for(combat.primary_player)
        assert primary_state is not None
        assert ally_state is not None
        primary_state.draw.clear()
        primary_state.discard.clear()
        ally_state.draw.clear()
        ally_state.discard.clear()
        combat.summon_osty(combat.primary_player, osty_hp)
        noisebot, noisebot_ai = create_noisebot(Rng(rng_seed))
        combat.add_enemy(noisebot, noisebot_ai)

        noisebot_ai.current_move.perform(combat)

        assert [card.card_id for card in primary_state.draw] == [CardId.DAZED]
        assert [card.card_id for card in primary_state.discard] == [CardId.DAZED]
        assert [card.card_id for card in ally_state.draw] == [CardId.DAZED]
        assert [card.card_id for card in ally_state.discard] == [CardId.DAZED]

    def test_fabricator_disintegrates_when_four_teammates_are_alive(self):
        combat = _make_combat(37)
        fabricator, fabricator_ai = create_fabricator(Rng(37))
        combat.add_enemy(fabricator, fabricator_ai)

        for creator in (create_zapbot, create_stabbot, create_guardbot, create_noisebot):
            bot, bot_ai = creator(Rng(37))
            combat.add_enemy(bot, bot_ai)

        fabricator_ai._current_state_id = "fabricateBranch"  # noqa: SLF001
        fabricator_ai._performed_first_move = True  # noqa: SLF001
        fabricator_ai.roll_move(Rng(37))

        assert fabricator_ai.current_move.state_id == "DISINTEGRATE_MOVE"

    def test_soul_nexus_uses_original_attack_and_debuff_moves(self):
        combat = _make_combat(38)
        creature, ai = create_soul_nexus(Rng(38))
        combat.add_enemy(creature, ai)

        assert creature.max_hp == 234
        assert ai.current_move.state_id == "SOUL_BURN_MOVE"

        ai.states["SOUL_BURN_MOVE"].perform(combat)
        assert combat.player.current_hp == 51

        combat.player.current_hp = 80
        ai.states["MAELSTROM_MOVE"].perform(combat)
        assert combat.player.current_hp == 56

        combat.player.current_hp = 80
        ai.states["DRAIN_LIFE_MOVE"].perform(combat)
        assert combat.player.current_hp == 62
        assert combat.player.get_power_amount(PowerId.VULNERABLE) == 2
        assert combat.player.get_power_amount(PowerId.WEAK) == 2

    def test_queen_boss_uses_amalgam_and_original_opening_sequence(self):
        combat = _make_combat(39)
        setup_queen_boss(combat, Rng(39))

        assert [enemy.monster_id for enemy in combat.enemies] == ["TORCH_HEAD_AMALGAM", "QUEEN"]
        amalgam, queen = combat.enemies
        amalgam_ai = combat.enemy_ais[amalgam.combat_id]
        queen_ai = combat.enemy_ais[queen.combat_id]

        assert amalgam.max_hp == 199
        assert amalgam.get_power_amount(PowerId.MINION) == 1
        assert amalgam_ai.current_move.state_id == "TACKLE_1_MOVE"
        assert queen.max_hp == 400
        assert queen_ai.current_move.state_id == "PUPPET_STRINGS_MOVE"

        queen_ai.current_move.perform(combat)
        assert combat.player.get_power_amount(PowerId.CHAINS_OF_BINDING) == 3

        queen_ai.on_move_performed()
        queen_ai.roll_move(Rng(39))
        assert queen_ai.current_move.state_id == "YOUR_MINE_MOVE"

        queen_ai.current_move.perform(combat)
        assert combat.player.get_power_amount(PowerId.FRAIL) == 99
        assert combat.player.get_power_amount(PowerId.WEAK) == 99
        assert combat.player.get_power_amount(PowerId.VULNERABLE) == 99

        queen_ai.on_move_performed()
        queen_ai.roll_move(Rng(39))
        assert queen_ai.current_move.state_id == "BURN_BRIGHT_FOR_ME_MOVE"

        queen_ai.current_move.perform(combat)
        assert queen.block == 20
        assert amalgam.get_power_amount(PowerId.STRENGTH) == 1
        assert queen.get_power_amount(PowerId.STRENGTH) == 0

        counter = _BlockHookCounterPower()
        queen.powers[PowerId.JUGGERNAUT] = counter
        queen.block = 0
        queen_ai.states["BURN_BRIGHT_FOR_ME_MOVE"].perform(combat)
        assert queen.block == 20
        assert counter.calls == [20]

        combat.kill_creature(amalgam)
        queen_ai.on_move_performed()
        queen_ai.roll_move(Rng(39))
        assert queen_ai.current_move.state_id == "OFF_WITH_YOUR_HEAD_MOVE"

    def test_act4_weak_monsters_use_original_move_ids_and_stats(self):
        slug, slug_ai = create_corpse_slug(Rng(50), starter_idx=0)
        assert 25 <= slug.max_hp <= 27
        assert slug.get_power_amount(PowerId.RAVENOUS) == 4
        assert _run_ai(slug_ai, Rng(50), 4) == [
            "WHIP_SLAP_MOVE",
            "GLOMP_MOVE",
            "GOOP_MOVE",
            "WHIP_SLAP_MOVE",
        ]

        seapunk, seapunk_ai = create_seapunk(Rng(51))
        combat = _make_combat(51)
        combat.add_enemy(seapunk, seapunk_ai)
        assert 44 <= seapunk.max_hp <= 46
        assert _run_ai(seapunk_ai, Rng(51), 4) == [
            "SEA_KICK_MOVE",
            "SPINNING_KICK_MOVE",
            "BUBBLE_BURP_MOVE",
            "SEA_KICK_MOVE",
        ]

        seapunk_effect, seapunk_effect_ai = create_seapunk(Rng(52))
        seapunk_combat = _make_combat(52)
        seapunk_combat.add_enemy(seapunk_effect, seapunk_effect_ai)
        seapunk_effect_ai.states["SEA_KICK_MOVE"].perform(seapunk_combat)
        assert seapunk_combat.player.current_hp == 69
        seapunk_effect_ai.states["SPINNING_KICK_MOVE"].perform(seapunk_combat)
        assert seapunk_combat.player.current_hp == 61
        seapunk_effect_ai.states["BUBBLE_BURP_MOVE"].perform(seapunk_combat)
        assert seapunk_effect.block == 7
        assert seapunk_effect.get_power_amount(PowerId.STRENGTH) == 1
        counter = _BlockHookCounterPower()
        seapunk_effect.powers[PowerId.JUGGERNAUT] = counter
        seapunk_effect.block = 0
        seapunk_effect_ai.states["BUBBLE_BURP_MOVE"].perform(seapunk_combat)
        assert seapunk_effect.block == 7
        assert counter.calls == [7]

        sludge, sludge_ai = create_sludge_spinner(Rng(53))
        sludge_combat = _make_combat(53)
        sludge_combat.add_enemy(sludge, sludge_ai)
        assert 37 <= sludge.max_hp <= 39
        assert sludge_ai.current_move.state_id == "OIL_SPRAY_MOVE"
        assert {"RAND", "OIL_SPRAY_MOVE", "SLAM_MOVE", "RAGE_MOVE"}.issubset(
            sludge_ai.states
        )
        sludge_ai.states["OIL_SPRAY_MOVE"].perform(sludge_combat)
        assert sludge_combat.player.current_hp == 72
        assert sludge_combat.player.get_power_amount(PowerId.WEAK) == 1
        sludge_ai.states["RAGE_MOVE"].perform(sludge_combat)
        assert sludge_combat.player.current_hp == 66
        assert sludge.get_power_amount(PowerId.STRENGTH) == 3

        lethal_sludge, lethal_sludge_ai = create_sludge_spinner(Rng(153))
        lethal_sludge_combat = _make_combat(153)
        lethal_sludge_combat.add_enemy(lethal_sludge, lethal_sludge_ai)
        lethal_sludge_combat.player.current_hp = 6
        lethal_sludge_ai.states["RAGE_MOVE"].perform(lethal_sludge_combat)
        assert lethal_sludge_combat.is_over
        assert lethal_sludge_combat.player_won is False
        assert lethal_sludge.get_power_amount(PowerId.STRENGTH) == 0

        toad_front, toad_front_ai = create_toadpole(Rng(54), slot="front")
        toad_combat = _make_combat(54)
        toad_combat.add_enemy(toad_front, toad_front_ai)
        assert 21 <= toad_front.max_hp <= 25
        assert _run_ai(toad_front_ai, Rng(54), 4) == [
            "SPIKEN_MOVE",
            "SPIKE_SPIT_MOVE",
            "WHIRL_MOVE",
            "SPIKEN_MOVE",
        ]

        toad_effect, toad_effect_ai = create_toadpole(Rng(55), slot="front")
        toad_effect_combat = _make_combat(55)
        toad_effect_combat.add_enemy(toad_effect, toad_effect_ai)
        toad_effect_ai.current_move.perform(toad_effect_combat)
        assert toad_effect.get_power_amount(PowerId.THORNS) == 2
        toad_effect_ai.on_move_performed()
        toad_effect_ai.roll_move(Rng(55))
        assert toad_effect_ai.current_move.state_id == "SPIKE_SPIT_MOVE"
        toad_effect_ai.current_move.perform(toad_effect_combat)
        assert toad_effect.get_power_amount(PowerId.THORNS) == 0
        assert toad_effect_combat.player.current_hp == 71

        _, toad_back_ai = create_toadpole(Rng(56), slot="back")
        assert toad_back_ai.current_move.state_id == "WHIRL_MOVE"

    def test_act4_corpse_slug_and_toadpole_encounters_match_original_composition(self):
        move_order = ["WHIP_SLAP_MOVE", "GLOMP_MOVE", "GOOP_MOVE"]

        weak_combat = _make_combat(57)
        setup_corpse_slugs_weak(weak_combat, Rng(57))
        weak_moves = [
            weak_combat.enemy_ais[enemy.combat_id].current_move.state_id
            for enemy in weak_combat.enemies
        ]
        assert [enemy.monster_id for enemy in weak_combat.enemies] == [
            "CORPSE_SLUG",
            "CORPSE_SLUG",
        ]
        assert len(set(weak_moves)) == 2
        assert move_order.index(weak_moves[1]) == (
            move_order.index(weak_moves[0]) + 1
        ) % 3

        normal_combat = _make_combat(58)
        setup_corpse_slugs_normal(normal_combat, Rng(58))
        normal_moves = [
            normal_combat.enemy_ais[enemy.combat_id].current_move.state_id
            for enemy in normal_combat.enemies
        ]
        assert [enemy.monster_id for enemy in normal_combat.enemies] == [
            "CORPSE_SLUG",
            "CORPSE_SLUG",
            "CORPSE_SLUG",
        ]
        assert set(normal_moves) == set(move_order)

        seapunk_combat = _make_combat(58)
        setup_seapunk_weak(seapunk_combat, Rng(58))
        assert [enemy.monster_id for enemy in seapunk_combat.enemies] == ["SEAPUNK"]

        sludge_combat = _make_combat(58)
        setup_sludge_spinner_weak(sludge_combat, Rng(58))
        assert [enemy.monster_id for enemy in sludge_combat.enemies] == ["SLUDGE_SPINNER"]

        toad_weak_combat = _make_combat(59)
        setup_toadpoles_weak(toad_weak_combat, Rng(59))
        assert [enemy.monster_id for enemy in toad_weak_combat.enemies] == [
            "TOADPOLE",
            "TOADPOLE",
        ]
        assert [
            toad_weak_combat.enemy_ais[enemy.combat_id].current_move.state_id
            for enemy in toad_weak_combat.enemies
        ] == ["SPIKEN_MOVE", "WHIRL_MOVE"]

        toad_normal_combat = _make_combat(60)
        setup_toadpoles_normal(toad_normal_combat, Rng(60))
        assert [enemy.monster_id for enemy in toad_normal_combat.enemies] == [
            "CALCIFIED_CULTIST",
            "TOADPOLE",
        ]
        assert toad_normal_combat.enemy_ais[toad_normal_combat.enemies[1].combat_id].current_move.state_id == (
            "WHIRL_MOVE"
        )

    def test_act4_normal_cultist_fossil_and_gremlin_merc_match_original_moves(self):
        calcified, calcified_ai = create_calcified_cultist(Rng(61))
        calcified_combat = _make_combat(61)
        calcified_combat.add_enemy(calcified, calcified_ai)
        assert 38 <= calcified.max_hp <= 41
        assert _run_ai(calcified_ai, Rng(61), 3) == [
            "INCANTATION_MOVE",
            "DARK_STRIKE_MOVE",
            "DARK_STRIKE_MOVE",
        ]
        calcified_ai.states["INCANTATION_MOVE"].perform(calcified_combat)
        assert calcified.get_power_amount(PowerId.RITUAL) == 2

        damp, damp_ai = create_damp_cultist(Rng(62))
        damp_combat = _make_combat(62)
        damp_combat.add_enemy(damp, damp_ai)
        assert 51 <= damp.max_hp <= 53
        assert _run_ai(damp_ai, Rng(62), 3) == [
            "INCANTATION_MOVE",
            "DARK_STRIKE_MOVE",
            "DARK_STRIKE_MOVE",
        ]
        damp_ai.states["INCANTATION_MOVE"].perform(damp_combat)
        assert damp.get_power_amount(PowerId.RITUAL) == 5

        fossil, fossil_ai = create_fossil_stalker(Rng(63))
        fossil_combat = _make_combat(63)
        fossil_combat.add_enemy(fossil, fossil_ai)
        assert 51 <= fossil.max_hp <= 53
        assert fossil.get_power_amount(PowerId.SUCK) == 3
        assert fossil_ai.current_move.state_id == "LATCH_MOVE"
        assert {"RAND", "TACKLE_MOVE", "LATCH_MOVE", "LASH_MOVE"}.issubset(
            fossil_ai.states
        )
        fossil_ai.states["TACKLE_MOVE"].perform(fossil_combat)
        assert fossil_combat.player.current_hp == 71
        assert fossil_combat.player.get_power_amount(PowerId.FRAIL) == 1
        assert fossil.get_power_amount(PowerId.STRENGTH) == 3

        fossil_lash, fossil_lash_ai = create_fossil_stalker(Rng(64))
        fossil_lash_combat = _make_combat(64)
        fossil_lash_combat.add_enemy(fossil_lash, fossil_lash_ai)
        fossil_lash_ai.states["LASH_MOVE"].perform(fossil_lash_combat)
        assert fossil_lash_combat.player.current_hp == 74

        merc, merc_ai = create_gremlin_merc(Rng(65))
        merc_combat = _make_combat(65)
        merc_combat.add_enemy(merc, merc_ai)
        assert 47 <= merc.max_hp <= 49
        assert merc.get_power_amount(PowerId.SURPRISE) == 1
        assert merc.get_power_amount(PowerId.THIEVERY) == 20
        assert _run_ai(merc_ai, Rng(65), 4) == [
            "GIMME_MOVE",
            "DOUBLE_SMASH_MOVE",
            "HEHE_MOVE",
            "GIMME_MOVE",
        ]
        merc_ai.states["DOUBLE_SMASH_MOVE"].perform(merc_combat)
        assert merc_combat.player.current_hp == 68
        assert merc_combat.player.get_power_amount(PowerId.WEAK) == 2
        merc_ai.states["HEHE_MOVE"].perform(merc_combat)
        assert merc_combat.player.current_hp == 60
        assert merc.get_power_amount(PowerId.STRENGTH) == 2

        lethal_merc, lethal_merc_ai = create_gremlin_merc(Rng(165))
        lethal_merc_combat = _make_combat(165)
        lethal_merc_combat.add_enemy(lethal_merc, lethal_merc_ai)
        lethal_merc_combat.player.current_hp = 8
        lethal_merc_ai.states["HEHE_MOVE"].perform(lethal_merc_combat)
        assert lethal_merc_combat.is_over
        assert lethal_merc_combat.player_won is False
        assert lethal_merc.get_power_amount(PowerId.STRENGTH) == 0

        sneaky, sneaky_ai = create_sneaky_gremlin(Rng(66))
        sneaky_combat = _make_combat(66)
        sneaky_combat.add_enemy(sneaky, sneaky_ai)
        assert 10 <= sneaky.max_hp <= 14
        assert _run_ai(sneaky_ai, Rng(66), 3) == [
            "SPAWNED_MOVE",
            "TACKLE_MOVE",
            "TACKLE_MOVE",
        ]
        sneaky_ai.states["TACKLE_MOVE"].perform(sneaky_combat)
        assert sneaky_combat.player.current_hp == 71

        fat, fat_ai = create_fat_gremlin(Rng(67))
        assert 13 <= fat.max_hp <= 17
        assert _run_ai(fat_ai, Rng(67), 3) == [
            "SPAWNED_MOVE",
            "FLEE_MOVE",
            "FLEE_MOVE",
        ]

    def test_act4_normal_punch_construct_and_sewer_clam_match_original_moves(self):
        punch, punch_ai = create_punch_construct(Rng(68))
        punch_combat = _make_combat(68)
        punch_combat.add_enemy(punch, punch_ai)
        assert punch.max_hp == 55
        assert punch.get_power_amount(PowerId.ARTIFACT) == 1
        assert _run_ai(punch_ai, Rng(68), 4) == [
            "READY_MOVE",
            "STRONG_PUNCH_MOVE",
            "FAST_PUNCH_MOVE",
            "READY_MOVE",
        ]
        punch_ai.states["READY_MOVE"].perform(punch_combat)
        assert punch.block == 10
        counter = _BlockHookCounterPower()
        punch.powers[PowerId.JUGGERNAUT] = counter
        punch.block = 0
        punch_ai.states["READY_MOVE"].perform(punch_combat)
        assert punch.block == 10
        assert counter.calls == [10]
        punch_ai.states["STRONG_PUNCH_MOVE"].perform(punch_combat)
        assert punch_combat.player.current_hp == 66
        punch_ai.states["FAST_PUNCH_MOVE"].perform(punch_combat)
        assert punch_combat.player.current_hp == 56
        assert punch_combat.player.get_power_amount(PowerId.WEAK) == 1

        clam, clam_ai = create_sewer_clam(Rng(69))
        clam_combat = _make_combat(69)
        clam_combat.add_enemy(clam, clam_ai)
        assert clam.max_hp == 56
        assert clam.get_power_amount(PowerId.PLATING) == 8
        assert _run_ai(clam_ai, Rng(69), 4) == [
            "JET_MOVE",
            "PRESSURIZE_MOVE",
            "JET_MOVE",
            "PRESSURIZE_MOVE",
        ]
        clam_ai.states["JET_MOVE"].perform(clam_combat)
        assert clam_combat.player.current_hp == 70
        clam_ai.states["PRESSURIZE_MOVE"].perform(clam_combat)
        assert clam.get_power_amount(PowerId.STRENGTH) == 4

    def test_act4_normal_haunted_ship_living_fog_and_two_tailed_rat_match_original_moves(self):
        ship, ship_ai = create_haunted_ship(Rng(70))
        ship_combat = _make_combat(70)
        ship_combat.add_enemy(ship, ship_ai)
        assert ship.max_hp == 63
        assert ship_ai.current_move.state_id == "RAMMING_SPEED_MOVE"
        assert {"RAND", "RAMMING_SPEED_MOVE", "SWIPE_MOVE", "STOMP_MOVE", "HAUNT_MOVE"}.issubset(
            ship_ai.states
        )
        ship_ai.current_move.perform(ship_combat)
        assert ship_combat.player.current_hp == 70
        assert [card.card_id for card in ship_combat.discard_pile] == [CardId.WOUND, CardId.WOUND]

        lethal_ship, lethal_ship_ai = create_haunted_ship(Rng(170))
        lethal_ship_combat = _make_combat(170)
        lethal_ship_combat.add_enemy(lethal_ship, lethal_ship_ai)
        lethal_ship_combat.player.current_hp = 10
        lethal_ship_ai.states["RAMMING_SPEED_MOVE"].perform(lethal_ship_combat)
        assert lethal_ship_combat.is_over
        assert lethal_ship_combat.player_won is False
        assert lethal_ship_combat.discard_pile == []

        ship_combat.round_number = 2
        ship_ai.on_move_performed()
        ship_ai.roll_move(Rng(70))
        assert ship_ai.current_move.state_id == "HAUNT_MOVE"
        ship_ai.current_move.perform(ship_combat)
        assert ship_combat.player.get_power_amount(PowerId.WEAK) == 2
        assert ship_combat.player.get_power_amount(PowerId.FRAIL) == 2
        assert ship_combat.player.get_power_amount(PowerId.VULNERABLE) == 2

        ship_effect, ship_effect_ai = create_haunted_ship(Rng(71))
        ship_effect_combat = _make_combat(71)
        ship_effect_combat.add_enemy(ship_effect, ship_effect_ai)
        ship_effect_ai.states["SWIPE_MOVE"].perform(ship_effect_combat)
        assert ship_effect_combat.player.current_hp == 67
        ship_effect_ai.states["STOMP_MOVE"].perform(ship_effect_combat)
        assert ship_effect_combat.player.current_hp == 55

        fog, fog_ai = create_living_fog(Rng(72))
        fog_combat = _make_combat(72)
        fog_combat.add_enemy(fog, fog_ai)
        assert fog.max_hp == 80
        assert _run_ai(fog_ai, Rng(72), 4) == [
            "ADVANCED_GAS_MOVE",
            "BLOAT_MOVE",
            "SUPER_GAS_BLAST_MOVE",
            "BLOAT_MOVE",
        ]

        fog_effect, fog_effect_ai = create_living_fog(Rng(73))
        fog_effect_combat = _make_combat(73)
        fog_effect_combat.add_enemy(fog_effect, fog_effect_ai)
        fog_effect_ai.states["ADVANCED_GAS_MOVE"].perform(fog_effect_combat)
        assert fog_effect_combat.player.current_hp == 72
        assert fog_effect_combat.player.get_power_amount(PowerId.SMOGGY) == 1
        fog_effect_ai.states["BLOAT_MOVE"].perform(fog_effect_combat)
        assert [enemy.monster_id for enemy in fog_effect_combat.enemies] == [
            "LIVING_FOG",
            "GAS_BOMB",
        ]
        assert fog_effect_combat.player.current_hp == 67
        fog_effect_ai.states["BLOAT_MOVE"].perform(fog_effect_combat)
        assert [enemy.monster_id for enemy in fog_effect_combat.enemies] == [
            "LIVING_FOG",
            "GAS_BOMB",
            "GAS_BOMB",
            "GAS_BOMB",
        ]
        assert fog_effect_combat.player.current_hp == 62

        bomb, bomb_ai = create_gas_bomb(Rng(74))
        assert bomb.get_power_amount(PowerId.MINION) == 0
        bomb_combat = _make_combat(74)
        bomb_combat.add_enemy(bomb, bomb_ai)
        assert bomb.max_hp == 10
        assert bomb.get_power_amount(PowerId.MINION) == 1
        assert bomb_ai.current_move.state_id == "EXPLODE_MOVE"
        bomb_ai.current_move.perform(bomb_combat)
        assert bomb_combat.player.current_hp == 72
        assert bomb.is_dead

        rat, rat_ai = create_two_tailed_rat(Rng(75), starter_move_idx=0)
        rat_combat = _make_combat(75)
        rat_combat.add_enemy(rat, rat_ai)
        assert 17 <= rat.max_hp <= 21
        assert rat_ai.current_move.state_id == "SCRATCH_MOVE"
        assert {
            "RAND",
            "SCRATCH_MOVE",
            "DISEASE_BITE_MOVE",
            "SCREECH_MOVE",
            "CALL_FOR_BACKUP_MOVE",
        }.issubset(rat_ai.states)
        rat_ai.states["SCRATCH_MOVE"].perform(rat_combat)
        assert rat_combat.player.current_hp == 72
        rat_ai.states["DISEASE_BITE_MOVE"].perform(rat_combat)
        assert rat_combat.player.current_hp == 66
        rat_ai.states["SCREECH_MOVE"].perform(rat_combat)
        assert rat_combat.player.get_power_amount(PowerId.FRAIL) == 1

        rat_ai.states["CALL_FOR_BACKUP_MOVE"].perform(rat_combat)
        assert [enemy.monster_id for enemy in rat_combat.enemies] == [
            "TWO_TAILED_RAT",
            "TWO_TAILED_RAT",
        ]

        rats_combat = _make_combat(76)
        setup_two_tailed_rats_normal(rats_combat, Rng(76))
        assert [enemy.monster_id for enemy in rats_combat.enemies] == [
            "TWO_TAILED_RAT",
            "TWO_TAILED_RAT",
            "TWO_TAILED_RAT",
        ]
        assert {
            rats_combat.enemy_ais[enemy.combat_id].current_move.state_id
            for enemy in rats_combat.enemies
        } == {"SCRATCH_MOVE", "DISEASE_BITE_MOVE", "SCREECH_MOVE"}

    def test_act4_elites_match_original_moves_and_setup(self):
        assert create_phantasmal_gardener(Rng(77), slot="first")[1].current_move.state_id == "FLAIL_MOVE"
        assert create_phantasmal_gardener(Rng(77), slot="second")[1].current_move.state_id == "BITE_MOVE"
        assert create_phantasmal_gardener(Rng(77), slot="third")[1].current_move.state_id == "LASH_MOVE"
        assert create_phantasmal_gardener(Rng(77), slot="fourth")[1].current_move.state_id == "ENLARGE_MOVE"

        gardener, gardener_ai = create_phantasmal_gardener(Rng(77), slot="second")
        gardener_combat = _make_combat(77)
        gardener_combat.add_enemy(gardener, gardener_ai)
        assert 28 <= gardener.max_hp <= 32
        assert gardener.get_power_amount(PowerId.SKITTISH) == 6
        assert _run_ai(gardener_ai, Rng(77), 5) == [
            "BITE_MOVE",
            "LASH_MOVE",
            "FLAIL_MOVE",
            "ENLARGE_MOVE",
            "BITE_MOVE",
        ]
        gardener_ai.states["FLAIL_MOVE"].perform(gardener_combat)
        assert gardener_combat.player.current_hp == 77
        gardener_ai.states["ENLARGE_MOVE"].perform(gardener_combat)
        assert gardener.get_power_amount(PowerId.STRENGTH) == 2

        gardeners_combat = _make_combat(78)
        setup_phantasmal_gardeners_elite(gardeners_combat, Rng(78))
        assert [enemy.monster_id for enemy in gardeners_combat.enemies] == [
            "PHANTASMAL_GARDENER",
            "PHANTASMAL_GARDENER",
            "PHANTASMAL_GARDENER",
            "PHANTASMAL_GARDENER",
        ]
        assert [
            gardeners_combat.enemy_ais[enemy.combat_id].current_move.state_id
            for enemy in gardeners_combat.enemies
        ] == ["FLAIL_MOVE", "BITE_MOVE", "LASH_MOVE", "ENLARGE_MOVE"]

        colony, colony_ai = create_skulking_colony(Rng(79))
        colony_combat = _make_combat(79)
        colony_combat.add_enemy(colony, colony_ai)
        assert colony.max_hp == 79
        assert colony.get_power_amount(PowerId.HARDENED_SHELL) == 20
        assert _run_ai(colony_ai, Rng(79), 5) == [
            "SMASH_MOVE",
            "ZOOM_MOVE",
            "INERTIA_MOVE",
            "SUPER_CRAB_MOVE",
            "SMASH_MOVE",
        ]
        colony_ai.states["SMASH_MOVE"].perform(colony_combat)
        assert colony_combat.player.current_hp == 71
        assert [card.card_id for card in colony_combat.discard_pile] == [CardId.DAZED] * 4

        lethal_colony, lethal_colony_ai = create_skulking_colony(Rng(80))
        lethal_colony_combat = _make_combat(80)
        lethal_colony_combat.add_enemy(lethal_colony, lethal_colony_ai)
        lethal_colony_combat.player.current_hp = 9
        lethal_colony_ai.states["SMASH_MOVE"].perform(lethal_colony_combat)
        assert lethal_colony_combat.is_over
        assert lethal_colony_combat.player_won is False
        assert lethal_colony_combat.discard_pile == []

        colony_ai.states["INERTIA_MOVE"].perform(colony_combat)
        assert colony.block == 10
        assert colony.get_power_amount(PowerId.STRENGTH) == 3
        counter = _BlockHookCounterPower()
        colony.powers[PowerId.JUGGERNAUT] = counter
        colony.block = 0
        colony_ai.states["INERTIA_MOVE"].perform(colony_combat)
        assert colony.block == 10
        assert counter.calls == [10]

        colony_zoom, colony_zoom_ai = create_skulking_colony(Rng(80))
        colony_zoom_combat = _make_combat(80)
        colony_zoom_combat.add_enemy(colony_zoom, colony_zoom_ai)
        colony_zoom_ai.states["ZOOM_MOVE"].perform(colony_zoom_combat)
        assert colony_zoom_combat.player.current_hp == 64
        colony_zoom_ai.states["SUPER_CRAB_MOVE"].perform(colony_zoom_combat)
        assert colony_zoom_combat.player.current_hp == 52

        eel, eel_ai = create_terror_eel(Rng(81))
        eel_combat = _make_combat(81)
        eel_combat.add_enemy(eel, eel_ai)
        assert eel.max_hp == 140
        assert eel.get_power_amount(PowerId.SHRIEK) == 70
        assert _run_ai(eel_ai, Rng(81), 3) == ["CRASH_MOVE", "ThrashMove", "CRASH_MOVE"]
        eel_ai.states["ThrashMove"].perform(eel_combat)
        assert eel_combat.player.current_hp == 71
        assert eel.get_power_amount(PowerId.VIGOR) == 7

        lethal_eel, lethal_eel_ai = create_terror_eel(Rng(83))
        lethal_eel_combat = _make_combat(83)
        lethal_eel_combat.add_enemy(lethal_eel, lethal_eel_ai)
        lethal_eel_combat.player.current_hp = 6
        lethal_eel_ai.states["ThrashMove"].perform(lethal_eel_combat)
        assert lethal_eel_combat.is_over
        assert lethal_eel_combat.player_won is False
        assert lethal_eel.get_power_amount(PowerId.VIGOR) == 0

        eel_shriek, eel_shriek_ai = create_terror_eel(Rng(82))
        eel_shriek_combat = _make_combat(82)
        eel_shriek_combat.add_enemy(eel_shriek, eel_shriek_ai)
        apply_damage(eel_shriek, 80, ValueProp.MOVE, eel_shriek_combat, eel_shriek_combat.player)
        assert eel_shriek.get_power_amount(PowerId.SHRIEK) == 0
        assert eel_shriek_ai.current_move.state_id == "STUN_MOVE"
        eel_shriek_ai.current_move.perform(eel_shriek_combat)
        eel_shriek_ai.on_move_performed()
        eel_shriek_ai.roll_move(Rng(82))
        assert eel_shriek_ai.current_move.state_id == "TERROR_MOVE"
        eel_shriek_ai.current_move.perform(eel_shriek_combat)
        assert eel_shriek_combat.player.get_power_amount(PowerId.VULNERABLE) == 99

    def test_act4_bosses_match_original_moves_and_setup(self):
        giant, giant_ai = create_waterfall_giant(Rng(83))
        giant_combat = _make_combat(83)
        giant_combat.add_enemy(giant, giant_ai)
        assert giant.max_hp == 250
        assert _run_ai(giant_ai, Rng(83), 7) == [
            "PRESSURIZE_MOVE",
            "STOMP_MOVE",
            "RAM_MOVE",
            "SIPHON_MOVE",
            "PRESSURE_GUN_MOVE",
            "PRESSURE_UP_MOVE",
            "STOMP_MOVE",
        ]

        giant_effect, giant_effect_ai = create_waterfall_giant(Rng(84))
        giant_effect_combat = _make_combat(84)
        giant_effect_combat.add_enemy(giant_effect, giant_effect_ai)
        giant_effect_ai.states["PRESSURIZE_MOVE"].perform(giant_effect_combat)
        assert giant_effect.get_power_amount(PowerId.STEAM_ERUPTION) == 15
        giant_effect_ai.states["STOMP_MOVE"].perform(giant_effect_combat)
        assert giant_effect_combat.player.current_hp == 65
        assert giant_effect_combat.player.get_power_amount(PowerId.WEAK) == 1
        assert giant_effect.get_power_amount(PowerId.STEAM_ERUPTION) == 18

        lethal_giant, lethal_giant_ai = create_waterfall_giant(Rng(184))
        lethal_giant_combat = _make_combat(184)
        lethal_giant_combat.add_enemy(lethal_giant, lethal_giant_ai)
        lethal_giant.apply_power(PowerId.STEAM_ERUPTION, 15)
        lethal_giant_combat.player.current_hp = 15
        lethal_giant_ai.states["STOMP_MOVE"].perform(lethal_giant_combat)
        assert lethal_giant_combat.is_over
        assert lethal_giant_combat.player_won is False
        assert lethal_giant_combat.player.get_power_amount(PowerId.WEAK) == 0
        assert lethal_giant.get_power_amount(PowerId.STEAM_ERUPTION) == 15

        giant_effect.current_hp = 20
        giant_effect_ai.states["PRESSURE_GUN_MOVE"].perform(giant_effect_combat)
        assert giant_effect_combat.player.current_hp == 45
        giant_effect.heal(5)
        assert giant_effect.current_hp == 25
        assert giant_effect_combat.kill_creature(giant_effect)
        assert giant_effect_ai.current_move.state_id == "ABOUT_TO_BLOW_MOVE"
        giant_effect_ai.current_move.perform(giant_effect_combat)
        giant_effect_ai.on_move_performed()
        giant_effect_ai.roll_move(Rng(84))
        assert giant_effect.get_power_amount(PowerId.STEAM_ERUPTION) == 0
        assert giant_effect_ai.current_move.state_id == "EXPLODE_MOVE"

        soul, soul_ai = create_soul_fysh(Rng(85))
        soul_combat = _make_combat(85)
        soul_combat.add_enemy(soul, soul_ai)
        assert soul.max_hp == 211
        assert _run_ai(soul_ai, Rng(85), 6) == [
            "BECKON_MOVE",
            "DE_GAS_MOVE",
            "GAZE_MOVE",
            "FADE_MOVE",
            "SCREAM_MOVE",
            "BECKON_MOVE",
        ]

        soul_effect, soul_effect_ai = create_soul_fysh(Rng(86))
        soul_effect_combat = _make_combat(86)
        soul_effect_combat.draw_pile.clear()
        soul_effect_combat.discard_pile.clear()
        soul_effect_combat.add_enemy(soul_effect, soul_effect_ai)
        soul_effect_ai.states["BECKON_MOVE"].perform(soul_effect_combat)
        assert [card.card_id for card in soul_effect_combat.draw_pile] == [CardId.BECKON]
        assert [card.card_id for card in soul_effect_combat.discard_pile] == [CardId.BECKON]
        soul_effect_ai.states["DE_GAS_MOVE"].perform(soul_effect_combat)
        assert soul_effect_combat.player.current_hp == 64
        soul_effect_ai.states["GAZE_MOVE"].perform(soul_effect_combat)
        assert soul_effect_combat.player.current_hp == 57
        assert [card.card_id for card in soul_effect_combat.discard_pile] == [CardId.BECKON, CardId.BECKON]

        lethal_soul, lethal_soul_ai = create_soul_fysh(Rng(87))
        lethal_soul_combat = _make_combat(87)
        lethal_soul_combat.add_enemy(lethal_soul, lethal_soul_ai)
        lethal_soul_combat.discard_pile.clear()
        lethal_soul_combat.player.current_hp = 7
        lethal_soul_ai.states["GAZE_MOVE"].perform(lethal_soul_combat)
        assert lethal_soul_combat.is_over
        assert lethal_soul_combat.player_won is False
        assert lethal_soul_combat.discard_pile == []

        soul_effect_ai.states["FADE_MOVE"].perform(soul_effect_combat)
        assert soul_effect.get_power_amount(PowerId.INTANGIBLE) == 2
        soul_effect_ai.states["SCREAM_MOVE"].perform(soul_effect_combat)
        assert soul_effect_combat.player.current_hp == 46
        assert soul_effect_combat.player.get_power_amount(PowerId.VULNERABLE) == 3

        soul_multiplayer, soul_multiplayer_ai = create_soul_fysh(Rng(88))
        soul_multiplayer_combat = _make_combat(88)
        ally_player_id = 2
        ally_character_id = "Silent"
        ally_hp = 70
        ally = soul_multiplayer_combat.add_ally_player(
            PlayerState(
                player_id=ally_player_id,
                character_id=ally_character_id,
                max_hp=ally_hp,
                current_hp=ally_hp,
            )
        )
        primary_state = soul_multiplayer_combat.combat_player_state_for(soul_multiplayer_combat.primary_player)
        ally_state = soul_multiplayer_combat.combat_player_state_for(ally)
        assert primary_state is not None
        assert ally_state is not None
        primary_state.draw.clear()
        primary_state.discard.clear()
        ally_state.draw.clear()
        ally_state.discard.clear()
        soul_multiplayer_combat.summon_osty(soul_multiplayer_combat.primary_player, 5)
        soul_multiplayer_combat.add_enemy(soul_multiplayer, soul_multiplayer_ai)
        soul_multiplayer_ai.states["BECKON_MOVE"].perform(soul_multiplayer_combat)
        assert [card.card_id for card in primary_state.draw] == [CardId.BECKON]
        assert [card.card_id for card in primary_state.discard] == [CardId.BECKON]
        assert [card.card_id for card in ally_state.draw] == [CardId.BECKON]
        assert [card.card_id for card in ally_state.discard] == [CardId.BECKON]
        expected_gaze_damage = 7
        expected_scream_damage = 11
        expected_scream_vulnerable = 3
        assert soul_multiplayer_combat.osty is not None
        osty_hp_before_gaze = soul_multiplayer_combat.osty.current_hp
        primary_hp_before_gaze = soul_multiplayer_combat.primary_player.current_hp
        ally_hp_before_gaze = ally.current_hp
        soul_multiplayer_ai.states["GAZE_MOVE"].perform(soul_multiplayer_combat)
        assert [card.card_id for card in primary_state.discard] == [CardId.BECKON, CardId.BECKON]
        assert [card.card_id for card in ally_state.discard] == [CardId.BECKON, CardId.BECKON]
        expected_gaze_overflow = expected_gaze_damage - osty_hp_before_gaze
        assert soul_multiplayer_combat.osty.current_hp == 0
        assert soul_multiplayer_combat.primary_player.current_hp == primary_hp_before_gaze - expected_gaze_overflow
        assert ally.current_hp == ally_hp_before_gaze - expected_gaze_damage
        primary_hp_before_scream = soul_multiplayer_combat.primary_player.current_hp
        ally_hp_before_scream = ally.current_hp
        soul_multiplayer_ai.states["SCREAM_MOVE"].perform(soul_multiplayer_combat)
        assert soul_multiplayer_combat.primary_player.current_hp == primary_hp_before_scream - expected_scream_damage
        assert ally.current_hp == ally_hp_before_scream - expected_scream_damage
        assert soul_multiplayer_combat.primary_player.get_power_amount(PowerId.VULNERABLE) == expected_scream_vulnerable
        assert ally.get_power_amount(PowerId.VULNERABLE) == expected_scream_vulnerable

        matriarch, matriarch_ai = create_lagavulin_matriarch(Rng(87))
        matriarch_combat = _make_combat(87)
        matriarch_combat.add_enemy(matriarch, matriarch_ai)
        assert matriarch.max_hp == 222
        assert matriarch.get_power_amount(PowerId.PLATING) == 12
        assert matriarch.get_power_amount(PowerId.ASLEEP) == 3
        matriarch.powers.pop(PowerId.ASLEEP)
        assert _run_ai(matriarch_ai, Rng(87), 5) == [
            "SLEEP_MOVE",
            "SLASH_MOVE",
            "DISEMBOWEL_MOVE",
            "SLASH2_MOVE",
            "SOUL_SIPHON_MOVE",
        ]

        matriarch_effect, matriarch_effect_ai = create_lagavulin_matriarch(Rng(88))
        matriarch_effect_combat = _make_combat(88)
        matriarch_effect_combat.add_enemy(matriarch_effect, matriarch_effect_ai)
        matriarch_effect.powers.pop(PowerId.ASLEEP)
        matriarch_effect_ai.on_move_performed()
        matriarch_effect_ai.roll_move(Rng(88))
        matriarch_effect_ai.current_move.perform(matriarch_effect_combat)
        assert matriarch_effect_combat.player.current_hp == 61
        matriarch_effect_ai.on_move_performed()
        matriarch_effect_ai.roll_move(Rng(88))
        matriarch_effect_ai.current_move.perform(matriarch_effect_combat)
        assert matriarch_effect_combat.player.current_hp == 43
        matriarch_effect_ai.on_move_performed()
        matriarch_effect_ai.roll_move(Rng(88))
        matriarch_effect_ai.current_move.perform(matriarch_effect_combat)
        assert matriarch_effect_combat.player.current_hp == 31
        assert matriarch_effect.block == 12
        counter = _BlockHookCounterPower()
        matriarch_effect.powers[PowerId.JUGGERNAUT] = counter
        matriarch_effect.block = 0
        matriarch_effect_ai.states["SLASH2_MOVE"].perform(matriarch_effect_combat)
        assert matriarch_effect.block == 12
        assert counter.calls == [12]
        matriarch_effect_ai.on_move_performed()
        matriarch_effect_ai.roll_move(Rng(88))
        matriarch_effect_ai.current_move.perform(matriarch_effect_combat)
        assert matriarch_effect_combat.player.get_power_amount(PowerId.STRENGTH) == -2
        assert matriarch_effect_combat.player.get_power_amount(PowerId.DEXTERITY) == -2
        assert matriarch_effect.get_power_amount(PowerId.STRENGTH) == 2

        matriarch_damage_wake, matriarch_damage_wake_ai = create_lagavulin_matriarch(Rng(89))
        matriarch_damage_wake_combat = _make_combat(89)
        matriarch_damage_wake_combat.add_enemy(matriarch_damage_wake, matriarch_damage_wake_ai)
        apply_damage(matriarch_damage_wake, 1, ValueProp.MOVE, matriarch_damage_wake_combat, matriarch_damage_wake_combat.player)
        assert PowerId.ASLEEP not in matriarch_damage_wake.powers
        assert PowerId.PLATING not in matriarch_damage_wake.powers
        assert matriarch_damage_wake_ai.current_move.state_id == "STUNNED"
        matriarch_damage_wake_ai.current_move.perform(matriarch_damage_wake_combat)
        matriarch_damage_wake_ai.on_move_performed()
        matriarch_damage_wake_ai.roll_move(Rng(89))
        assert matriarch_damage_wake_ai.current_move.state_id == "SLASH_MOVE"

        matriarch_natural_wake, matriarch_natural_wake_ai = create_lagavulin_matriarch(Rng(90))
        matriarch_natural_wake_combat = _make_combat(90)
        matriarch_natural_wake_combat.add_enemy(matriarch_natural_wake, matriarch_natural_wake_ai)
        matriarch_natural_wake.powers[PowerId.ASLEEP].amount = 1
        matriarch_natural_wake.powers[PowerId.ASLEEP].after_turn_end(
            matriarch_natural_wake,
            CombatSide.ENEMY,
            matriarch_natural_wake_combat,
        )
        assert PowerId.ASLEEP not in matriarch_natural_wake.powers
        assert PowerId.PLATING not in matriarch_natural_wake.powers
        assert matriarch_natural_wake_ai.current_move.state_id == "SLASH_MOVE"

        for setup in (setup_waterfall_giant_boss, setup_soul_fysh_boss, setup_lagavulin_matriarch_boss):
            setup_combat = _make_combat(91)
            setup(setup_combat, Rng(91))
            assert len(setup_combat.enemies) == 1


# ========================================================================
# 2. RandomBranchState with CannotRepeat
# ========================================================================

class TestRandomBranchCannotRepeat:
    def test_two_moves_must_alternate(self):
        """With 2 moves both CANNOT_REPEAT, verify no consecutive repeats."""
        rng = Rng(0)
        rand = RandomBranchState("RAND")
        rand.add_branch("A", MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch("B", MoveRepeatType.CANNOT_REPEAT)

        states = {
            "RAND": rand,
            "A": _make_move("A", "RAND"),
            "B": _make_move("B", "RAND"),
        }
        ai = MonsterAI(states, "RAND")
        moves = _run_ai(ai, rng, 20)

        for i in range(1, len(moves)):
            assert moves[i] != moves[i - 1], (
                f"Consecutive repeat at index {i}: {moves[i-1:i+1]}"
            )

    def test_three_moves_cannot_repeat_no_consecutive(self):
        """With 3 moves all CANNOT_REPEAT, none should repeat consecutively."""
        rng = Rng(99)
        rand = RandomBranchState("RAND")
        rand.add_branch("A", MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch("B", MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch("C", MoveRepeatType.CANNOT_REPEAT)

        states = {
            "RAND": rand,
            "A": _make_move("A", "RAND"),
            "B": _make_move("B", "RAND"),
            "C": _make_move("C", "RAND"),
        }
        ai = MonsterAI(states, "RAND")
        moves = _run_ai(ai, rng, 30)

        for i in range(1, len(moves)):
            assert moves[i] != moves[i - 1]

    def test_uses_multiple_seeds(self):
        """CANNOT_REPEAT should work across different RNG seeds."""
        rand = RandomBranchState("RAND")
        rand.add_branch("X", MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch("Y", MoveRepeatType.CANNOT_REPEAT)

        for seed in range(10):
            rng = Rng(seed)
            states = {
                "RAND": RandomBranchState("RAND"),
                "X": _make_move("X", "RAND"),
                "Y": _make_move("Y", "RAND"),
            }
            # Re-add branches since we cloned the state
            states["RAND"] = RandomBranchState("RAND")
            states["RAND"].add_branch("X", MoveRepeatType.CANNOT_REPEAT)
            states["RAND"].add_branch("Y", MoveRepeatType.CANNOT_REPEAT)

            ai = MonsterAI(states, "RAND")
            moves = _run_ai(ai, rng, 10)
            for i in range(1, len(moves)):
                assert moves[i] != moves[i - 1], f"seed={seed}"


# ========================================================================
# 3. UseOnlyOnce
# ========================================================================

class TestUseOnlyOnce:
    def test_appears_at_most_once(self):
        """USE_ONLY_ONCE move should appear at most 1 time."""
        rng = Rng(12345)
        rand = RandomBranchState("RAND")
        rand.add_branch("ONCE", MoveRepeatType.USE_ONLY_ONCE)
        rand.add_branch("ALWAYS", MoveRepeatType.CAN_REPEAT_FOREVER)

        states = {
            "RAND": rand,
            "ONCE": _make_move("ONCE", "RAND"),
            "ALWAYS": _make_move("ALWAYS", "RAND"),
        }
        ai = MonsterAI(states, "RAND")
        moves = _run_ai(ai, rng, 30)

        assert moves.count("ONCE") <= 1

    def test_use_only_once_across_seeds(self):
        """Verify USE_ONLY_ONCE across multiple seeds."""
        for seed in range(20):
            rng = Rng(seed)
            rand = RandomBranchState("RAND")
            rand.add_branch("SPECIAL", MoveRepeatType.USE_ONLY_ONCE)
            rand.add_branch("NORMAL", MoveRepeatType.CAN_REPEAT_FOREVER)

            states = {
                "RAND": rand,
                "SPECIAL": _make_move("SPECIAL", "RAND"),
                "NORMAL": _make_move("NORMAL", "RAND"),
            }
            ai = MonsterAI(states, "RAND")
            moves = _run_ai(ai, rng, 20)
            assert moves.count("SPECIAL") <= 1, f"seed={seed}, moves={moves}"


# ========================================================================
# 4. CAN_REPEAT_X_TIMES
# ========================================================================

class TestCanRepeatXTimes:
    def test_max_consecutive(self):
        """CAN_REPEAT_X_TIMES with max_times=2 allows at most 2 consecutive."""
        rng = Rng(0)
        rand = RandomBranchState("RAND")
        rand.add_branch("A", MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2)
        rand.add_branch("B", MoveRepeatType.CAN_REPEAT_FOREVER)

        states = {
            "RAND": rand,
            "A": _make_move("A", "RAND"),
            "B": _make_move("B", "RAND"),
        }
        ai = MonsterAI(states, "RAND")
        moves = _run_ai(ai, rng, 40)

        # Check: never more than 2 consecutive A's
        consecutive_a = 0
        max_consecutive_a = 0
        for m in moves:
            if m == "A":
                consecutive_a += 1
                max_consecutive_a = max(max_consecutive_a, consecutive_a)
            else:
                consecutive_a = 0
        assert max_consecutive_a <= 2, f"Got {max_consecutive_a} consecutive A's"


# ========================================================================
# 5. ConditionalBranchState
# ========================================================================

class TestConditionalBranch:
    def test_first_matching_condition_wins(self):
        """ConditionalBranch picks the first true condition."""
        rng = Rng(0)
        cond = ConditionalBranchState("COND")
        cond.add_branch(lambda: False, "A")
        cond.add_branch(lambda: True, "B")
        cond.add_branch(lambda: True, "C")  # Also true but should not be picked

        states = {
            "COND": cond,
            "A": _make_move("A", "A"),
            "B": _make_move("B", "B"),
            "C": _make_move("C", "C"),
        }
        ai = MonsterAI(states, "COND")
        assert ai.current_move.state_id == "B"

    def test_condition_with_mutable_state(self):
        """ConditionalBranch can use mutable external state."""
        rng = Rng(0)
        flag = [False]

        cond = ConditionalBranchState("COND")
        cond.add_branch(lambda: flag[0], "WHEN_TRUE")
        cond.add_branch(lambda: True, "FALLBACK")

        states = {
            "COND": cond,
            "WHEN_TRUE": _make_move("WHEN_TRUE", "WHEN_TRUE"),
            "FALLBACK": _make_move("FALLBACK", "FALLBACK"),
        }

        ai = MonsterAI(states, "COND")
        assert ai.current_move.state_id == "FALLBACK"

    def test_no_condition_matches_raises(self):
        """ConditionalBranch with no matching condition raises ValueError."""
        rng = Rng(0)
        cond = ConditionalBranchState("COND")
        cond.add_branch(lambda: False, "A")
        cond.add_branch(lambda: False, "B")

        states = {
            "COND": cond,
            "A": _make_move("A", "A"),
            "B": _make_move("B", "B"),
        }

        with pytest.raises(ValueError, match="no condition matched"):
            MonsterAI(states, "COND")

    def test_nibbit_conditional_start(self, rng):
        """Nibbit uses ConditionalBranch for start state."""
        from sts2_env.monsters.act1_weak import create_nibbit

        _, ai_alone = create_nibbit(rng, is_alone=True)
        assert ai_alone.current_move.state_id == "BUTT_MOVE"

        _, ai_front = create_nibbit(rng, is_alone=False, is_front=True)
        assert ai_front.current_move.state_id == "SLICE_MOVE"

        _, ai_back = create_nibbit(rng, is_alone=False, is_front=False)
        assert ai_back.current_move.state_id == "HISS_MOVE"


# ========================================================================
# 6. state_log only tracks MoveStates (not branch states)
# ========================================================================

class TestStateLog:
    def test_log_only_move_states(self):
        """state_log should only contain MoveState entries, not branch states."""
        rng = Rng(0)
        rand = RandomBranchState("RAND")
        rand.add_branch("A", MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch("B", MoveRepeatType.CANNOT_REPEAT)

        states = {
            "RAND": rand,
            "A": _make_move("A", "RAND"),
            "B": _make_move("B", "RAND"),
        }
        ai = MonsterAI(states, "RAND")
        _run_ai(ai, rng, 6)

        assert "RAND" not in ai.state_log
        for entry in ai.state_log:
            assert entry in ("A", "B"), f"Unexpected log entry: {entry}"
        assert len(ai.state_log) == 6

    def test_fixed_rotation_log(self):
        """Fixed rotation should log each performed move."""
        rng = Rng(0)
        states = {
            "A": _make_move("A", "B"),
            "B": _make_move("B", "C"),
            "C": _make_move("C", "A"),
        }
        ai = MonsterAI(states, "A")
        _run_ai(ai, rng, 6)

        assert ai.state_log == ["A", "B", "C", "A", "B", "C"]

    def test_log_length_matches_moves(self):
        """Log length should match number of performed moves."""
        rng = Rng(42)
        rand = RandomBranchState("RAND")
        rand.add_branch("X", MoveRepeatType.CAN_REPEAT_FOREVER)
        rand.add_branch("Y", MoveRepeatType.CAN_REPEAT_FOREVER)

        states = {
            "RAND": rand,
            "X": _make_move("X", "RAND"),
            "Y": _make_move("Y", "RAND"),
        }
        ai = MonsterAI(states, "RAND")
        moves = _run_ai(ai, rng, 15)

        assert len(ai.state_log) == 15
        assert ai.state_log == moves


# ========================================================================
# 7. First move hold
# ========================================================================

class TestFirstMoveHold:
    def test_cannot_advance_before_perform(self):
        """Initial MoveState can't transition away until performed."""
        rng = Rng(42)
        states = {
            "A": _make_move("A", "B"),
            "B": _make_move("B", "A"),
        }
        ai = MonsterAI(states, "A")

        # Roll multiple times without performing -- should stay on A
        ai.roll_move(rng)
        assert ai.current_move.state_id == "A"
        ai.roll_move(rng)
        assert ai.current_move.state_id == "A"
        ai.roll_move(rng)
        assert ai.current_move.state_id == "A"

        # Now perform, then roll should advance
        ai.on_move_performed()
        ai.roll_move(rng)
        assert ai.current_move.state_id == "B"

    def test_must_perform_once_blocks_transition(self):
        """must_perform_once prevents transition until the move is performed."""
        rng = Rng(0)
        a_state = MoveState("A", _noop, [attack_intent(1)], follow_up_id="B",
                            must_perform_once=True)
        states = {
            "A": a_state,
            "B": _make_move("B", "A"),
        }
        ai = MonsterAI(states, "A")

        # First move hold: can't advance until on_move_performed
        ai.roll_move(rng)
        assert ai.current_move.state_id == "A"

        # on_move_performed clears both first-move hold AND marks performed
        ai.on_move_performed()
        assert a_state._performed_at_least_once is True

        # Now can transition to B
        ai.roll_move(rng)
        assert ai.current_move.state_id == "B"

        # Perform B, roll back to A
        ai.on_move_performed()
        ai.roll_move(rng)
        assert ai.current_move.state_id == "A"

        # A was exited (on_exit_state resets _performed_at_least_once),
        # so must_perform_once holds it again until on_move_performed
        assert a_state._performed_at_least_once is False
        result = ai.roll_move(rng)
        assert result.state_id == "A"  # Held because must_perform_once not yet done

        # After on_move_performed, A can transition again
        ai.on_move_performed()
        assert a_state._performed_at_least_once is True
        ai.roll_move(rng)
        assert ai.current_move.state_id == "B"


# ========================================================================
# 8. Cooldown
# ========================================================================

class TestCooldown:
    def test_cooldown_prevents_recent_use(self):
        """Cooldown=2 prevents a move from appearing within the last 2 log entries."""
        rng = Rng(0)
        rand = RandomBranchState("RAND")
        rand.add_branch("A", MoveRepeatType.CAN_REPEAT_FOREVER, cooldown=2)
        rand.add_branch("B", MoveRepeatType.CAN_REPEAT_FOREVER)

        states = {
            "RAND": rand,
            "A": _make_move("A", "RAND"),
            "B": _make_move("B", "RAND"),
        }
        ai = MonsterAI(states, "RAND")
        moves = _run_ai(ai, rng, 20)

        for i in range(len(moves)):
            if moves[i] == "A":
                # Next 2 entries should not be A
                window = moves[i + 1: i + 3]
                assert "A" not in window, (
                    f"A appeared within cooldown at index {i}: {moves[i:i+4]}"
                )
