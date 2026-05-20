"""Trace collection for damage-lab executions."""

from __future__ import annotations

from collections import deque
from typing import Any

from sts2_env.core.enums import ValueProp


def _serialize_props(props: ValueProp) -> list[str]:
    names = [flag.name for flag in ValueProp if flag is not ValueProp.NONE and props & flag]
    return sorted(names)


class LabTraceRecorder:
    """Collect operation-local traces without changing combat behavior."""

    def __init__(self, combat) -> None:
        self.combat = combat
        self.current_operation: dict[str, Any] | None = None
        self._pending_damage_events: deque[dict[str, Any]] = deque()
        self._active_application: dict[str, Any] | None = None

    def begin_operation(self, operation: dict[str, Any]) -> None:
        self.current_operation = {
            "type": operation["type"],
            "input": operation,
        }
        self._pending_damage_events.clear()
        self._active_application = None

    def end_operation(self) -> dict[str, Any]:
        if self.current_operation is None:
            raise RuntimeError("No active operation to finish.")
        result = self.current_operation
        self.current_operation = None
        self._pending_damage_events.clear()
        self._active_application = None
        return result

    def label(self, creature) -> str | None:
        if creature is None:
            return None
        mapping = getattr(self.combat, "_damage_lab_entity_labels", {})
        label = mapping.get(creature)
        if label is not None:
            return label
        base = getattr(creature, "monster_id", None) or ("player" if getattr(creature, "is_player", False) else "creature")
        combat_id = getattr(creature, "combat_id", 0)
        label = f"{base.lower()}#{combat_id}"
        mapping[creature] = label
        self.combat._damage_lab_entity_labels = mapping
        return label

    def start_damage_trace(self, base_damage: int, dealer, target, props: ValueProp) -> None:
        if self.current_operation is None:
            return
        event = {
            "target": self.label(target),
            "dealer": self.label(dealer),
            "props": _serialize_props(props),
            "damage_trace": {
                "base_damage": base_damage,
                "additive": [],
                "multiplicative": [],
                "caps": [],
            },
            "application": None,
        }
        self.current_operation.setdefault("damage_events", []).append(event)
        self._pending_damage_events.append(event)

    def record_damage_additive(self, owner, source_type: str, source_id: str, delta: float, before: float, after: float) -> None:
        event = self._pending_damage_events[-1] if self._pending_damage_events else None
        if event is None:
            return
        event["damage_trace"]["additive"].append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "owner": self.label(owner),
                "delta": delta,
                "before": before,
                "after": after,
            }
        )

    def record_damage_multiplier(
        self,
        owner,
        source_type: str,
        source_id: str,
        multiplier: float,
        before: float,
        after: float,
    ) -> None:
        event = self._pending_damage_events[-1] if self._pending_damage_events else None
        if event is None:
            return
        event["damage_trace"]["multiplicative"].append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "owner": self.label(owner),
                "multiplier": multiplier,
                "before": before,
                "after": after,
            }
        )

    def record_damage_cap(self, owner, source_type: str, source_id: str, cap: float, before: float, after: float) -> None:
        event = self._pending_damage_events[-1] if self._pending_damage_events else None
        if event is None:
            return
        event["damage_trace"]["caps"].append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "owner": self.label(owner),
                "cap": cap,
                "before": before,
                "after": after,
            }
        )

    def finish_damage_trace(self, final_damage: int) -> None:
        event = self._pending_damage_events[-1] if self._pending_damage_events else None
        if event is None:
            return
        event["damage_trace"]["final_damage"] = final_damage

    def start_block_trace(self, base_block: int, target, props: ValueProp) -> None:
        if self.current_operation is None:
            return
        self.current_operation["block_trace"] = {
            "target": self.label(target),
            "props": _serialize_props(props),
            "base_block": base_block,
            "additive": [],
            "multiplicative": [],
        }

    def record_block_additive(self, owner, source_type: str, source_id: str, delta: float, before: float, after: float) -> None:
        trace = self.current_operation.get("block_trace") if self.current_operation is not None else None
        if trace is None:
            return
        trace["additive"].append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "owner": self.label(owner),
                "delta": delta,
                "before": before,
                "after": after,
            }
        )

    def record_block_multiplier(
        self,
        owner,
        source_type: str,
        source_id: str,
        multiplier: float,
        before: float,
        after: float,
    ) -> None:
        trace = self.current_operation.get("block_trace") if self.current_operation is not None else None
        if trace is None:
            return
        trace["multiplicative"].append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "owner": self.label(owner),
                "multiplier": multiplier,
                "before": before,
                "after": after,
            }
        )

    def finish_block_trace(self, final_block: int) -> None:
        trace = self.current_operation.get("block_trace") if self.current_operation is not None else None
        if trace is None:
            return
        trace["final_block"] = final_block

    def begin_application(self, target, damage: int, props: ValueProp, dealer) -> None:
        if self.current_operation is None:
            return
        event = self._pending_damage_events.popleft() if self._pending_damage_events else {
            "target": self.label(target),
            "dealer": self.label(dealer),
            "props": _serialize_props(props),
            "damage_trace": {"base_damage": damage, "additive": [], "multiplicative": [], "caps": [], "final_damage": damage},
            "application": None,
        }
        if event not in self.current_operation.get("damage_events", []):
            self.current_operation.setdefault("damage_events", []).append(event)
        app = {
            "target": self.label(target),
            "damage_input": damage,
            "block_before": target.block,
            "hp_before": target.current_hp,
            "props": _serialize_props(props),
        }
        event["application"] = app
        self._active_application = app

    def record_application_block(self, blocked: int, remaining_after_block: int, unblockable: bool, block_after: int) -> None:
        if self._active_application is None:
            return
        self._active_application["blocked"] = blocked
        self._active_application["remaining_after_block"] = remaining_after_block
        self._active_application["unblockable"] = unblockable
        self._active_application["block_after"] = block_after

    def record_hp_loss_modifier(
        self,
        phase: str,
        owner,
        source_type: str,
        source_id: str,
        before: float,
        after: float,
    ) -> None:
        if self._active_application is None:
            return
        self._active_application.setdefault(phase, []).append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "owner": self.label(owner),
                "before": before,
                "after": after,
            }
        )

    def record_redirect(self, original_target, redirected_target, amount: int, owner, source_id: str) -> None:
        if self._active_application is None:
            return
        self._active_application["redirect"] = {
            "from": self.label(original_target),
            "to": self.label(redirected_target),
            "amount": amount,
            "owner": self.label(owner),
            "source_id": source_id,
        }

    def finish_application(
        self,
        result,
        resolved_target,
        *,
        hp_before: int,
        hp_after: int,
        was_fully_blocked: bool,
    ) -> None:
        if self._active_application is None:
            return
        self._active_application["resolved_target"] = self.label(resolved_target)
        self._active_application["resolved_hp_before"] = hp_before
        self._active_application["resolved_hp_after"] = hp_after
        self._active_application["hp_after"] = hp_after if resolved_target is not None and self.label(resolved_target) == self._active_application["target"] else self._active_application["hp_before"] - result.hp_lost
        self._active_application["hp_lost"] = result.hp_lost
        self._active_application["was_killed"] = result.was_killed
        self._active_application["was_fully_blocked"] = was_fully_blocked
        self._active_application["unblocked_damage"] = result.unblocked_damage
        self._active_application = None
