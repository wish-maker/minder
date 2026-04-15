"""
GitHub Plugin Installer
Download and install plugins from GitHub repositories
"""
import os
import logging
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import httpx
import asyncio

logger = logging.getLogger(__name__)


class GitHubPluginInstaller:
    """Install plugins from GitHub repositories"""

    def __init__(self, store_path: str = "/var/lib/minder/plugins", github_token: str = None):
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)
        self.github_token = github_token or os.getenv("GITHUB_TOKEN", "")
        logger.info(f"✅ Plugin installer initialized: {self.store_path}")
        if self.github_token:
            logger.info(f"✅ GitHub authentication configured")

    async def download_plugin(self, repo_url: str, branch: str = "main") -> Dict[str, Any]:
        """
        Download plugin from GitHub repository

        Args:
            repo_url: GitHub repository URL
            branch: Branch name (default: main)

        Returns:
            Download result with path and metadata
        """
        try:
            # Extract owner/repo from URL
            # Support both https://github.com/owner/repo and owner/repo formats
            if "github.com/" in repo_url:
                parts = repo_url.split("github.com/")[-1].split("/")
            else:
                parts = repo_url.split("/")

            if len(parts) < 2:
                raise ValueError(f"Invalid GitHub URL: {repo_url}")

            owner, repo = parts[0], parts[1]
            repo_name = repo.replace(".git", "")

            logger.info(f"Downloading plugin: {owner}/{repo_name}")

            # Create temp directory for download
            with tempfile.TemporaryDirectory() as temp_dir:
                plugin_path = Path(temp_dir) / repo_name

                # Clone repository with authentication if token available
                if self.github_token:
                    repo_url_with_auth = f"https://{self.github_token}@github.com/{owner}/{repo_name}.git"
                else:
                    repo_url_with_auth = f"https://github.com/{owner}/{repo_name}.git"

                clone_cmd = [
                    "git", "clone",
                    "--depth", "1",
                    "--branch", branch,
                    repo_url_with_auth,
                    str(plugin_path)
                ]

                result = subprocess.run(
                    clone_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode != 0:
                    raise RuntimeError(f"Git clone failed: {result.stderr}")

                # Copy to store
                final_path = self.store_path / repo_name
                if final_path.exists():
                    shutil.rmtree(final_path)

                shutil.copytree(plugin_path, final_path)

                logger.info(f"✅ Plugin downloaded to: {final_path}")

                return {
                    "plugin_name": repo_name,
                    "path": str(final_path),
                    "owner": owner,
                    "branch": branch
                }

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Git clone timeout for {repo_url}")
        except Exception as e:
            logger.error(f"Download error: {e}")
            raise

    def scan_plugin_files(self, plugin_path: Path) -> list[str]:
        """Scan plugin directory for Python files"""
        python_files = list(plugin_path.rglob("*.py"))
        logger.info(f"Found {len(python_files)} Python files in plugin")
        return python_files

    def get_plugin_metadata(self, plugin_path: Path) -> Dict[str, Any]:
        """Extract plugin metadata from files"""
        metadata = {
            "name": plugin_path.name,
            "path": str(plugin_path),
            "python_files": [],
            "has_requirements": False,
            "has_init": False
        }

        # Check for requirements.txt
        req_file = plugin_path / "requirements.txt"
        if req_file.exists():
            metadata["has_requirements"] = True
            metadata["requirements"] = req_file.read_text().splitlines()

        # Check for __init__.py
        init_file = plugin_path / "__init__.py"
        metadata["has_init"] = init_file.exists()

        # List Python files
        metadata["python_files"] = [str(f.relative_to(plugin_path)) for f in self.scan_plugin_files(plugin_path)]

        return metadata

    async def install_plugin(self, repo_url: str, branch: str = "main") -> Dict[str, Any]:
        """
        Download and install plugin from GitHub

        Args:
            repo_url: GitHub repository URL
            branch: Branch name

        Returns:
            Installation result
        """
        download_result = await self.download_plugin(repo_url, branch)

        # Get metadata
        plugin_path = Path(download_result["path"])
        metadata = self.get_plugin_metadata(plugin_path)

        return {
            **download_result,
            "metadata": metadata,
            "status": "installed"
        }


async def test_github_installer():
    """Test GitHub plugin installer"""
    installer = GitHubPluginInstaller()

    # Test with a simple repository
    try:
        result = await installer.install_plugin(
            "https://github.com/minder-plugins/example-plugin",
            "main"
        )
        print(f"✅ Plugin installed: {result['plugin_name']}")
        print(f"Path: {result['path']}")
        print(f"Files: {len(result['metadata']['python_files'])}")
    except Exception as e:
        print(f"❌ Installation failed: {e}")
