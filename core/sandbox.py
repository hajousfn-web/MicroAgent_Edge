"""Bounded subprocess harness for candidate Python code."""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SandboxResult:
    success: bool
    output: str = ''
    error: str = ''
    return_code: int | None = None

class Sandbox:
    """Run Python in a temporary working directory with time/output bounds.

    A subprocess is not an OS security sandbox. Production deployments must
    supply container/OS isolation before executing proposals from untrusted sources.
    """
    def __init__(self, timeout_seconds: float = 5.0, max_output_bytes: int = 16_384) -> None:
        if timeout_seconds <= 0 or max_output_bytes < 1:
            raise ValueError('Sandbox limits must be positive')
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
    def execute(self, source: str) -> SandboxResult:
        if not isinstance(source, str) or not source.strip():
            raise ValueError('Source must be a non-empty string')
        with tempfile.TemporaryDirectory(prefix='microagent-edge-') as directory:
            script = Path(directory) / 'proposal.py'
            script.write_text(source, encoding='utf-8')
            env = {'PATH': os.environ.get('PATH', ''), 'PYTHONIOENCODING': 'utf-8'}
            try:
                completed = subprocess.run([sys.executable, '-I', '-S', str(script)],
                    cwd=directory, env=env, capture_output=True, text=True,
                    timeout=self.timeout_seconds, check=False, shell=False)
            except subprocess.TimeoutExpired as exc:
                output = (exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
                return SandboxResult(False, output[:self.max_output_bytes], 'Execution timed out')
            output = (completed.stdout + completed.stderr)[:self.max_output_bytes]
            return SandboxResult(completed.returncode == 0, output,
                '' if completed.returncode == 0 else f'Process exited with code {completed.returncode}', completed.returncode)
