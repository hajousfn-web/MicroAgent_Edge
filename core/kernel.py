"""Kernel authority for validating and applying advisory proposals."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol
from core.sandbox import Sandbox, SandboxResult
from core.validator import ValidationReport

logger = logging.getLogger(__name__)

class KernelState(str, Enum):
    IDLE = 'IDLE'
    ANALYZING = 'ANALYZING'
    PROPOSING = 'PROPOSING'
    VALIDATING = 'VALIDATING'
    EXECUTING = 'EXECUTING'
    REJECTED = 'REJECTED'
    HALTED = 'HALTED'

class ProposalValidator(Protocol):
    def validate(self, proposal: str) -> ValidationReport: ...

class AdvisoryProposal(Protocol):
    proposed_patch: str

class Advisory(Protocol):
    def analyze_and_propose(self, code_snippet: str, error_log: str,
                            code_graph: str = '') -> AdvisoryProposal: ...

class PatchAdapter(Protocol):
    def apply_patch(self, validated_code: str) -> bool: ...

@dataclass(frozen=True)
class KernelResult:
    status: str
    state: KernelState
    executed: bool
    reason: str = ''
    output: str = ''
    def to_dict(self) -> dict[str, Any]:
        return {'status': self.status, 'state': self.state.value,
                'executed': self.executed, 'reason': self.reason, 'output': self.output}

class ExecutionKernel:
    """FSM owning deterministic validation, subprocess checks, and patch application."""
    _ALLOWED = {
        KernelState.IDLE: {KernelState.ANALYZING, KernelState.VALIDATING, KernelState.HALTED},
        KernelState.ANALYZING: {KernelState.PROPOSING, KernelState.HALTED},
        KernelState.PROPOSING: {KernelState.VALIDATING, KernelState.HALTED},
        KernelState.VALIDATING: {KernelState.EXECUTING, KernelState.REJECTED, KernelState.HALTED},
        KernelState.EXECUTING: {KernelState.IDLE, KernelState.REJECTED, KernelState.HALTED},
        KernelState.REJECTED: {KernelState.IDLE, KernelState.HALTED},
        KernelState.HALTED: set(),
    }
    def __init__(self, validators: list[ProposalValidator], sandbox: Sandbox,
                 adapter: PatchAdapter | None = None) -> None:
        if not validators:
            raise ValueError('At least one deterministic validator is required')
        self._validators = tuple(validators)
        self._sandbox = sandbox
        self._adapter = adapter
        self._state = KernelState.IDLE
    @property
    def state(self) -> KernelState:
        return self._state
    def _transition(self, new_state: KernelState) -> None:
        if new_state not in self._ALLOWED[self._state]:
            raise RuntimeError(f'Illegal kernel transition: {self._state.value} -> {new_state.value}')
        logger.info('Kernel state: %s -> %s', self._state.value, new_state.value)
        self._state = new_state
    def _ensure_idle(self) -> None:
        if self._state is KernelState.HALTED:
            raise RuntimeError('Kernel is halted')
        if self._state is not KernelState.IDLE:
            raise RuntimeError(f'Kernel is busy in state {self._state.value}')
    def process_with_advisor(self, advisor: Advisory, source: str, diagnostics: str,
                             code_graph: str = '') -> KernelResult:
        """Get advisory data, then govern its candidate through the complete FSM."""
        self._ensure_idle()
        self._transition(KernelState.ANALYZING)
        try:
            advice = advisor.analyze_and_propose(source, diagnostics, code_graph)
            self._transition(KernelState.PROPOSING)
            proposal = advice.proposed_patch
            if not isinstance(proposal, str) or not proposal.strip():
                raise ValueError('Advisor returned an empty or invalid patch')
            self._transition(KernelState.VALIDATING)
            return self._validate_and_execute(proposal)
        except Exception:
            if self._state is not KernelState.HALTED:
                self._transition(KernelState.HALTED)
            logger.exception('Advisory workflow failed; kernel halted')
            raise
    def process_proposal(self, proposal: str) -> KernelResult:
        """Validate an externally supplied candidate before any execution."""
        self._ensure_idle()
        if not isinstance(proposal, str) or not proposal.strip():
            raise ValueError('Proposal must be a non-empty string')
        self._transition(KernelState.VALIDATING)
        return self._validate_and_execute(proposal)
    def _validate_and_execute(self, proposal: str) -> KernelResult:
        try:
            reports = [validator.validate(proposal) for validator in self._validators]
        except Exception:
            self._transition(KernelState.HALTED)
            logger.exception('Validator failed; kernel halted')
            raise
        failures = [issue for report in reports for issue in report.issues]
        if any(not report.valid for report in reports) and not failures:
            failures.append('A validator rejected the proposal without a diagnostic')
        if failures:
            reason = '; '.join(failures)
            self._transition(KernelState.REJECTED)
            self._transition(KernelState.IDLE)
            logger.warning('Proposal rejected: %s', reason)
            return KernelResult('REJECTED', self._state, False, reason)
        self._transition(KernelState.EXECUTING)
        try:
            result: SandboxResult = self._sandbox.execute(proposal)
            if not result.success:
                self._transition(KernelState.REJECTED)
                reason = result.error or 'Sandbox reported execution failure'
                self._transition(KernelState.IDLE)
                return KernelResult('FAILED', self._state, False, reason, result.output)
            if self._adapter is not None and not self._adapter.apply_patch(proposal):
                self._transition(KernelState.REJECTED)
                self._transition(KernelState.IDLE)
                return KernelResult('APPLY_FAILED', self._state, False,
                                    'Environment adapter declined patch application', result.output)
        except Exception:
            self._transition(KernelState.HALTED)
            logger.exception('Execution or patch application failed; kernel halted')
            raise
        self._transition(KernelState.IDLE)
        return KernelResult('SUCCESS', self._state, True, output=result.output)
    def halt(self) -> None:
        if self._state is not KernelState.HALTED:
            self._transition(KernelState.HALTED)
