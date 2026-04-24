"""Stage registry — maps a stable string name to a stage callable.

The controller looks stages up by name (set in the params YAML) so the
running configuration drives which implementation is used. Tests can
register fakes against the same names without monkey-patching modules.
"""

from __future__ import annotations

from typing import Callable

from .contracts import StageInput, StageOutput

StageFn = Callable[[StageInput], StageOutput]


class StageRegistry:
    def __init__(self) -> None:
        self._stages: dict[str, StageFn] = {}

    def register(self, name: str, fn: StageFn) -> None:
        if name in self._stages:
            raise ValueError(f"Stage already registered: {name}")
        self._stages[name] = fn

    def resolve(self, name: str) -> StageFn:
        try:
            return self._stages[name]
        except KeyError as exc:
            raise KeyError(f"Stage not registered: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._stages)


# Module-level default registry — concrete stages register themselves on
# import so callers only need `from app.pipeline import stages` to populate it.
default_registry = StageRegistry()


def register(name: str) -> Callable[[StageFn], StageFn]:
    """Decorator: `@register("preprocess")` registers a stage at import."""

    def _wrap(fn: StageFn) -> StageFn:
        default_registry.register(name, fn)
        return fn

    return _wrap
