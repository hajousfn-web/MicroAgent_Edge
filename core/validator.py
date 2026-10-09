"""Deterministic Python AST safety checks for advisory proposals."""
from __future__ import annotations
import ast
from dataclasses import dataclass

@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    issues: tuple[str, ...] = ()

class PythonProposalValidator:
    """Reject malformed and obviously hazardous Python before execution.

    This static policy is defense in depth, not a security boundary. Run untrusted
    proposals only in an OS-level sandbox with appropriate isolation.
    """
    _blocked_imports = frozenset({'ctypes', 'subprocess', 'socket', 'multiprocessing', 'importlib'})
    _blocked_calls = frozenset({'exec', 'eval', 'compile', '__import__', 'open', 'breakpoint'})
    def __init__(self, max_source_bytes: int = 64_000, max_nodes: int = 10_000) -> None:
        if max_source_bytes < 1 or max_nodes < 1:
            raise ValueError('Validation limits must be positive')
        self.max_source_bytes = max_source_bytes
        self.max_nodes = max_nodes
    def validate(self, proposal: str) -> ValidationReport:
        issues: list[str] = []
        if not isinstance(proposal, str) or not proposal.strip():
            return ValidationReport(False, ('Proposal must be non-empty Python source',))
        if len(proposal.encode('utf-8')) > self.max_source_bytes:
            return ValidationReport(False, ('Proposal exceeds configured source-size limit',))
        try:
            tree = ast.parse(proposal)
        except SyntaxError as exc:
            return ValidationReport(False, (f'Python syntax error at line {exc.lineno}: {exc.msg}',))
        nodes = list(ast.walk(tree))
        if len(nodes) > self.max_nodes:
            return ValidationReport(False, ('Proposal exceeds configured AST complexity limit',))
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.split('.')[0] for alias in node.names] if isinstance(node, ast.Import) else [(node.module or '').split('.')[0]]
                for name in names:
                    if name in self._blocked_imports:
                        issues.append(f'Import of {name!r} is forbidden by policy')
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self._blocked_calls:
                issues.append(f'Call to {node.func.id!r} is forbidden by policy')
            if isinstance(node, ast.Attribute) and node.attr.startswith('__') and node.attr.endswith('__'):
                issues.append('Dunder attribute access is forbidden by policy')
        return ValidationReport(not issues, tuple(dict.fromkeys(issues)))
