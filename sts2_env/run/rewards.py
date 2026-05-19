"""Card reward generation.

Implements CardFactory logic: rarity odds, pity counter, upgrade probability,
blacklist handling, and GetNextHighestRarity fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sts2_env.cards.base import CardInstance
from sts2_env.cards.factory import card_metadata, card_preview, create_card, eligible_character_cards, eligible_registered_cards
from sts2_env.core.enums import CardId, CardRarity, CardType
from sts2_env.core.rng import Rng

if TYPE_CHECKING:
    from sts2_env.run.run_state import RunState


@dataclass(frozen=True)
class CardRewardGenerationOptions:
    context: str = "regular"
    num_cards: int = 3
    character_ids: tuple[str, ...] = field(default_factory=tuple)
    forced_rarities: tuple[CardRarity, ...] = field(default_factory=tuple)
    include_colorless: bool = False
    use_default_character_pool: bool = True
    generation_context: str | None = "combat"
    roll_upgrade: bool = True
    card_creation_source: str = "encounter"
    allow_card_pool_modifications: bool = True
    has_custom_card_pool: bool = False
    custom_card_ids: tuple[CardId, ...] = field(default_factory=tuple)


def _get_next_highest_rarity(rarity: CardRarity) -> CardRarity:
    """If a rarity pool is exhausted, bump up."""
    if rarity == CardRarity.COMMON:
        return CardRarity.UNCOMMON
    if rarity == CardRarity.UNCOMMON:
        return CardRarity.RARE
    return CardRarity.RARE


def _matches_card_instance_filters(
    card_id: CardId,
    *,
    cost: int | None = None,
    costs_x: bool | None = None,
) -> bool:
    if cost is None and costs_x is None:
        return True
    card = card_preview(card_id)
    if cost is not None and card.cost != cost:
        return False
    if costs_x is not None and card.has_energy_cost_x != costs_x:
        return False
    return True


def generate_card_reward(
    run_state: RunState,
    context: str = "regular",
    num_cards: int = 3,
) -> list[CardRarity]:
    """Generate card rarities for a reward screen.

    Args:
        run_state: Current run state (contains pity counter).
        context: "regular", "elite", or "boss".
        num_cards: Number of cards to generate (default 3).

    Returns:
        List of CardRarity values for each offered card.
    """
    result: list[CardRarity] = []
    for _ in range(num_cards):
        rarity = run_state.card_rarity_odds.roll(
            run_state.rng.rewards, context=context
        )
        result.append(rarity)
    return result


def roll_for_upgrade(
    run_state: RunState,
    rarity: CardRarity,
    rng: Rng,
    base_chance: float = 0.0,
) -> bool:
    """Roll whether a reward card should be upgraded.

    Formula: odds = base_chance + (act_index * scaling) for non-rare cards.
    Scaling = 0.25 normally, 0.125 at A7+.

    Args:
        run_state: Current run state.
        rarity: The card's rarity.
        rng: RNG stream for the roll.
        base_chance: Base upgrade chance (0.0 for combat, -999999999 for shop).

    Returns:
        True if the card should be upgraded.
    """
    roll = rng.next_float()
    odds = base_chance

    if rarity != CardRarity.RARE:
        scaling = 0.125 if run_state.ascension_level >= 7 else 0.25
        odds += run_state.current_act_index * scaling

    return roll <= odds


def generate_combat_card_rewards(
    run_state: RunState,
    context: str = "regular",
    num_cards: int = 3,
) -> list[tuple[CardRarity, bool]]:
    """Generate card rewards with upgrade rolls.

    Returns list of (rarity, should_upgrade) tuples.
    """
    rarities = generate_card_reward(run_state, context, num_cards)
    result: list[tuple[CardRarity, bool]] = []
    for rarity in rarities:
        upgraded = roll_for_upgrade(
            run_state, rarity, run_state.rng.rewards, base_chance=0.0,
        )
        result.append((rarity, upgraded))
    return result


def _pick_reward_card(
    run_state: RunState,
    rarity: CardRarity,
    chosen_ids: set,
    *,
    character_ids: tuple[str, ...],
    include_colorless: bool = False,
    generation_context: str | None = "combat",
    roll_upgrade: bool = True,
    card_type: CardType | None = None,
    cost: int | None = None,
    costs_x: bool | None = None,
    custom_card_ids: tuple[CardId, ...] = (),
) -> CardInstance | None:
    current_rarity = rarity
    candidate_ids = []

    while True:
        seen_ids = set()
        candidate_ids = []
        if custom_card_ids:
            for card_id in custom_card_ids:
                try:
                    metadata = card_metadata(card_id)
                except KeyError:
                    continue
                if metadata.rarity is not current_rarity:
                    continue
                if card_type is not None and metadata.card_type is not card_type:
                    continue
                if not _matches_card_instance_filters(card_id, cost=cost, costs_x=costs_x):
                    continue
                if card_id in chosen_ids or card_id in seen_ids:
                    continue
                seen_ids.add(card_id)
                candidate_ids.append(card_id)
        else:
            for character_id in character_ids:
                for card_id in eligible_character_cards(
                    character_id,
                    card_type=card_type,
                    rarity=current_rarity,
                    generation_context=generation_context,
                ):
                    if not _matches_card_instance_filters(card_id, cost=cost, costs_x=costs_x):
                        continue
                    if card_id in chosen_ids or card_id in seen_ids:
                        continue
                    seen_ids.add(card_id)
                    candidate_ids.append(card_id)
            if include_colorless:
                for card_id in eligible_registered_cards(
                    module_name="sts2_env.cards.colorless",
                    card_type=card_type,
                    rarity=current_rarity,
                    generation_context=generation_context,
                ):
                    if not _matches_card_instance_filters(card_id, cost=cost, costs_x=costs_x):
                        continue
                    if card_id in chosen_ids or card_id in seen_ids:
                        continue
                    seen_ids.add(card_id)
                    candidate_ids.append(card_id)
        if candidate_ids or current_rarity == CardRarity.RARE:
            break
        current_rarity = _get_next_highest_rarity(current_rarity)

    if not candidate_ids:
        seen_ids = set()
        if custom_card_ids:
            for card_id in custom_card_ids:
                try:
                    metadata = card_metadata(card_id)
                except KeyError:
                    continue
                if metadata.rarity is not current_rarity:
                    continue
                if card_type is not None and metadata.card_type is not card_type:
                    continue
                if not _matches_card_instance_filters(card_id, cost=cost, costs_x=costs_x):
                    continue
                if card_id in seen_ids:
                    continue
                seen_ids.add(card_id)
                candidate_ids.append(card_id)
        else:
            for character_id in character_ids:
                for card_id in eligible_character_cards(
                    character_id,
                    card_type=card_type,
                    rarity=current_rarity,
                    generation_context=generation_context,
                ):
                    if not _matches_card_instance_filters(card_id, cost=cost, costs_x=costs_x):
                        continue
                    if card_id in seen_ids:
                        continue
                    seen_ids.add(card_id)
                    candidate_ids.append(card_id)
            if include_colorless:
                for card_id in eligible_registered_cards(
                    module_name="sts2_env.cards.colorless",
                    card_type=card_type,
                    rarity=current_rarity,
                    generation_context=generation_context,
                ):
                    if not _matches_card_instance_filters(card_id, cost=cost, costs_x=costs_x):
                        continue
                    if card_id in seen_ids:
                        continue
                    seen_ids.add(card_id)
                    candidate_ids.append(card_id)
    if not candidate_ids:
        return None

    chosen_id = run_state.rng.rewards.choice(candidate_ids)
    chosen_ids.add(chosen_id)
    upgraded = False
    if roll_upgrade:
        upgraded = roll_for_upgrade(
            run_state,
            current_rarity,
            run_state.rng.rewards,
            base_chance=0.0,
        )
    card = create_card(chosen_id, upgraded=upgraded)
    if cost is not None and card.cost != cost:
        return None
    if costs_x is not None and card.has_energy_cost_x != costs_x:
        return None
    return card


def generate_combat_reward_cards(
    run_state: RunState,
    context: str = "regular",
    num_cards: int = 3,
    *,
    character_ids: tuple[str, ...] | None = None,
    forced_rarities: tuple[CardRarity, ...] = (),
    include_colorless: bool = False,
    generation_context: str | None = "combat",
    roll_upgrade: bool = True,
    card_type: CardType | None = None,
    cost: int | None = None,
    costs_x: bool | None = None,
    custom_card_ids: tuple[CardId, ...] = (),
) -> list[CardInstance]:
    """Generate concrete card reward options for a post-combat reward screen."""
    if character_ids is None:
        character_ids = (run_state.player.character_id,)
    rarities = list(forced_rarities) if forced_rarities else generate_card_reward(run_state, context=context, num_cards=num_cards)
    chosen_ids: set = set()
    cards: list[CardInstance] = []
    for rarity in rarities:
        card = _pick_reward_card(
            run_state,
            rarity,
            chosen_ids,
            character_ids=character_ids,
            include_colorless=include_colorless,
            generation_context=generation_context,
            roll_upgrade=roll_upgrade,
            card_type=card_type,
            cost=cost,
            costs_x=costs_x,
            custom_card_ids=custom_card_ids,
        )
        if card is not None:
            cards.append(card)
    return cards


def generate_noncombat_reward_cards(
    run_state: RunState,
    *,
    num_cards: int,
    character_ids: tuple[str, ...] | None = None,
    forced_rarities: tuple[CardRarity, ...] = (),
    include_colorless: bool = False,
    card_type: CardType | None = None,
    cost: int | None = None,
    costs_x: bool | None = None,
) -> list[CardInstance]:
    if character_ids is None:
        character_ids = (run_state.player.character_id,)
    rarities = list(forced_rarities) if forced_rarities else [
        run_state.card_rarity_odds.roll_with_base_odds(run_state.rng.rewards, context="regular")
        for _ in range(num_cards)
    ]
    chosen_ids: set = set()
    cards: list[CardInstance] = []
    for rarity in rarities:
        card = _pick_reward_card(
            run_state,
            rarity,
            chosen_ids,
            character_ids=character_ids,
            include_colorless=include_colorless,
            generation_context=None,
            roll_upgrade=False,
            card_type=card_type,
            cost=cost,
            costs_x=costs_x,
        )
        if card is not None:
            cards.append(card)
    return cards


def generate_uniform_noncombat_cards(
    run_state: RunState,
    *,
    num_cards: int,
    character_ids: tuple[str, ...] | None = None,
    include_colorless: bool = False,
    card_type: CardType | None = None,
    rarity: CardRarity | None = None,
    cost: int | None = None,
    costs_x: bool | None = None,
    distinct: bool = False,
) -> list[CardInstance]:
    if character_ids is None:
        character_ids = (run_state.player.character_id,)
    candidate_ids: list = []
    seen: set = set()
    for character_id in character_ids:
        for card_id in eligible_character_cards(
            character_id,
            card_type=card_type,
            rarity=rarity,
            generation_context=None,
        ):
            if distinct and card_id in seen:
                continue
            seen.add(card_id)
            candidate_ids.append(card_id)
    if include_colorless:
        for card_id in eligible_registered_cards(
            module_name="sts2_env.cards.colorless",
            card_type=card_type,
            rarity=rarity,
            generation_context=None,
        ):
            if distinct and card_id in seen:
                continue
            seen.add(card_id)
            candidate_ids.append(card_id)
    if not candidate_ids:
        return []
    filtered_ids = []
    for card_id in candidate_ids:
        card = create_card(card_id, upgraded=False)
        if cost is not None and card.cost != cost:
            continue
        if costs_x is not None and card.has_energy_cost_x != costs_x:
            continue
        filtered_ids.append(card_id)
    if not filtered_ids:
        return []
    cards: list[CardInstance] = []
    available = list(filtered_ids)
    for _ in range(max(0, num_cards)):
        if not available:
            break
        chosen_id = run_state.rng.rewards.choice(available)
        card = create_card(chosen_id, upgraded=False)
        cards.append(card)
        if distinct:
            available.remove(chosen_id)
    return cards
