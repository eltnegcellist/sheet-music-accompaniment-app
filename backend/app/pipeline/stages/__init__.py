"""Concrete pipeline stages.

Importing this package registers each stage onto `default_registry` so the
controller can resolve them by name. Stages must be side-effect free at
import time apart from registration.
"""

from . import omr, postprocess, preprocess  # noqa: F401 — import for side-effect registration

__all__ = ["omr", "postprocess", "preprocess"]
