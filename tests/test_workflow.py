"""Tests for advisory-to-kernel workflow and bounded harness output."""
import json
import unittest
from agent.reasoning_engine import GemmaAdvisoryAgent
from core.kernel import ExecutionKernel, KernelState
from core.sandbox import Sandbox, SandboxResult
from core.validator import PythonProposalValidator

class FakeSandbox:
    def __init__(self, success=True):
        self.success = success
        self.calls = []
    def execute(self, source):
        self.calls.append(source)
        return SandboxResult(self.success, 'checked', '' if self.success else 'failed', 0 if self.success else 1)

class FakeAdapter:
    def __init__(self, accept=True):
        self.accept = accept
        self.applied = []
    def apply_patch(self, source):
        self.applied.append(source)
        return self.accept

class WorkflowTests(unittest.TestCase):
    def test_advisor_proposal_is_validated_checked_and_then_applied(self):
        sandbox = FakeSandbox()
        adapter = FakeAdapter()
        kernel = ExecutionKernel([PythonProposalValidator()], sandbox, adapter)
        advisor = GemmaAdvisoryAgent(lambda prompt: json.dumps({'proposed_patch': "print('ok')", 'rationale': 'test'}))
        result = kernel.process_with_advisor(advisor, 'x = 1', 'test')
        self.assertTrue(result.executed)
        self.assertEqual(sandbox.calls, ["print('ok')"])
        self.assertEqual(adapter.applied, ["print('ok')"])
        self.assertEqual(kernel.state, KernelState.COMPLETED)
    def test_invalid_candidate_never_reaches_sandbox_or_adapter(self):
        sandbox = FakeSandbox()
        adapter = FakeAdapter()
        kernel = ExecutionKernel([PythonProposalValidator()], sandbox, adapter)
        result = kernel.process_proposal("open('blocked')")
        self.assertEqual(result.status, 'FAILED')
        self.assertEqual(sandbox.calls, [])
        self.assertEqual(adapter.applied, [])
    def test_refused_patch_is_not_reported_as_applied(self):
        adapter = FakeAdapter(accept=False)
        kernel = ExecutionKernel([PythonProposalValidator()], FakeSandbox(), adapter)
        result = kernel.process_proposal('print(1)')
        self.assertEqual(result.status, 'FAILED')
        self.assertFalse(result.executed)
    def test_captured_output_is_bounded(self):
        result = Sandbox(timeout_seconds=3, max_output_bytes=64).execute("import os; print('PATH_PRESENT=' + str('PATH' in os.environ)); print('TMP_IS_CWD=' + str(os.environ.get('TMP') == os.getcwd())); print('x' * 10000)")
        self.assertTrue(result.success and result.output.splitlines()[:2] == ['PATH_PRESENT=False', 'TMP_IS_CWD=True'])
        self.assertLessEqual(len(result.output.encode('utf-8')), 64)

if __name__ == '__main__':
    unittest.main()
