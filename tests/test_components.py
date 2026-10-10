"""Tests for deterministic authority boundaries."""
import json
import unittest
from agent.code_graph import build_code_graph
from agent.reasoning_engine import GemmaAdvisoryAgent
from core.kernel import ExecutionKernel, KernelState
from core.sandbox import SandboxResult
from core.validator import PythonProposalValidator

class FakeSandbox:
    def __init__(self):
        self.calls = []
    def execute(self, source):
        self.calls.append(source)
        return SandboxResult(True, 'ok', return_code=0)

class KernelTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = FakeSandbox()
        self.kernel = ExecutionKernel([PythonProposalValidator()], self.sandbox)
    def test_valid_proposal_is_executed_by_kernel(self):
        result = self.kernel.process_proposal("print('safe')")
        self.assertTrue(result.executed)
        self.assertEqual(self.sandbox.calls, ["print('safe')"])
        self.assertEqual(self.kernel.state, KernelState.COMPLETED)
    def test_blocked_call_is_rejected_without_execution(self):
        result = self.kernel.process_proposal("open('file')")
        self.assertEqual(result.status, 'FAILED')
        self.assertFalse(result.executed)
        self.assertEqual(self.sandbox.calls, [])
    def test_invalid_syntax_is_rejected(self):
        result = self.kernel.process_proposal('def (')
        self.assertEqual(result.status, 'FAILED')
        self.assertEqual(self.sandbox.calls, [])

class AdvisoryTests(unittest.TestCase):
    def test_advisor_returns_data_without_execution(self):
        agent = GemmaAdvisoryAgent(lambda prompt: json.dumps({'proposed_patch':'print(1)', 'rationale':'demo'}))
        result = agent.analyze_and_propose('x = 1', 'demo')
        self.assertEqual(result.proposed_patch, 'print(1)')
    def test_code_graph_does_not_execute_source(self):
        graph = build_code_graph('def f():\n    print(1)')
        self.assertIn('f', graph.functions)
        self.assertIn(('f', 'print'), graph.calls)

if __name__ == '__main__':
    unittest.main()
