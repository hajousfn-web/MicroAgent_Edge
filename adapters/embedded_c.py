"""File-backed adapter for embedded C/C++ firmware source."""
from __future__ import annotations
import os
import platform
import tempfile
from pathlib import Path
from typing import Any
from adapters.base_adapter import BaseEnvironmentAdapter

class EmbeddedCAdapter(BaseEnvironmentAdapter):
    """Atomically update one configured firmware source file.

    Compilation, flashing and hardware validation are intentionally delegated to
    an explicitly configured device/toolchain workflow.
    """
    def __init__(self, source_path: str | Path) -> None:
        self.source_path = Path(source_path).expanduser().resolve()
    def read_target_source(self) -> str:
        return self.source_path.read_text(encoding='utf-8')
    def capture_telemetry(self) -> dict[str, Any]:
        stat = self.source_path.stat()
        return {'host_platform': platform.platform(), 'source_bytes': stat.st_size,
                'source_mtime': stat.st_mtime, 'device_connected': False}
    def apply_patch(self, validated_code: str) -> bool:
        if not isinstance(validated_code, str) or not validated_code.strip():
            raise ValueError('Patch must be non-empty text')
        self.source_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f'.{self.source_path.name}.', dir=self.source_path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
                stream.write(validated_code)
                stream.flush()
                os.fsync(stream.fileno())
            Path(temporary).replace(self.source_path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise
        return True
