"""
Shared package for Minder services
Provides common models, utilities, and configurations
"""

__version__ = "1.0.0"
__author__ = "Minder Platform Team"

# NOTE: subpackages are intentionally NOT eagerly imported here. Importing one
# shared module (e.g. `from shared.metrics import setup_metrics`) must not drag
# in every subpackage's third-party deps (pydantic-settings via config, etc.) —
# that coupling broke adoption in services that don't need config/models/utils.
# Consumers import the specific submodule they need by full path.

__all__ = [
    "models",
    "utils",
    "config",
    "metrics",
]
