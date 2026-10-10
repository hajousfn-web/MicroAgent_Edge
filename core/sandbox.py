"""Bounded subprocess harness; not an OS security boundary."""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread

@dataclass(frozen=True)
class SandboxResult:
    success: bool
    output: str = ''
    error: str = ''
    return_code: int | None = None

class Sandbox:
    """Run candidate Python with wall-clock and captured-output bounds.

    A subprocess does not prevent access to host resources. Use OS/container
    isolation before executing proposals from untrusted sources.
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
            env = {'PYTHONIOENCODING': 'utf-8', 'TMP': directory, 'TEMP': directory}
            for name in ('SYSTEMROOT', 'WINDIR'):
                if name in os.environ:
                    env[name] = os.environ[name]
            process = subprocess.Popen(
                [sys.executable, '-I', '-S', str(script)], cwd=directory, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, shell=False, close_fds=True,
            )
            if process.stdout is None:
                process.kill()
                raise RuntimeError('Failed to open sandbox output pipe')
            chunks: list[bytes] = []
            stored = 0
            lock = Lock()
            def drain_output() -> None:
                nonlocal stored
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        return
                    with lock:
                        remaining = self.max_output_bytes - stored
                        if remaining > 0:
                            chunks.append(chunk[:remaining])
                            stored += min(len(chunk), remaining)
            reader = Thread(target=drain_output, name='microagent-output-reader', daemon=True)
            reader.start()
            timed_out = False
            try:
                return_code = process.wait(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                return_code = process.wait()
            reader.join(timeout=1.0)
            with lock:
                output = b''.join(chunks).decode('utf-8', errors='replace')
            if timed_out:
                return SandboxResult(False, output, 'Execution timed out', return_code)
            return SandboxResult(return_code == 0, output,
                '' if return_code == 0 else f'Process exited with code {return_code}', return_code)
