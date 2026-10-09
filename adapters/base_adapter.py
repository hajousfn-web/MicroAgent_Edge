"""Interfaces for pluggable target environments."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class BaseEnvironmentAdapter(ABC):
    @abstractmethod
    def read_target_source(self) -> str:
        """Read source currently installed on the target."""
    @abstractmethod
    def capture_telemetry(self) -> dict[str, Any]:
        """Return target telemetry or diagnostic logs."""
    @abstractmethod
    def apply_patch(self, validated_code: str) -> bool:
        """Apply code approved by the kernel; report an explicit result."""
