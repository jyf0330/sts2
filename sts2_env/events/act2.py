"""Act 2 specific events.

Events that only appear in Act 2 (act_index == 1), or require act > 0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts2_env.cards.factory import create_card, eligible_registered_cards
from sts2_env.cards.enchantments import can_enchant_card
from sts2_env.cards.status import make_debt, make_feeding_frenzy, make_normality, make_spore_mind
from sts2_env.core.enums import CardRarity, CardType, PotionRarity
from sts2_env.events.shared import (
    _event_result_with_rewards,
    _downgrade_selected_cards,
    _event_potion_options,
    _obtain_random_relics,
    _roll_event_potion_id,
    _remove_n_cards,
    _remove_selected_cards,
    _should_defer_event_rewards,
    _transform_n_cards,
    _transform_selected_cards,
    _upgrade_n_cards,
)
from sts2_env.potions.base import create_potion
from sts2_env.relics.base import RelicId, RelicRarity
from sts2_env.run.reward_objects import (
    AddCardsReward,
    CardReward,
    EnchantCardsReward,
    PotionReward,
    RelicReward,
    RemoveCardReward,
    TransformCardsReward,
)
from sts2_env.run.events import EventModel, EventOption, EventResult, register_event

if TYPE_CHECKING:
    from sts2_env.run.run_state import RunState


# ── CrystalSphere ─────────────────────────────────────────────────────

class CrystalSphere(EventModel):
    """Uncover Future: Pay 50-100g for 3 Prophesize picks.
    Payment Plan: Gain Debt curse for 6 Prophesize picks.
    """

    event_id = "CrystalSphere"

    def __init__(self) -> None:
        self._cost = 50

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.player.gold >= 100 and run_state.current_act_index > 0

    def calculate_vars(self, run_state: RunState) -> None:
        extra = self.get_rng(run_state).next_int_exclusive(1, 50)
        self._cost = 50 + extra

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        self.ensure_vars_calculated(run_state)
        return [
            EventOption("pay", f"Uncover Future ({self._cost}g)",
                         "3 Prophesize picks"),
            EventOption("debt", "Payment Plan",
                         "6 picks, gain Debt curse"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "pay":
            run_state.player.lose_gold(self._cost)
            return EventResult(finished=True,
                               description=f"Paid {self._cost}g for 3 Prophesize picks.")
        if option_id == "debt":
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Gained Debt curse for 6 Prophesize picks.",
                    [AddCardsReward(run_state.player.player_id, [make_debt()])],
                )
            run_state.player.add_card_instance_to_deck(make_debt())
            return EventResult(finished=True,
                               description="Gained Debt curse for 6 Prophesize picks.")
        return EventResult(finished=True)


register_event(CrystalSphere())


# ── DollRoom ──────────────────────────────────────────────────────────

class DollRoom(EventModel):
    """Multi-page: Choose how to pick a doll (relic).

    Random: Get a random doll relic.
    Take Some Time: Take 5 damage, choose from 2 doll relics.
    Examine: Take 15 damage, choose from all 3 doll relics.
    Dolls: Daughter of the Wind, Mr Struggles, Bing Bong.
    """

    event_id = "DollRoom"

    def __init__(self) -> None:
        self._doll_choices: dict[str, str] = {}

    _DOLLS = (
        ("DAUGHTER_OF_THE_WIND", "Daughter of the Wind"),
        ("MR_STRUGGLES", "Mr Struggles"),
        ("BING_BONG", "Bing Bong"),
    )

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.current_act_index == 1

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        self._doll_choices = {}
        return [
            EventOption("random", "Random", "Get a random doll relic"),
            EventOption("take_time", "Take Some Time",
                         "Take 5 damage, choose from 2 dolls"),
            EventOption("examine", "Examine",
                         "Take 15 damage, choose from 3 dolls"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "random":
            relic_id, _ = run_state.rng.niche.choice(list(self._DOLLS))
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Got a random doll relic.",
                    [RelicReward(run_state.player.player_id, relic_id=relic_id)],
                )
            run_state.player.obtain_relic(relic_id)
            return EventResult(finished=True,
                               description="Got a random doll relic.")
        if option_id == "take_time":
            run_state.player.lose_hp(5)
            dolls = list(self._DOLLS)
            self.get_rng(run_state).shuffle(dolls)
            shown = dolls[:2]
            self._doll_choices = {f"doll_{i + 1}": relic_id for i, (relic_id, _) in enumerate(shown)}
            return EventResult(
                finished=False,
                description="Took 5 damage, examining dolls.",
                next_options=[
                    EventOption(option_id, label, f"Gain {label} relic")
                    for option_id, (relic_id, label) in zip(self._doll_choices, shown)
                ],
            )
        if option_id == "examine":
            run_state.player.lose_hp(15)
            dolls = list(self._DOLLS)
            self.get_rng(run_state).shuffle(dolls)
            self._doll_choices = {f"doll_{i + 1}": relic_id for i, (relic_id, _) in enumerate(dolls)}
            return EventResult(
                finished=False,
                description="Took 15 damage, all dolls revealed.",
                next_options=[
                    EventOption(option_id, label, f"Gain {label} relic")
                    for option_id, (relic_id, label) in zip(self._doll_choices, dolls)
                ],
            )
        relic_id = self._doll_choices.get(option_id)
        if relic_id is not None:
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Obtained a doll relic.",
                    [RelicReward(run_state.player.player_id, relic_id=relic_id)],
                )
            run_state.player.obtain_relic(relic_id)
        return EventResult(finished=True,
                           description="Obtained a doll relic.")


register_event(DollRoom())


# ── EndlessConveyor ───────────────────────────────────────────────────

class EndlessConveyor(EventModel):
    """Conveyor belt sushi bar. Pay 35g per grab for random benefits.

    Dishes: Caviar (+4 Max HP), Clam Roll (Heal 10), Spicy Snappy (Upgrade 1),
    Jelly Liver (Transform 1), Fried Eel (Colorless card), Golden Fysh (+75g),
    Seapunk Salad (Feeding Frenzy card), Suspicious Condiment (Potion).
    Observe Chef: Upgrade 1 card (free).
    """

    event_id = "EndlessConveyor"

    def __init__(self) -> None:
        self._grabs = 0
        self._current_dish: str = ""
        self._last_dish: str = ""

    def is_allowed(self, run_state: RunState) -> bool:
        return all(player.gold >= 105 for player in run_state.players)

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        self._grabs = 0
        self._roll_dish(run_state)
        return [
            self._grab_option(run_state, initial=True),
            EventOption("observe", "Observe Chef",
                         "Upgrade 1 random card (free)"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "observe":
            _upgrade_n_cards(run_state, 1, rng=self.get_rng(run_state))
            return EventResult(finished=True,
                               description="Observed chef, upgraded a random card.")
        if option_id == "leave":
            return EventResult(finished=True, description="Left the conveyor.")

        # grab
        if run_state.player.gold >= 35:
            if self._current_dish != "golden_fysh":
                run_state.player.lose_gold(35)
            self._apply_dish(run_state)
            self._grabs += 1
            self._roll_dish(run_state)

            next_opts = [
                self._grab_option(run_state, initial=False),
                EventOption("leave", "Leave", "Done eating"),
            ]

            return EventResult(
                finished=False,
                description=f"Grabbed dish #{self._grabs} from the conveyor.",
                next_options=next_opts,
            )
        return EventResult(finished=True, description="Cannot afford more food.")

    def _grab_option(self, run_state: RunState, *, initial: bool) -> EventOption:
        label = "Grab Something (35g)" if initial else "Grab Another (35g)"
        if run_state.player.gold >= 35:
            return EventOption("grab", label, "Random dish")
        return EventOption("grab", "Locked", "Cannot afford another dish", enabled=False)

    def _roll_dish(self, run_state: RunState) -> None:
        if (self._grabs + 1) % 5 == 0:
            self._last_dish = "seapunk_salad"
            self._current_dish = "seapunk_salad"
            return
        weighted = [
            ("caviar", 6.0),
            ("spicy_snappy", 3.0),
            ("jelly_liver", 3.0),
            ("fried_eel", 3.0),
        ]
        if len(run_state.player.held_potions()) < run_state.player.max_potion_slots:
            weighted.append(("suspicious_condiment", 3.0))
        if run_state.player.current_hp != run_state.player.max_hp:
            weighted.append(("clam_roll", 6.0))
        if self._grabs >= 1:
            weighted.append(("golden_fysh", 1.0))
        weighted = [(dish, weight) for dish, weight in weighted if dish != self._last_dish]
        total = sum(weight for _, weight in weighted)
        roll = self.get_rng(run_state).next_float() * total
        for dish, weight in weighted:
            roll -= weight
            if roll <= 0:
                self._last_dish = dish
                self._current_dish = dish
                return
        self._last_dish = weighted[-1][0]
        self._current_dish = weighted[-1][0]

    def _apply_dish(self, run_state: RunState) -> None:
        dish = self._current_dish
        if dish == "caviar":
            run_state.player.gain_max_hp(4)
        elif dish == "clam_roll":
            run_state.player.heal(10)
        elif dish == "spicy_snappy":
            _upgrade_n_cards(run_state, 1, rng=self.get_rng(run_state))
        elif dish == "jelly_liver":
            _transform_n_cards(run_state, 1, rng=self.get_rng(run_state))
        elif dish == "fried_eel":
            from sts2_env.run.rewards import generate_noncombat_reward_cards

            cards = generate_noncombat_reward_cards(
                run_state,
                num_cards=1,
                character_ids=(),
                include_colorless=True,
            )
            if cards:
                run_state.player.add_card_instance_to_deck(cards[0])
        elif dish == "golden_fysh":
            run_state.player.gain_gold(75)
        elif dish == "seapunk_salad":
            if _should_defer_event_rewards(run_state):
                run_state.pending_rewards.append(AddCardsReward(run_state.player.player_id, [make_feeding_frenzy()]))
            else:
                run_state.player.add_card_instance_to_deck(make_feeding_frenzy())
        elif dish == "suspicious_condiment":
            potion_id = _roll_event_potion_id(run_state)
            if potion_id is not None:
                run_state.pending_rewards.append(PotionReward(run_state.player.player_id, potion_id=potion_id))


register_event(EndlessConveyor())


# ── FakeMerchant ──────────────────────────────────────────────────────

class FakeMerchant(EventModel):
    """Custom merchant event: buy fake relics for 50g each.

    Can throw Foul Potion to start a fight for real rewards.
    """

    event_id = "FakeMerchant"
    is_shared = True

    _INVENTORY_RELICS = (
        RelicId.FAKE_ANCHOR.name,
        RelicId.FAKE_BLOOD_VIAL.name,
        RelicId.FAKE_HAPPY_FLOWER.name,
        RelicId.FAKE_LEES_WAFFLE.name,
        RelicId.FAKE_MANGO.name,
        RelicId.FAKE_ORICHALCUM.name,
        RelicId.FAKE_SNECKO_EYE.name,
        RelicId.FAKE_STRIKE_DUMMY.name,
        RelicId.FAKE_VENERABLE_TEA_SET.name,
    )

    def __init__(self) -> None:
        self._inventories: dict[int, list[str]] = {}

    def _inventory_for(self, run_state: RunState) -> list[str]:
        key = id(run_state)
        inventory = self._inventories.get(key)
        if inventory is None:
            pool = list(self._INVENTORY_RELICS)
            self.get_rng(run_state).shuffle(pool)
            inventory = pool[:6]
            self._inventories[key] = inventory
        return inventory

    def is_allowed(self, run_state: RunState) -> bool:
        if run_state.current_act_index < 1:
            return False
        if len(run_state.players) > 1:
            return False
        has_foul_potion = any(
            p.potion_id == "FoulPotion"
            for p in run_state.player.held_potions()
        )
        return run_state.player.gold >= 100 or has_foul_potion

    def before_event_started(self, run_state: RunState) -> None:
        run_state.player.can_remove_potions = False

    def on_event_finished(self, run_state: RunState) -> None:
        run_state.player.can_remove_potions = True

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        self._inventories[id(run_state)] = self._inventory_for(run_state)
        options = [
            EventOption("buy", "Buy a Relic (50g)", "Purchase a fake relic"),
        ]
        has_foul = any(
            p.potion_id == "FoulPotion"
            for p in run_state.player.held_potions()
        )
        if has_foul:
            options.append(EventOption("throw_foul", "Throw Foul Potion",
                                        "Fight for real rewards"))
        options.append(EventOption("leave", "Leave", "Leave the merchant"))
        return options

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        inventory = self._inventory_for(run_state)
        if option_id == "buy":
            if not inventory:
                return EventResult(finished=True, description="Nothing happened.")
            return EventResult(
                finished=False,
                description="Choose a fake relic to buy.",
                next_options=[
                    EventOption(f"buy_{idx}", relic_id.replace("_", " ").title(), "Buy this fake relic")
                    for idx, relic_id in enumerate(inventory)
                ] + [EventOption("leave", "Leave", "Leave the merchant")],
            )
        if option_id.startswith("buy_"):
            try:
                idx = int(option_id.split("_", 1)[1])
            except ValueError:
                return EventResult(finished=True, description="Nothing happened.")
            if 0 <= idx < len(inventory) and run_state.player.gold >= 50:
                run_state.player.lose_gold(50)
                purchased = inventory.pop(idx)
                if _should_defer_event_rewards(run_state):
                    next_options = []
                    if inventory and run_state.player.gold >= 50:
                        next_options.extend(
                            EventOption(f"buy_{i}", relic_id.replace("_", " ").title(), "Buy this fake relic")
                            for i, relic_id in enumerate(inventory)
                        )
                    has_foul = any(p.potion_id == "FoulPotion" for p in run_state.player.held_potions())
                    if has_foul:
                        next_options.append(EventOption("throw_foul", "Throw Foul Potion", "Fight for real rewards"))
                    next_options.append(EventOption("leave", "Leave", "Leave the merchant"))
                    return EventResult(
                        finished=False,
                        description="Bought a fake relic for 50g.",
                        next_options=next_options,
                        rewards={"reward_objects": [RelicReward(run_state.player.player_id, relic_id=purchased)]},
                    )
                run_state.player.obtain_relic(purchased)
                next_options = []
                if inventory and run_state.player.gold >= 50:
                    next_options.extend(
                        EventOption(f"buy_{i}", relic_id.replace("_", " ").title(), "Buy this fake relic")
                        for i, relic_id in enumerate(inventory)
                    )
                has_foul = any(p.potion_id == "FoulPotion" for p in run_state.player.held_potions())
                if has_foul:
                    next_options.append(EventOption("throw_foul", "Throw Foul Potion", "Fight for real rewards"))
                next_options.append(EventOption("leave", "Leave", "Leave the merchant"))
                return EventResult(
                    finished=False,
                    description="Bought a fake relic for 50g.",
                    next_options=next_options,
                )
            return EventResult(finished=True, description="Could not buy that relic.")
        if option_id == "throw_foul":
            for idx, potion in enumerate(list(run_state.player.held_potions())):
                if potion.potion_id == "FoulPotion":
                    run_state.player.remove_potion(potion.slot_index)
                    break
            stocked_fake_relics = [RelicId.FAKE_MERCHANTS_RUG.name, *inventory]
            rewards = [RelicReward(run_state.player.player_id, relic_id=relic_id) for relic_id in stocked_fake_relics]
            return EventResult(
                finished=True,
                description="Threw Foul Potion and started a fight for real rewards.",
                rewards={"reward_objects": rewards},
                event_combat_setup="fake_merchant",
            )
        return EventResult(finished=True, description="Left the fake merchant.")


register_event(FakeMerchant())


# ── FieldOfManSizedHoles ──────────────────────────────────────────────

class FieldOfManSizedHoles(EventModel):
    """Resist: Remove 2 cards, gain Normality curse.
    Enter Your Hole: Enchant a card with Perfect Fit.
    """

    event_id = "FieldOfManSizedHoles"

    def is_allowed(self, run_state: RunState) -> bool:
        return any(can_enchant_card(card, "PerfectFit") for card in run_state.player.deck)

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        return [
            EventOption("resist", "Resist",
                         "Remove 2 cards, gain Normality curse"),
            EventOption("enter", "Enter Your Hole",
                         "Enchant a card with Perfect Fit"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "resist":
            candidates = run_state.player.removable_deck_cards()
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Removed 2 cards, gained Normality curse.",
                    [
                        RemoveCardReward(
                            run_state.player.player_id,
                            count=min(2, len(candidates)),
                            cards=candidates,
                        ),
                        AddCardsReward(run_state.player.player_id, [make_normality()]),
                    ],
                )
            return self.request_card_choice(
                prompt="Choose 2 cards to remove",
                cards=candidates,
                source_pile="deck",
                resolver=lambda selected: (
                    _remove_selected_cards(selected, run_state),
                    run_state.player.add_card_instance_to_deck(make_normality()),
                    EventResult(finished=True, description="Removed 2 cards, gained Normality curse."),
                )[-1],
                allow_skip=False,
                min_count=min(2, len(candidates)),
                max_count=min(2, len(candidates)),
                description="Choose 2 cards to remove.",
            )
        candidates = [card for card in run_state.player.deck if can_enchant_card(card, "PerfectFit")]
        if not candidates:
            return EventResult(finished=True, description="No valid card for Perfect Fit.")
        if _should_defer_event_rewards(run_state):
            return _event_result_with_rewards(
                "Enchanted a card with Perfect Fit.",
                [
                    EnchantCardsReward(
                        run_state.player.player_id,
                        enchantment="PerfectFit",
                        amount=1,
                        count=1,
                        cards=candidates,
                    )
                ],
            )
        return self.request_card_choice(
            prompt="Choose a card to enchant with Perfect Fit",
            cards=candidates,
            source_pile="deck",
            resolver=lambda selected: (
                selected and selected[0].add_enchantment("PerfectFit", 1),
                EventResult(finished=True, description="Enchanted a card with Perfect Fit."),
            )[-1],
            description="Choose a card to enchant.",
        )


register_event(FieldOfManSizedHoles())


# ── JungleMazeAdventure ──────────────────────────────────────────────

class JungleMazeAdventure(EventModel):
    """Solo Quest: Take 18 damage, gain ~150 gold.
    Join Forces: Gain ~50 gold (safe).
    """

    event_id = "JungleMazeAdventure"
    is_shared = True

    def __init__(self) -> None:
        self._solo_gold = 150
        self._join_gold = 50

    def calculate_vars(self, run_state: RunState) -> None:
        rng = self.get_rng(run_state)
        self._solo_gold = 150 + rng.next_float_range(-15, 15)
        self._join_gold = 50 + rng.next_float_range(-15, 15)

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        self.ensure_vars_calculated(run_state)
        return [
            EventOption("solo", "Solo Quest",
                         f"Take 18 damage, gain {self._solo_gold} gold"),
            EventOption("join", "Join Forces",
                         f"Gain {self._join_gold} gold"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "solo":
            run_state.player.lose_hp(18)
            run_state.player.gain_gold(self._solo_gold)
            return EventResult(finished=True,
                               description=f"Took 18 damage, gained {self._solo_gold} gold.")
        run_state.player.gain_gold(self._join_gold)
        return EventResult(finished=True,
                           description=f"Gained {self._join_gold} gold.")


register_event(JungleMazeAdventure())


# ── LuminousChoir ─────────────────────────────────────────────────────

class LuminousChoir(EventModel):
    """Reach Into the Flesh: Remove 2 cards, gain Spore Mind curse.
    Offer Tribute: Pay ~100-149g, gain a relic.
    """

    event_id = "LuminousChoir"

    def __init__(self) -> None:
        self._cost = 149

    def calculate_vars(self, run_state: RunState) -> None:
        self._cost = 149 - self.get_rng(run_state).next_int_exclusive(0, 50)

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.player.gold >= 149 and run_state.player.has_available_relics()

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        self.ensure_vars_calculated(run_state)
        return [
            EventOption("reach", "Reach Into the Flesh",
                         "Remove 2 cards, gain Spore Mind curse"),
            EventOption(
                "tribute",
                f"Offer Tribute ({self._cost}g)" if run_state.player.gold >= self._cost else "Offer Tribute",
                "Gain a relic",
                enabled=run_state.player.gold >= self._cost and run_state.player.has_available_relics(),
            ),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "reach":
            candidates = run_state.player.removable_deck_cards()
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Removed 2 cards, gained Spore Mind curse.",
                    [
                        RemoveCardReward(
                            run_state.player.player_id,
                            count=min(2, len(candidates)),
                            cards=candidates,
                        ),
                        AddCardsReward(run_state.player.player_id, [make_spore_mind()]),
                    ],
                )
            return self.request_card_choice(
                prompt="Choose 2 cards to remove",
                cards=candidates,
                source_pile="deck",
                resolver=lambda selected: (
                    _remove_selected_cards(selected, run_state),
                    run_state.player.add_card_instance_to_deck(make_spore_mind()),
                    EventResult(finished=True, description="Removed 2 cards, gained Spore Mind curse."),
                )[-1],
                min_count=min(2, len(candidates)),
                max_count=min(2, len(candidates)),
                description="Choose 2 cards to remove.",
            )
        run_state.player.lose_gold(self._cost)
        _obtain_random_relics(run_state, 1)
        return EventResult(finished=True,
                           description=f"Paid {self._cost}g, gained a relic.")


register_event(LuminousChoir())


# ── MorphicGrove ──────────────────────────────────────────────────────

class MorphicGrove(EventModel):
    """Group: Lose 100g, transform 2 cards. Loner: Gain 5 Max HP."""

    event_id = "MorphicGrove"

    def is_allowed(self, run_state: RunState) -> bool:
        return all(player.gold >= 100 for player in run_state.players)

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        return [
            EventOption("group", "Group",
                         "Lose 100g, transform 2 cards"),
            EventOption("loner", "Loner", "Gain 5 Max HP"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "group":
            run_state.player.lose_gold(100)
            candidates = run_state.player.transformable_deck_cards()
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Lost 100g, transformed 2 cards.",
                    [
                        TransformCardsReward(
                            run_state.player.player_id,
                            count=min(2, len(candidates)),
                            cards=candidates,
                        )
                    ],
                )
            return self.request_card_choice(
                prompt="Choose 2 cards to transform",
                cards=candidates,
                source_pile="deck",
                resolver=lambda selected: (
                    _transform_selected_cards(selected, run_state),
                    EventResult(finished=True, description="Lost 100g, transformed 2 cards."),
                )[-1],
                min_count=min(2, len(candidates)),
                max_count=min(2, len(candidates)),
                description="Choose 2 cards to transform.",
            )
        run_state.player.gain_max_hp(5)
        return EventResult(finished=True, description="Gained 5 Max HP.")


register_event(MorphicGrove())


# ── PotionCourier ────────────────────────────────────────────────────

class PotionCourier(EventModel):
    """Grab Potions: Gain 3 Foul Potions. Ransack: Gain 1 uncommon potion."""

    event_id = "PotionCourier"

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.current_act_index > 0

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        return [
            EventOption("grab", "Grab Potions", "Gain 3 Foul Potions"),
            EventOption("ransack", "Ransack", "Gain 1 uncommon potion"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "grab":
            return EventResult(
                finished=True,
                description="Gained 3 Foul Potions.",
                rewards={
                    "reward_objects": [
                        PotionReward(run_state.player.player_id, potion_id="FoulPotion"),
                        PotionReward(run_state.player.player_id, potion_id="FoulPotion"),
                        PotionReward(run_state.player.player_id, potion_id="FoulPotion"),
                    ]
                },
            )
        uncommon_models = [model for model in _event_potion_options(run_state) if model.rarity == PotionRarity.UNCOMMON]
        if uncommon_models:
            model = run_state.rng.rewards.choice(uncommon_models)
            return EventResult(
                finished=True,
                description="Gained an uncommon potion.",
                rewards={"reward_objects": [PotionReward(run_state.player.player_id, potion_id=model.potion_id)]},
            )
        return EventResult(finished=True, description="Gained an uncommon potion.")


register_event(PotionCourier())


# ── RanwidTheElder ────────────────────────────────────────────────────

class RanwidTheElder(EventModel):
    """Give Potion: Lose a potion, gain a relic.
    Give Gold: Lose 100g, gain a relic.
    Give Relic: Lose a relic, gain 2 relics.
    """

    event_id = "RanwidTheElder"

    def __init__(self) -> None:
        self._potion_slot: int | None = None
        self._relic_id: str | None = None

    @staticmethod
    def _tradable_relics(run_state: RunState) -> list[str]:
        return [
            relic_id
            for relic_id in run_state.player.relics
            if relic_id not in {
                "BURNING_BLOOD", "RING_OF_THE_SNAKE", "CRACKED_CORE", "BOUND_PHYLACTERY", "DIVINE_RIGHT",
                "BLACK_BLOOD", "RING_OF_THE_DRAKE", "INFUSED_CORE", "PHYLACTERY_UNBOUND", "DIVINE_DESTINY",
            }
        ]

    def is_allowed(self, run_state: RunState) -> bool:
        return (
            run_state.current_act_index > 0
            and run_state.player.gold >= 100
            and len(run_state.player.held_potions()) > 0
            and bool(self._tradable_relics(run_state))
        )

    def before_event_started(self, run_state: RunState) -> None:
        run_state.player.can_remove_potions = False

    def on_event_finished(self, run_state: RunState) -> None:
        run_state.player.can_remove_potions = True

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        tradable_relics = self._tradable_relics(run_state)
        held_potions = run_state.player.held_potions()
        rng = self.get_rng(run_state)
        chosen_potion = rng.choice(held_potions) if held_potions else None
        chosen_relic = rng.choice(tradable_relics) if tradable_relics else None
        self._potion_slot = chosen_potion.slot_index if chosen_potion is not None else None
        self._relic_id = chosen_relic
        return [
            EventOption("potion", "Give a Potion", "Lose a potion, gain a relic", enabled=bool(run_state.player.held_potions())),
            EventOption("gold", "Give 100 Gold", "Lose 100g, gain a relic"),
            EventOption("relic", "Give a Relic", "Lose a relic, gain 2 relics", enabled=bool(tradable_relics)),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "potion":
            if self._potion_slot is not None:
                run_state.player.remove_potion(self._potion_slot)
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Gave a potion, gained a relic.",
                    _roll_random_relic_rewards(run_state, 1),
                )
            _obtain_random_relics(run_state, 1)
            return EventResult(finished=True,
                               description="Gave a potion, gained a relic.")
        if option_id == "gold":
            run_state.player.lose_gold(100)
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Paid 100g, gained a relic.",
                    _roll_random_relic_rewards(run_state, 1),
                )
            _obtain_random_relics(run_state, 1)
            return EventResult(finished=True,
                               description="Paid 100g, gained a relic.")
        tradable_relics = self._tradable_relics(run_state)
        if self._relic_id is not None and self._relic_id in tradable_relics:
            to_remove = self._relic_id
            if to_remove in run_state.player.relics:
                index = run_state.player.relics.index(to_remove)
                run_state.player.relics.pop(index)
                if index < len(run_state.player.relic_objects):
                    run_state.player.relic_objects.pop(index)
        if _should_defer_event_rewards(run_state):
            return _event_result_with_rewards(
                "Gave a relic, gained 2 relics.",
                _roll_random_relic_rewards(run_state, 2),
            )
        _obtain_random_relics(run_state, 2)
        return EventResult(finished=True,
                           description="Gave a relic, gained 2 relics.")


register_event(RanwidTheElder())


# ── RelicTrader ───────────────────────────────────────────────────────

class RelicTrader(EventModel):
    """Trade an owned relic for a new random relic (up to 3 trade options)."""

    event_id = "RelicTrader"

    def __init__(self) -> None:
        self._owned_relic_choices: list[str] = []
        self._new_relic_choices: list[str] = []

    @staticmethod
    def _tradable_relics(run_state: RunState) -> list[str]:
        return [
            relic_id for relic_id in run_state.player.relics if relic_id not in {
                "BURNING_BLOOD", "RING_OF_THE_SNAKE", "CRACKED_CORE", "BOUND_PHYLACTERY", "DIVINE_RIGHT",
                "BLACK_BLOOD", "RING_OF_THE_DRAKE", "INFUSED_CORE", "PHYLACTERY_UNBOUND", "DIVINE_DESTINY",
            }
        ]

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.current_act_index > 0 and len(self._tradable_relics(run_state)) >= 5

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        owned = self._tradable_relics(run_state)
        self.get_rng(run_state).shuffle(owned)
        self._owned_relic_choices = owned[:3]
        self._new_relic_choices = []
        for _ in self._owned_relic_choices:
            reward = RelicReward(run_state.player.player_id)
            reward.populate(run_state, None)
            self._new_relic_choices.append(reward.relic_id or "CIRCLET")
        options = []
        for i in range(len(self._owned_relic_choices)):
            options.append(EventOption(f"trade_{i}", f"Trade Relic {i+1}",
                                        "Swap an owned relic for a new one"))
        return options

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id.startswith("trade_"):
            index = int(option_id.split("_")[1])
            if 0 <= index < len(self._owned_relic_choices):
                old = self._owned_relic_choices[index]
                new = self._new_relic_choices[index]
                if old in run_state.player.relics:
                    old_index = run_state.player.relics.index(old)
                    run_state.player.relics.pop(old_index)
                    if old_index < len(run_state.player.relic_objects):
                        run_state.player.relic_objects.pop(old_index)
                if _should_defer_event_rewards(run_state):
                    return _event_result_with_rewards(
                        "Traded a relic for a new one.",
                        [RelicReward(run_state.player.player_id, relic_id=new)],
                    )
                run_state.player.obtain_relic(new)
        return EventResult(finished=True,
                           description="Traded a relic for a new one.")


register_event(RelicTrader())


# ── SlipperyBridge ────────────────────────────────────────────────────

class SlipperyBridge(EventModel):
    """Multi-page: Overcome (lose a random card) or Hold On (take escalating damage).

    Hold On damage starts at 3 and increases by 1 each time.
    Each Hold On rerolls which card would be lost.
    """

    event_id = "SlipperyBridge"

    def __init__(self) -> None:
        self._hold_ons = 0
        self._random_card_to_lose = None

    def is_allowed(self, run_state: RunState) -> bool:
        has_removable = any(card.is_removable for card in run_state.player.deck)
        return run_state.total_floor > 6 and has_removable

    def _roll_random_card_to_lose(self, run_state: RunState) -> None:
        if self._random_card_to_lose is None:
            candidates = [
                card for card in run_state.player.deck
                if card.rarity != CardRarity.BASIC and card.is_removable
            ]
        else:
            candidates = [
                card for card in run_state.player.deck
                if card.card_id != self._random_card_to_lose.card_id and card.is_removable
            ]
        if not candidates:
            candidates = [card for card in run_state.player.deck if card.is_removable]
        self._random_card_to_lose = self.get_rng(run_state).choice(candidates) if candidates else None

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        self._hold_ons = 0
        self._random_card_to_lose = None
        self._roll_random_card_to_lose(run_state)
        dmg = 3
        return [
            EventOption("overcome", "Overcome", "Lose a random card"),
            EventOption("hold_on", "Hold On", f"Take {dmg} damage, reroll card"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "overcome":
            if self._random_card_to_lose is None:
                self._roll_random_card_to_lose(run_state)
            if self._random_card_to_lose is not None:
                _remove_selected_cards([self._random_card_to_lose], run_state)
            return EventResult(finished=True,
                               description="Lost a random card to cross the bridge.")

        # hold_on
        dmg = 3 + self._hold_ons
        run_state.player.lose_hp(dmg)
        self._hold_ons += 1
        self._roll_random_card_to_lose(run_state)
        next_dmg = 3 + self._hold_ons

        return EventResult(
            finished=False,
            description=f"Took {dmg} damage, holding on.",
            next_options=[
                EventOption("overcome", "Overcome", "Lose a random card"),
                EventOption("hold_on", "Hold On",
                             f"Take {next_dmg} damage, reroll card"),
            ],
        )


register_event(SlipperyBridge())


# ── SpiralingWhirlpool ────────────────────────────────────────────────

class SpiralingWhirlpool(EventModel):
    """Observe: Enchant a card with Spiral. Drink: Heal 33% of Max HP."""

    event_id = "SpiralingWhirlpool"

    def is_allowed(self, run_state: RunState) -> bool:
        return any(can_enchant_card(card, "Spiral") for card in run_state.player.deck)

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        heal = int(run_state.player.max_hp * 0.33)
        return [
            EventOption("observe", "Observe the Spiral",
                         "Enchant a card with Spiral"),
            EventOption("drink", "Drink", f"Heal {heal} HP"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "observe":
            candidates = [card for card in run_state.player.deck if can_enchant_card(card, "Spiral")]
            if not candidates:
                return EventResult(finished=True, description="No card could be enchanted with Spiral.")
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Enchanted a card with Spiral.",
                    [
                        EnchantCardsReward(
                            run_state.player.player_id,
                            enchantment="Spiral",
                            amount=1,
                            count=1,
                            cards=candidates,
                        )
                    ],
                )
            return self.request_card_choice(
                prompt="Choose a card to enchant with Spiral",
                cards=candidates,
                source_pile="deck",
                resolver=lambda selected: (
                    selected and selected[0].add_enchantment("Spiral", 1),
                    EventResult(finished=True, description="Enchanted a card with Spiral."),
                )[-1],
                description="Choose a card to enchant.",
            )
        heal = int(run_state.player.max_hp * 0.33)
        run_state.player.heal(heal)
        return EventResult(finished=True, description=f"Healed {heal} HP.")


register_event(SpiralingWhirlpool())


# ── StoneOfAllTime ────────────────────────────────────────────────────

class StoneOfAllTime(EventModel):
    """Lift: Discard a potion, gain 10 Max HP.
    Push: Take 6 damage, enchant a card with Vigorous +8.
    """

    event_id = "StoneOfAllTime"

    def __init__(self) -> None:
        self._lift_potion_slot: int | None = None

    def is_allowed(self, run_state: RunState) -> bool:
        return (
            run_state.current_act_index == 1
            and len(run_state.player.held_potions()) >= 1
        )

    def before_event_started(self, run_state: RunState) -> None:
        run_state.player.can_remove_potions = False

    def on_event_finished(self, run_state: RunState) -> None:
        run_state.player.can_remove_potions = True

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        held = run_state.player.held_potions()
        lift_potion = self.get_rng(run_state).choice(held) if held else None
        self._lift_potion_slot = lift_potion.slot_index if lift_potion is not None else None
        has_lift = lift_potion is not None
        has_push = any(can_enchant_card(card, "Vigorous") for card in run_state.player.deck)
        return [
            EventOption("lift", "Lift", "Discard a potion, gain 10 Max HP", enabled=has_lift),
            EventOption("push", "Push", "Take 6 damage, enchant a card with Vigorous +8", enabled=has_push),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "lift":
            if self._lift_potion_slot is None:
                held = run_state.player.held_potions()
                lift_potion = self.get_rng(run_state).choice(held) if held else None
                self._lift_potion_slot = lift_potion.slot_index if lift_potion is not None else None
            if self._lift_potion_slot is not None:
                run_state.player.remove_potion(self._lift_potion_slot)
            run_state.player.gain_max_hp(10)
            self.get_rng(run_state).next_int(0, 99)
            return EventResult(finished=True,
                               description="Discarded a potion, gained 10 Max HP.")
        run_state.player.lose_hp(6)
        candidates = [card for card in run_state.player.deck if can_enchant_card(card, "Vigorous")]
        if not candidates:
            return EventResult(finished=True, description="Took 6 damage, but had no card to enchant.")
        if _should_defer_event_rewards(run_state):
            return _event_result_with_rewards(
                "Took 6 damage, enchanted a card with Vigorous +8.",
                [
                    EnchantCardsReward(
                        run_state.player.player_id,
                        enchantment="Vigorous",
                        amount=8,
                        count=1,
                        cards=candidates,
                    )
                ],
            )
        return self.request_card_choice(
            prompt="Choose a card to enchant with Vigorous",
            cards=candidates,
            source_pile="deck",
            resolver=lambda selected: (
                selected and selected[0].add_enchantment("Vigorous", 8),
                self.get_rng(run_state).next_int(0, 99),
                EventResult(finished=True, description="Took 6 damage, enchanted a card with Vigorous +8."),
            )[-1],
            description="Choose a card to enchant.",
        )


register_event(StoneOfAllTime())


# ── Symbiote ──────────────────────────────────────────────────────────

class Symbiote(EventModel):
    """Approach: Enchant a card with Corrupted.
    Kill with Fire: Transform 1 card.
    """

    event_id = "Symbiote"

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.current_act_index > 0

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        approach_enabled = any(can_enchant_card(card, "Corrupted") for card in run_state.player.deck)
        return [
            EventOption("approach", "Approach", "Enchant a card with Corrupted", enabled=approach_enabled),
            EventOption("kill_fire", "Kill with Fire", "Transform 1 card"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "approach":
            candidates = [card for card in run_state.player.deck if can_enchant_card(card, "Corrupted")]
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Enchanted a card with Corrupted.",
                    [
                        EnchantCardsReward(
                            run_state.player.player_id,
                            enchantment="Corrupted",
                            amount=1,
                            count=1,
                            cards=candidates,
                        )
                    ],
                )
            return self.request_card_choice(
                prompt="Choose a card to enchant with Corrupted",
                cards=candidates,
                source_pile="deck",
                resolver=lambda selected: (
                    selected and selected[0].add_enchantment("Corrupted", 1),
                    EventResult(finished=True, description="Enchanted a card with Corrupted."),
                )[-1],
                description="Choose a card to enchant.",
            )
        candidates = run_state.player.transformable_deck_cards()
        if _should_defer_event_rewards(run_state):
            return _event_result_with_rewards(
                "Transformed 1 card.",
                [
                    TransformCardsReward(
                        run_state.player.player_id,
                        count=min(1, len(candidates)),
                        cards=candidates,
                    )
                ],
            )
        return self.request_card_choice(
            prompt="Choose a card to transform",
            cards=candidates,
            source_pile="deck",
            resolver=lambda selected: (
                _transform_selected_cards(selected, run_state, rng=self.get_rng(run_state)),
                EventResult(finished=True, description="Transformed 1 card."),
            )[-1],
            description="Choose a card to transform.",
        )


register_event(Symbiote())


# ── TheFutureOfPotions ────────────────────────────────────────────────

class TheFutureOfPotions(EventModel):
    """Trade a potion for upgraded card rewards matching rarity."""

    event_id = "TheFutureOfPotions"

    def __init__(self) -> None:
        self._trade_choices: list[tuple[int, CardRarity, CardType]] = []

    def is_allowed(self, run_state: RunState) -> bool:
        return len(run_state.player.held_potions()) >= 2

    def before_event_started(self, run_state: RunState) -> None:
        run_state.player.can_remove_potions = False

    def on_event_finished(self, run_state: RunState) -> None:
        run_state.player.can_remove_potions = True

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        self._trade_choices = []
        potions = run_state.player.held_potions()
        options = []
        for i, p in enumerate(potions[:3]):
            card_types = [CardType.ATTACK, CardType.SKILL, CardType.POWER]
            if p.rarity in {PotionRarity.COMMON, PotionRarity.TOKEN}:
                card_types = [CardType.ATTACK, CardType.SKILL]
            chosen_type = self.get_rng(run_state).choice(card_types)
            self._trade_choices.append((p.slot_index, self._target_card_rarity(p.rarity), chosen_type))
            options.append(
                EventOption(f"trade_{i}", f"Trade {p.potion_id}",
                             "Discard potion for upgraded card reward")
            )
        return options

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if not option_id.startswith("trade_"):
            return EventResult(finished=True, description="Nothing happened.")
        try:
            choice_idx = int(option_id.split("_", 1)[1])
        except ValueError:
            return EventResult(finished=True, description="Nothing happened.")
        if choice_idx < 0 or choice_idx >= len(self._trade_choices):
            return EventResult(finished=True, description="Nothing happened.")

        slot_index, target_rarity, target_type = self._trade_choices[choice_idx]
        run_state.player.remove_potion(slot_index)
        rewards = CardReward(
            run_state.player.player_id,
            option_count=3,
            character_ids=(run_state.player.character_id,),
            forced_rarities=(target_rarity, target_rarity, target_rarity),
            generation_context=None,
            roll_upgrade=False,
            use_default_character_pool=False,
            card_type=target_type,
            upgrade_after_generation=True,
        )
        return EventResult(finished=True,
                           description="Traded a potion for upgraded card rewards.",
                           rewards={"reward_objects": [rewards]})

    @staticmethod
    def _target_card_rarity(potion_rarity: PotionRarity) -> CardRarity:
        if potion_rarity in {PotionRarity.RARE, PotionRarity.EVENT}:
            return CardRarity.RARE
        if potion_rarity == PotionRarity.UNCOMMON:
            return CardRarity.UNCOMMON
        return CardRarity.COMMON

register_event(TheFutureOfPotions())


# ── WaterloggedScriptorium ────────────────────────────────────────────

class WaterloggedScriptorium(EventModel):
    """Bloody Ink: Gain 6 Max HP.
    Tentacle Quill: Pay 65g, enchant 1 card with Steady.
    Prickly Sponge: Pay 155g, enchant 2 cards with Steady.
    """

    event_id = "WaterloggedScriptorium"

    def is_allowed(self, run_state: RunState) -> bool:
        return all(player.gold >= 65 for player in run_state.players)

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        gold = run_state.player.gold
        return [
            EventOption("bloody_ink", "Bloody Ink", "Gain 6 Max HP"),
            EventOption(
                "tentacle_quill",
                "Tentacle Quill (65g)" if gold >= 65 else "Tentacle Quill",
                "Enchant 1 card with Steady",
                enabled=gold >= 65,
            ),
            EventOption(
                "prickly_sponge",
                "Prickly Sponge (155g)" if gold >= 155 else "Prickly Sponge",
                "Enchant 2 cards with Steady",
                enabled=gold >= 155,
            ),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "bloody_ink":
            run_state.player.gain_max_hp(6)
            return EventResult(finished=True, description="Gained 6 Max HP.")
        if option_id == "tentacle_quill":
            run_state.player.lose_gold(65)
            candidates = [card for card in run_state.player.deck if can_enchant_card(card, "Steady")]
            if not candidates:
                return EventResult(finished=True, description="Paid 65g, but had no card to enchant.")
            if _should_defer_event_rewards(run_state):
                return _event_result_with_rewards(
                    "Paid 65g, enchanted 1 card with Steady.",
                    [
                        EnchantCardsReward(
                            run_state.player.player_id,
                            enchantment="Steady",
                            amount=1,
                            count=1,
                            cards=candidates,
                        )
                    ],
                )
            return self.request_card_choice(
                prompt="Choose a card to enchant with Steady",
                cards=candidates,
                source_pile="deck",
                resolver=lambda selected: (
                    selected and selected[0].add_enchantment("Steady", 1),
                    EventResult(finished=True, description="Paid 65g, enchanted 1 card with Steady."),
                )[-1],
                description="Choose a card to enchant.",
            )
        run_state.player.lose_gold(155)
        candidates = [card for card in run_state.player.deck if can_enchant_card(card, "Steady")]
        if not candidates:
            return EventResult(finished=True, description="Paid 155g, but had no cards to enchant.")
        if _should_defer_event_rewards(run_state):
            return _event_result_with_rewards(
                "Paid 155g, enchanted 2 cards with Steady.",
                [
                    EnchantCardsReward(
                        run_state.player.player_id,
                        enchantment="Steady",
                        amount=1,
                        count=min(2, len(candidates)),
                        cards=candidates,
                    )
                ],
            )
        return self.request_card_choice(
            prompt="Choose 2 cards to enchant with Steady",
            cards=candidates,
            source_pile="deck",
            resolver=lambda selected: (
                [card.add_enchantment("Steady", 1) for card in selected],
                EventResult(finished=True, description="Paid 155g, enchanted 2 cards with Steady."),
            )[-1],
            min_count=min(2, len(candidates)),
            max_count=min(2, len(candidates)),
            description="Choose 2 cards to enchant.",
        )


register_event(WaterloggedScriptorium())


# ── WelcomeToWongos ───────────────────────────────────────────────────

class WelcomeToWongos(EventModel):
    """Bargain Bin: 100g for common relic. Featured Item: 200g for rare relic.
    Mystery Box: 300g for mystery ticket. Leave: Downgrade a random card.
    """

    event_id = "WelcomeToWongos"

    def __init__(self) -> None:
        self._featured_relic_id: str | None = None

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.current_act_index == 1 and run_state.player.gold >= 100

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        gold = run_state.player.gold
        featured = RelicReward(run_state.player.player_id, rarity=RelicRarity.RARE)
        featured.populate(run_state, None)
        self._featured_relic_id = featured.relic_id
        options: list[EventOption] = [
            EventOption(
                "bargain_bin",
                "Bargain Bin (100g)" if gold >= 100 else "Bargain Bin",
                "Common relic",
                enabled=gold >= 100,
            )
        ]
        if gold >= 200:
            options.append(EventOption("featured", "Featured Item (200g)",
                                        "Rare relic"))
        else:
            options.append(EventOption("featured", "Featured Item", "Rare relic", enabled=False))
        if gold >= 300:
            options.append(EventOption("mystery", "Mystery Box (300g)",
                                        "Mystery ticket relic"))
        else:
            options.append(EventOption("mystery", "Mystery Box", "Mystery ticket relic", enabled=False))
        options.append(EventOption("leave", "Leave",
                                    "Downgrade a random upgraded card"))
        return options

    def _finish_purchase(
        self,
        run_state: RunState,
        *,
        description: str,
        points: int,
        reward_objects: list[object] | None = None,
    ) -> EventResult:
        previous_points = run_state.player.wongo_points
        run_state.player.wongo_points += points
        run_state.extra_fields["wongo_points_earned"] = points
        if run_state.player.wongo_points // 2000 > previous_points // 2000:
            badge_reward = RelicReward(run_state.player.player_id, relic_id=RelicId.WONGO_CUSTOMER_APPRECIATION_BADGE.name)
            if not _should_defer_event_rewards(run_state):
                run_state.player.obtain_relic(RelicId.WONGO_CUSTOMER_APPRECIATION_BADGE.name)
            elif reward_objects is None:
                reward_objects = [badge_reward]
            else:
                reward_objects = [*reward_objects, badge_reward]
        if reward_objects and _should_defer_event_rewards(run_state):
            return _event_result_with_rewards(description, reward_objects)
        return EventResult(finished=True, description=description)

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "bargain_bin":
            run_state.player.lose_gold(100)
            reward = RelicReward(run_state.player.player_id, rarity=RelicRarity.COMMON)
            reward.populate(run_state, None)
            rewards: list[object] | None = None
            if reward.relic_id is not None:
                if _should_defer_event_rewards(run_state):
                    rewards = [RelicReward(run_state.player.player_id, relic_id=reward.relic_id)]
                else:
                    run_state.player.obtain_relic(reward.relic_id)
            return self._finish_purchase(
                run_state,
                description="Bought common relic for 100g.",
                points=32,
                reward_objects=rewards,
            )
        if option_id == "featured":
            run_state.player.lose_gold(200)
            reward_id = self._featured_relic_id
            rewards = None
            if reward_id is not None:
                if _should_defer_event_rewards(run_state):
                    rewards = [RelicReward(run_state.player.player_id, relic_id=reward_id)]
                else:
                    run_state.player.obtain_relic(reward_id)
            return self._finish_purchase(
                run_state,
                description="Bought rare relic for 200g.",
                points=16,
                reward_objects=rewards,
            )
        if option_id == "mystery":
            run_state.player.lose_gold(300)
            rewards = None
            if _should_defer_event_rewards(run_state):
                rewards = [RelicReward(run_state.player.player_id, relic_id="WONGOS_MYSTERY_TICKET")]
            else:
                run_state.player.obtain_relic("WONGOS_MYSTERY_TICKET")
            return self._finish_purchase(
                run_state,
                description="Bought mystery box for 300g.",
                points=8,
                reward_objects=rewards,
            )
        upgraded_cards = [card for card in run_state.player.deck if card.upgraded]
        if upgraded_cards:
            _downgrade_selected_cards([self.get_rng(run_state).choice(upgraded_cards)], run_state)
        return EventResult(finished=True,
                           description="Left Wongo's, downgraded a card.")


register_event(WelcomeToWongos())


# ── WhisperingHollow ──────────────────────────────────────────────────

class WhisperingHollow(EventModel):
    """Gold: Pay 50g, gain 2 potions. Hug: Take 9 damage, transform 1 card."""

    event_id = "WhisperingHollow"

    def is_allowed(self, run_state: RunState) -> bool:
        return run_state.player.gold >= 50

    def generate_initial_options(self, run_state: RunState) -> list[EventOption]:
        return [
            EventOption("gold", "Pay Gold (50g)", "Gain 2 potions"),
            EventOption("hug", "Hug", "Take 9 damage, transform 1 card"),
        ]

    def choose(self, run_state: RunState, option_id: str) -> EventResult:
        if option_id == "gold":
            run_state.player.lose_gold(50)
            rewards = [PotionReward(run_state.player.player_id), PotionReward(run_state.player.player_id)]
            return EventResult(
                finished=True,
                description="Paid 50g, gained 2 potions.",
                rewards={"reward_objects": rewards},
            )
        candidates = run_state.player.transformable_deck_cards()
        if _should_defer_event_rewards(run_state):
            run_state.player.lose_hp(9)
            return _event_result_with_rewards(
                "Took 9 damage, transformed 1 card.",
                [
                    TransformCardsReward(
                        run_state.player.player_id,
                        count=min(1, len(candidates)),
                        cards=candidates,
                    )
                ],
            )
        return self.request_card_choice(
            prompt="Choose a card to transform",
            cards=candidates,
            source_pile="deck",
            resolver=lambda selected: (
                _transform_selected_cards(selected, run_state, rng=self.get_rng(run_state)),
                run_state.player.lose_hp(9),
                EventResult(finished=True, description="Took 9 damage, transformed 1 card."),
            )[-1],
            description="Choose a card to transform.",
        )


register_event(WhisperingHollow())
