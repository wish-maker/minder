"""
GitHub Plugin Installer
Installs plugins from GitHub repositories with security validation
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class GitHubPluginInstaller:
    """GitHub plugin installer with full implementation"""

    def __init__(self, install_dir: Optional[Path] = None):
        """Initialize installer"""
        self.install_dir = install_dir or Path("/app/plugins")
        self.install_dir.mkdir(parents=True, exist_ok=True)

    def _parse_github_url(self, repo_url: str) -> Dict[str, str]:
        """Parse GitHub URL to extract owner and repo name"""
        repo_url = repo_url.strip().rstrip(".git")

        if "github.com/" in repo_url:
            parts = repo_url.split("github.com/")[-1].split("/")
        else:
            parts = repo_url.split("/")

        if len(parts) >= 2:
            return {
                "owner": parts[0],
                "repo": parts[1],
                "url": f"https://github.com/{parts[0]}/{parts[1]}.git",
            }

        raise ValueError(f"Invalid GitHub URL: {repo_url}")

    async def _clone_repository(self, github_url: str, plugin_name: str) -> Path:
        """Clone repository to plugins directory"""
        plugin_path = self.install_dir / plugin_name

        if plugin_path.exists():
            logger.info(f"Removing existing plugin: {plugin_path}")
            shutil.rmtree(plugin_path, ignore_errors=True)

        logger.info(f"Cloning {github_url} to {plugin_path}")

        # Use subprocess.run for security (no shell)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", github_url, str(plugin_path)],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise Exception(f"Git clone failed: {result.stderr}")

        logger.info("Repository cloned successfully")
        return plugin_path

    def _validate_manifest(self, plugin_path: Path) -> tuple[bool, Optional[Dict], list]:
        """Validate plugin.yml manifest exists and is valid"""
        manifest_file = plugin_path / "plugin.yml"

        if not manifest_file.exists():
            return False, None, ["plugin.yml not found"]

        try:
            import yaml

            with open(manifest_file, "r") as f:
                manifest = yaml.safe_load(f)

            required_fields = ["name", "version", "description"]
            missing_fields = [f for f in required_fields if f not in manifest]

            if missing_fields:
                return False, manifest, [f"Missing required fields: {', '.join(missing_fields)}"]

            version = manifest.get("version", "")
            if version != "1.0.0":
                return False, manifest, [f"Version must be 1.0.0, got: {version}"]

            return True, manifest, []

        except Exception as e:
            return False, None, [f"Failed to parse plugin.yml: {e}"]

    async def _install_dependencies(self, plugin_path: Path) -> bool:
        """Install Python dependencies if requirements.txt exists"""
        req_file = plugin_path / "requirements.txt"

        if not req_file.exists():
            logger.info("No requirements.txt found")
            return True

        try:
            logger.info(f"Installing dependencies from {req_file}")
            result = subprocess.run(
                ["pip", "install", "-r", str(req_file)], capture_output=True, text=True, check=False
            )

            if result.returncode != 0:
                logger.warning(f"Dependency installation warnings: {result.stderr}")

            return True

        except Exception as e:
            logger.error(f"Failed to install dependencies: {e}")
            return False

    async def install_plugin(self, repo_url: str, branch: str = "main") -> Dict[str, Any]:
        """Install plugin from GitHub repository"""
        try:
            logger.info(f"Installing plugin from: {repo_url}")

            github_info = self._parse_github_url(repo_url)
            plugin_name = github_info["repo"]
            github_url = github_info["url"]

            plugin_path = await self._clone_repository(github_url, plugin_name)

            manifest_valid, manifest, manifest_errors = self._validate_manifest(plugin_path)

            if not manifest_valid:
                shutil.rmtree(plugin_path, ignore_errors=True)
                return {
                    "status": "failed",
                    "plugin_name": plugin_name,
                    "errors": manifest_errors,
                    "message": f"Manifest validation failed: {', '.join(manifest_errors)}",
                }

            await self._install_dependencies(plugin_path)

            return {
                "status": "success",
                "plugin_name": plugin_name,
                "version": manifest.get("version"),
                "description": manifest.get("description"),
                "path": str(plugin_path),
                "manifest": manifest,
                "message": f"Plugin '{plugin_name}' installed successfully",
            }

        except Exception as e:
            logger.error(f"Plugin installation failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e), "message": f"Installation failed: {str(e)}"}

    async def remove_plugin(self, plugin_name: str) -> Dict[str, Any]:
        """Remove installed plugin"""
        try:
            plugin_path = self.install_dir / plugin_name

            if not plugin_path.exists():
                return {"status": "not_found", "message": f"Plugin '{plugin_name}' not found"}

            shutil.rmtree(plugin_path, ignore_errors=True)

            return {
                "status": "success",
                "plugin_name": plugin_name,
                "message": f"Plugin '{plugin_name}' removed",
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def list_installed(self) -> list:
        """List installed plugins"""
        plugins = []

        try:
            for plugin_dir in self.install_dir.iterdir():
                if plugin_dir.is_dir() and not plugin_dir.name.startswith("_"):
                    manifest_file = plugin_dir / "plugin.yml"

                    if manifest_file.exists():
                        try:
                            import yaml

                            with open(manifest_file, "r") as f:
                                manifest = yaml.safe_load(f)

                            plugins.append(
                                {
                                    "name": manifest.get("name", plugin_dir.name),
                                    "version": manifest.get("version"),
                                    "description": manifest.get("description"),
                                    "path": str(plugin_dir),
                                }
                            )
                        except Exception:
                            pass

        except Exception as e:
            logger.error(f"Failed to list plugins: {e}")

        return plugins
