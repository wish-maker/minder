"""
GitHub Plugin Installer
Minimal implementation for plugin store functionality
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class GitHubPluginInstaller:
    """Minimal GitHub plugin installer implementation"""

    def __init__(self, install_dir: Optional[Path] = None):
        """Initialize installer"""
        self.install_dir = install_dir or Path("plugins/enabled")
        self.install_dir.mkdir(parents=True, exist_ok=True)

    async def install_plugin(self, repo_url: str) -> Dict[str, Any]:
        """Install plugin from GitHub repository"""
        logger.info(f"Install requested for: {repo_url}")
        return {
            "status": "not_implemented",
            "message": "GitHub installer not fully implemented yet",
        }

    async def remove_plugin(self, plugin_name: str) -> Dict[str, Any]:
        """Remove plugin"""
        logger.info(f"Remove requested for: {plugin_name}")
        return {
            "status": "not_implemented",
            "message": "GitHub installer not fully implemented yet",
        }

    async def list_installed(self) -> list:
        """List installed plugins"""
        return []
