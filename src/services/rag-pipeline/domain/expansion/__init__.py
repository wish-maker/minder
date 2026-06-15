"""
Expansion Package

This package contains query expansion strategies for improving
retrieval precision.
"""

from .hyde import HyDEQueryExpander

__all__ = [
    "HyDEQueryExpander",
]
