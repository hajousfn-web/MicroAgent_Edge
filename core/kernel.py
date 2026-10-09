"""Kernel authority for validating and applying advisory proposals."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from core.sandbox import Sandbox, SandboxResult
from core.validator import ValidationReport

logger = logging.getLogger(__name__)


class KernelState(str, Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    PROPOSING = "PROPOSING"
    VALIDATING = "VALIDATING"
    EXECUTING = "EXECUTING"
    REJECTED = "REJECTED"
    HALTED = "HALTED"


class ProposalValidator(Protocol):
    def validate(self, proposal: str) -> ValidationReport: ...


@dataclass(frozen=True)
class KernelResult:
    status: str
    state: KernelState
    executed: bool
    reason: str = ""
    output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "state": self.state.value,
                "executed": self.executed, "reason": self.reason,
                "output": self.output}


class ExecutionKernel:
    """Deterministic state machine; the agent never invokes execution itself."""

    _ALLOWED = {
        KernelState.IDLE: {KernelState.ANALYZING, KernelState.VALIDATING, KernelState.HALTED},
        KernelState.ANALYZING: {KernelState.PROPOSING, KernelState.REJECTED, KernelState.HALTED},
        KernelState.PROPOSING: {KernelState.VALIDATING, KernelState.REJECTED, KernelState.HALTED},
        KernelState.VALIDATING: {KernelState.EXECUTING, KernelState.REJECTED, KernelState.HALTED},
        KernelState.EXECUTING: {KernelState.IDLE, KernelState.REJECTED, KernelState.HALTED},
        KernelState.REJECTED: {KernelState.IDLE, KernelState.HALTED},
        KernelState.HALTED: set(),
    }

    def __init__(self, validators: list[ProposalValidator], sandbox: Sandbox) -> None:
        if not validators:
            raise ValueError("At least one deterministic validator is required")
        self._validators = tuple(validators)
        self._sandbox = sandbox
        self._state = KernelState.IDLE

    @property
    def state(self) -> KernelState:
        return self._state

    def _transition(self, new_state: KernelState) -> None:
        if new_state not in self._ALLOWED[self._state]:
            raise RuntimeError(f"Illegal kernel transition: {self._state.value} -> {new_state.value}")
        logger.info("Kernel state: %s -> %s", self._state.value, new_state.value)
        self._state = new_state

    def process_proposal(self, proposal: str, context: Mapping[str, Any] | None = None) -> KernelResult:
        """Validate first, then execute only in the configured isolated sandbox."""
        if self._state is KernelState.HALTED:
            return KernelResult("HALTED", self._state, False, "Kernel is halted")
        if self._state is not KernelState.IDLE:
            raise RuntimeError(f"Kernel is busy in state {self._state.value}")
        if not isinstance(proposal, str) or not proposal.strip():
            raise ValueError("Proposal must be a non-empty string")

        self._transition(KernelState.VALIDATING)
        reports = [validator.validate(proposal) for validator in self._validators]
        failures = [issue for report in reports for issue in report.issues]
        if failures:
            reason = "; ".join(failures)
            self._transition(KernelState.REJECTED)
            self._transition(KernelState.IDLE)
            logger.warning("Proposal rejected: %s", reason)
            return KernelResult("REJECTED", self._state, False, reason)

        self._transition(KernelState.EXECUTING)
        try:
            result: SandboxResult = self._sandbox.execute(proposal)
        except Exception:
            self._transition(KernelState.HALTED)
            logger.exception("Sandbox execution failed; kernel halted")
            raise
        if not result.success:
            self._transition(KernelState.REJECTED)
            reason = result.error or "Sandbox reported execution failure"
            self._transition(KernelState.IDLE)
            return KernelResult("FAILED", self._state, False, reason, result.output)
        self._transition(KernelState.IDLE)
        return KernelResult("SUCCESS", self._state, True, output=result.output)

    def halt(self) -> None:
        if self._state is not KernelState.HALTED:
            self._transition(KernelState.HALTED)
