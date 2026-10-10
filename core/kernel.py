"""Kernel authority for bounded, deterministic proposal correction."""
from __future__ import annotations
import logging
import traceback
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace
from typing import Any, Protocol
from core.sandbox import Sandbox, SandboxResult
from core.validator import ValidationReport

logger = logging.getLogger(__name__)

class KernelState(str, Enum):
    IDLE = 'IDLE'
    ANALYZING = 'ANALYZING'
    VALIDATING = 'VALIDATING'
    EXECUTING = 'EXECUTING'
    RETRYING = 'RETRYING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
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
    attempts: int = 0
    feedback: str = ''
    def to_dict(self) -> dict[str, Any]:
        return {'status': self.status, 'state': self.state.value,
                'executed': self.executed, 'reason': self.reason,
                'output': self.output, 'attempts': self.attempts,
                'feedback': self.feedback}

class ExecutionKernel:
    """Run a strict FSM with a bounded number of advisory repair attempts."""
    _ALLOWED = {
        KernelState.IDLE: {KernelState.ANALYZING, KernelState.HALTED},
        KernelState.ANALYZING: {KernelState.VALIDATING, KernelState.FAILED, KernelState.HALTED},
        KernelState.VALIDATING: {KernelState.EXECUTING, KernelState.RETRYING, KernelState.COMPLETED, KernelState.FAILED, KernelState.HALTED},
        KernelState.EXECUTING: {KernelState.RETRYING, KernelState.COMPLETED, KernelState.FAILED, KernelState.HALTED},
        KernelState.RETRYING: {KernelState.ANALYZING, KernelState.FAILED, KernelState.HALTED},
        KernelState.COMPLETED: set(), KernelState.FAILED: set(), KernelState.HALTED: set(),
    }
    def __init__(self, validators: list[ProposalValidator], sandbox: Sandbox,
                 adapter: PatchAdapter | None = None, max_retries: int = 2) -> None:
        if not validators:
            raise ValueError('At least one deterministic validator is required')
        self._check_retry_limit(max_retries)
        self._validators = tuple(validators)
        self._sandbox = sandbox
        self._adapter = adapter
        self.max_retries = max_retries
        self._state = KernelState.IDLE
    @staticmethod
    def _check_retry_limit(value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError('max_retries must be a non-negative integer')
    @property
    def state(self) -> KernelState:
        return self._state
    def _transition(self, new_state: KernelState) -> None:
        if new_state not in self._ALLOWED[self._state]:
            raise RuntimeError(f'Illegal kernel transition: {self._state.value} -> {new_state.value}')
        logger.info('Kernel state: %s -> %s', self._state.value, new_state.value)
        self._state = new_state
    def _ensure_idle(self) -> None:
        if self._state is not KernelState.IDLE:
            raise RuntimeError(f'Kernel cannot start a run from state {self._state.value}')
    @staticmethod
    def _attempt_feedback(attempt: int, phase: str, detail: str,
                          output: str = '', return_code: int | None = None) -> str:
        parts = [f'Attempt {attempt} failed during {phase}.', detail]
        if return_code is not None:
            parts.append(f'Sandbox return code: {return_code}')
        if output:
            parts.append('Captured sandbox output/traceback (verbatim):\n' + output)         return '\n'.join(parts)
    def process_with_advisor(self, advisor: Advisory, source: str, diagnostics: str,
                             code_graph: str = '', max_retries: int | None = None) -> KernelResult:
        """Ask for a patch, validate/run it, and feed exact failures into retries."""
        self._ensure_idle()
        retry_limit = self.max_retries if max_retries is None else max_retries
        self._check_retry_limit(retry_limit)
        feedback = diagnostics
        for attempt in range(1, retry_limit + 2):
            self._transition(KernelState.ANALYZING)
            try:
                advice = advisor.analyze_and_propose(source, feedback, code_graph)
                proposal = advice.proposed_patch
            except Exception:
                detail = traceback.format_exc()
                self._transition(KernelState.FAILED)
                logger.exception('Advisory inference failed')
                return KernelResult('FAILED', self._state, False, detail,
                                    attempts=attempt, feedback=detail)
            if not isinstance(proposal, str) or not proposal.strip():
                detail = 'Advisor returned an empty or invalid patch'
                self._transition(KernelState.FAILED)
                return KernelResult('FAILED', self._state, False, detail,
                                    attempts=attempt, feedback=detail)
            self._transition(KernelState.VALIDATING)
            if proposal.strip() == 'NO_PATCH':
                self._transition(KernelState.COMPLETED)
                return KernelResult('NO_PATCH', self._state, False, attempts=attempt)
            try:
                reports = [validator.validate(proposal) for validator in self._validators]
            except Exception:
                detail = traceback.format_exc()
                self._transition(KernelState.FAILED)
                logger.exception('Validator raised an exception')
                return KernelResult('FAILED', self._state, False, detail,
                                    attempts=attempt, feedback=detail)
            failures = [issue for report in reports for issue in report.issues]
            if any(not report.valid for report in reports) and not failures:
                failures.append('Validator rejected proposal without a diagnostic')
            if failures:
                detail = '
'.join(failures)
                feedback = self._attempt_feedback(attempt, 'validation', detail)
                if attempt <= retry_limit:
                    self._transition(KernelState.RETRYING)
                    continue
                self._transition(KernelState.FAILED)
                return KernelResult('FAILED', self._state, False, detail,
                                    attempts=attempt, feedback=feedback)
            self._transition(KernelState.EXECUTING)
            try:
                result: SandboxResult = self._sandbox.execute(proposal)
            except Exception:
                detail = traceback.format_exc()
                feedback = self._attempt_feedback(attempt, 'sandbox execution', detail)
                if attempt <= retry_limit:
                    self._transition(KernelState.RETRYING)
                    logger.exception('Sandbox raised; requesting a corrected proposal')
                    continue
                self._transition(KernelState.FAILED)
                return KernelResult('FAILED', self._state, False, detail,
                                    attempts=attempt, feedback=feedback)
            if not result.success:
                detail = result.error or 'Sandbox reported execution failure'
                feedback = self._attempt_feedback(attempt, 'sandbox execution', detail,
                                                  result.output, result.return_code)
                if attempt <= retry_limit:
                    self._transition(KernelState.RETRYING)
                    logger.warning('Sandbox failed; retrying proposal (attempt %d)', attempt)
                    continue
                self._transition(KernelState.FAILED)
                return KernelResult('FAILED', self._state, False, detail, result.output,
                                    attempt, feedback)
            if self._adapter is not None:
                try:
                    applied = self._adapter.apply_patch(proposal)
                except Exception:
                    detail = traceback.format_exc()
                    self._transition(KernelState.FAILED)
                    logger.exception('Patch adapter failed')
                    return KernelResult('FAILED', self._state, False, detail,
                                        result.output, attempt, detail)
                if not applied:
                    self._transition(KernelState.FAILED)
                    return KernelResult('FAILED', self._state, False,
                                        'Environment adapter declined patch application',
                                        result.output, attempt)
            self._transition(KernelState.COMPLETED)
            return KernelResult('SUCCESS', self._state, True, output=result.output,
                                attempts=attempt, feedback=feedback if attempt > 1 else '')
        raise RuntimeError('Retry loop terminated without a terminal result')
    def process_proposal(self, proposal: str) -> KernelResult:
        """Validate a supplied proposal once; use process_with_advisor for repair retries."""
        self._ensure_idle()
        if not isinstance(proposal, str) or not proposal.strip():
            raise ValueError('Proposal must be a non-empty string')
        class FixedAdvisory:
            def analyze_and_propose(self, code_snippet: str, error_log: str,
                                    code_graph: str = '') -> Any:
                return SimpleNamespace(proposed_patch=proposal)
        return self.process_with_advisor(FixedAdvisory(), '', '', max_retries=0)
    def halt(self) -> None:
        if self._state not in (KernelState.COMPLETED, KernelState.FAILED, KernelState.HALTED):
            self._transition(KernelState.HALTED)
