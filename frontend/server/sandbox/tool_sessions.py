"""Select and identify the transient and snapshot-backed Sandbox Tools."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxToolPair:
    """The two Tool ids serving one Studio Sandbox agent kind."""

    transient: str = ""
    persistent: str = ""

    @property
    def configured(self) -> tuple[str, ...]:
        """Return configured ids once, in transient then persistent order."""
        return tuple(dict.fromkeys(filter(None, (self.transient, self.persistent))))

    def select(self, persistent: bool) -> str:
        """Return the Tool id required by the requested persistence mode."""
        return self.persistent if persistent else self.transient

    def is_persistent(self, tool_id: str) -> bool:
        """Whether a Session belongs to the snapshot-backed Tool."""
        return bool(self.persistent and tool_id == self.persistent)
