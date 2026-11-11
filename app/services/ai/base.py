"""Provider-agnostic interface for text generation.

Services depend on this protocol, never on a vendor SDK, so providers can be
swapped or added (and replaced by test doubles) without touching business logic.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class GenerationResult:
    data: dict[str, Any]
    provider: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


class AIProvider(Protocol):
    name: str
    model: str

    def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any], images: list[bytes] | None = None
    ) -> GenerationResult:
        """Return an object that matches `schema` (JSON Schema). `images` (PNG) are shown to the model."""
        ...
