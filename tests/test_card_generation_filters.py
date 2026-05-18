"""Tests for combat card generation filters."""

from sts2_env.cards.factory import eligible_character_cards, eligible_registered_cards
from sts2_env.cards.ironclad import make_feed
from sts2_env.core.enums import CardId, CardType


def test_character_combat_generation_excludes_basic_event_and_ineligible_cards():
    ironclad_attacks = set(
        eligible_character_cards("Ironclad", card_type=CardType.ATTACK, generation_context="combat")
    )

    assert CardId.STRIKE_IRONCLAD not in ironclad_attacks
    assert CardId.FEED not in ironclad_attacks
    assert CardId.METEOR_SHOWER not in ironclad_attacks
    assert make_feed().can_be_generated_in_combat is False


def test_colorless_combat_generation_excludes_non_generatable_cards():
    colorless_cards = set(
        eligible_registered_cards(module_name="sts2_env.cards.colorless", generation_context="combat")
    )

    assert CardId.ALCHEMIZE not in colorless_cards
    assert CardId.HAND_OF_GREED not in colorless_cards
    assert CardId.DISCOVERY in colorless_cards


def test_modifier_generation_excludes_modifier_blacklisted_cards():
    ironclad_modifier_cards = set(
        eligible_character_cards("Ironclad", generation_context="modifier")
    )
    colorless_modifier_cards = set(
        eligible_registered_cards(module_name="sts2_env.cards.colorless", generation_context="modifier")
    )

    assert CardId.BAD_LUCK not in colorless_modifier_cards
    assert CardId.CURSE_OF_THE_BELL not in colorless_modifier_cards
    assert CardId.ANGER in ironclad_modifier_cards


def test_curse_pool_matches_reference_pool_without_legacy_curses():
    all_curses = set(eligible_registered_cards(card_type=CardType.CURSE, generation_context=None))
    modifier_curses = set(eligible_registered_cards(card_type=CardType.CURSE, generation_context="modifier"))

    assert all_curses == {
        CardId.ASCENDERS_BANE,
        CardId.BAD_LUCK,
        CardId.CLUMSY,
        CardId.CURSE_OF_THE_BELL,
        CardId.DEBT,
        CardId.DECAY,
        CardId.DOUBT,
        CardId.ENTHRALLED,
        CardId.FOLLY,
        CardId.GREED,
        CardId.GUILTY,
        CardId.INJURY,
        CardId.NORMALITY,
        CardId.POOR_SLEEP,
        CardId.REGRET,
        CardId.SHAME,
        CardId.SPORE_MIND,
        CardId.WRITHE,
    }
    assert modifier_curses == {
        CardId.CLUMSY,
        CardId.DEBT,
        CardId.DECAY,
        CardId.DOUBT,
        CardId.GUILTY,
        CardId.INJURY,
        CardId.NORMALITY,
        CardId.REGRET,
        CardId.SHAME,
        CardId.WRITHE,
    }
