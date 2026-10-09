"""Pluggable local inference adapter with advisory-only output."""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Callable
from agent.prompts import build_repair_prompt

@dataclass(frozen=True)
class AdvisoryProposal:
    advisor_model: str
    proposed_patch: str
    rationale: str

class GemmaAdvisoryAgent:
    """Wrap a locally supplied inference function; never executes model output."""
    def __init__(self, inference_fn: Callable[[str], str] | None = None,
                 model_id: str = 'gemma-4-local') -> None:
        if not model_id.strip():
            raise ValueError('model_id must not be empty')
        self.model_id = model_id
        self._inference_fn = inference_fn
    def analyze_and_propose(self, code_snippet: str, error_log: str,
                            code_graph: str = '') -> AdvisoryProposal:
        if self._inference_fn is None:
            raise RuntimeError('No local inference backend configured; inject inference_fn explicitly')
        prompt = build_repair_prompt(code_snippet, error_log, code_graph)
        raw = self._inference_fn(prompt)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError('Local model must return valid JSON') from exc
        if not isinstance(result, dict) or not isinstance(result.get('proposed_patch'), str) or not isinstance(result.get('rationale'), str):
            raise ValueError('Local model JSON must contain string proposed_patch and rationale fields')
        if not result['proposed_patch'].strip():
            raise ValueError('Local model returned an empty patch')
        return AdvisoryProposal(self.model_id, result['proposed_patch'], result['rationale'])
