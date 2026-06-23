"""
Shared package for Minder services
Provides common models, utilities, and configurations
"""

__version__ = "1.0.0"
__author__ = "Minder Platform Team"

# Import subpackages
from . import config, models, utils

__all__ = [
    "models",
    "utils",
    "config",
]
