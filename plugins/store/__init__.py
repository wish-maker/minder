"""
Minder Plugin Store
GitHub repolarından plugin yönetimi
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
import logging
import subprocess
import shutil
from datetime import datetime

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


class PluginStore:
    """
    Plugin Store - GitHub repolarından plugin yönetimi

    Jellyfin tarzı plugin sistemi:
    - Plugin'ler ayrı git repo'ları olarak
    - GitHub'dan clone edilip yükleniyor
    - Version control ve update desteği
    - 3rd party plugin desteği
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.store_path = Path(config.get("store_path", "/var/lib/minder/plugins"))
        self.store_path.mkdir(parents=True, exist_ok=True)

        self.index_url = config.get("index_url", "")
        self.github_token = config.get("github_token", "")

        self.installed_plugins: Dict[str, Dict[str, Any]] = {}
        self.plugin_index: List[Dict[str, Any]] = []

    async def initialize(self):
        """Plugin store'u başlat"""
        logger.info("🏪 Initializing Plugin Store...")

        # İndex'i yükle
        if self.index_url:
            await self._load_index()

        # Yüklü plugin'leri tara
        await self._scan_installed_plugins()

        logger.info(f"✅ Plugin Store ready: {len(self.installed_plugins)} plugins installed")

    async def _load_index(self):
        """Plugin index'ini yükle"""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(self.index_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.plugin_index = data.get("plugins", [])
                        logger.info(f"📋 Loaded {len(self.plugin_index)} plugins from index")
        except Exception as e:
            logger.warning(f"Failed to load plugin index: {e}")

    async def _scan_installed_plugins(self):
        """Yüklü plugin'leri tara"""
        for plugin_dir in self.store_path.iterdir():
            if plugin_dir.is_dir():
                manifest_file = plugin_dir / "plugin.yml"

                if manifest_file.exists():
                    try:
                        manifest = await self._load_manifest(plugin_dir)

                        # Git repo'su kontrol et
                        repo_url = manifest.get("repository", "")
                        is_git = (plugin_dir / ".git").exists()

                        self.installed_plugins[plugin_dir.name] = {
                            "path": plugin_dir,
                            "manifest": manifest,
                            "version": manifest.get("version", "unknown"),
                            "repository": repo_url,
                            "is_git": is_git,
                            "installed_at": datetime.fromtimestamp(plugin_dir.stat().st_mtime).isoformat(),
                        }

                        logger.info(f"📦 Found plugin: {plugin_dir.name}")

                    except Exception as e:
                        logger.error(f"Error loading plugin {plugin_dir.name}: {e}")

    async def search_plugins(self, query: str) -> List[Dict[str, Any]]:
        """Plugin ara"""
        results = []

        for plugin in self.plugin_index:
            searchable_text = (
                plugin.get("name", "") + plugin.get("description", "") + " ".join(plugin.get("tags", []))
            ).lower()

            if query.lower() in searchable_text:
                results.append(plugin)

        return results

    async def install_plugin(self, repo_url: str, branch: str = "main", version: str = "latest") -> Dict[str, Any]:
        """Plugin'i GitHub reposundan kur"""

        plugin_name = repo_url.split("/")[-1].replace(".git", "")
        install_path = self.store_path / plugin_name

        if plugin_name in self.installed_plugins:
            raise ValueError(f"Plugin already installed: {plugin_name}")

        logger.info(f"📦 Installing plugin: {plugin_name} from {repo_url}")

        try:
            # 1. Clone repo
            logger.info("📥 Cloning repository...")
            subprocess.run(
                [
                    "git",
                    "clone",
                    "-b",
                    branch,
                    "--single-branch",
                    repo_url,
                    str(install_path),
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )

            # 2. Manifest'i yükle
            manifest = await self._load_manifest(install_path)
            logger.info(f"📋 Plugin: {manifest['name']} v{manifest['version']}")

            # 3. Version kontrolü
            if version != "latest":
                await self._checkout_version(install_path, version)

            # 4. Dependencies'leri yükle
            await self._install_dependencies(install_path)

            # 5. Plugin'i validate et
            validation_result = await self._validate_plugin(install_path, manifest)

            if not validation_result["valid"]:
                shutil.rmtree(install_path)
                raise ValueError(f"Plugin validation failed: {validation_result['errors']}")

            # 6. Plugin'i kaydet
            self.installed_plugins[plugin_name] = {
                "path": install_path,
                "manifest": manifest,
                "version": manifest.get("version", "unknown"),
                "repository": repo_url,
                "is_git": True,
                "installed_at": datetime.now().isoformat(),
                "validated": True,
            }

            logger.info(f"✅ Plugin installed successfully: {plugin_name}")

            return {
                "plugin": plugin_name,
                "version": manifest["version"],
                "status": "installed",
                "warnings": validation_result.get("warnings", []),
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Git clone timeout for {repo_url}")
            if install_path.exists():
                shutil.rmtree(install_path)
            raise
        except Exception as e:
            logger.error(f"Failed to install plugin {plugin_name}: {e}")
            if install_path.exists():
                shutil.rmtree(install_path)
            raise

    async def uninstall_plugin(self, plugin_name: str) -> bool:
        """Plugin'i kaldır"""

        if plugin_name not in self.installed_plugins:
            raise ValueError(f"Plugin not installed: {plugin_name}")

        install_path = self.installed_plugins[plugin_name]["path"]

        logger.info(f"🗑️  Uninstalling plugin: {plugin_name}")

        try:
            # Plugin'i disable et (yüklüyse)
            # TODO: Registry'e entegrasyon

            # Dosyaları sil
            shutil.rmtree(install_path)

            # Kayıttan çıkar
            del self.installed_plugins[plugin_name]

            logger.info(f"✅ Plugin uninstalled: {plugin_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to uninstall plugin {plugin_name}: {e}")
            return False

    async def update_plugin(self, plugin_name: str) -> Dict[str, Any]:
        """Plugin'i güncelle"""

        if plugin_name not in self.installed_plugins:
            raise ValueError(f"Plugin not installed: {plugin_name}")

        logger.info(f"🔄 Updating plugin: {plugin_name}")

        current_info = self.installed_plugins[plugin_name]
        repo_url = current_info["repository"]
        current_branch = current_info["manifest"].get("branch", "main")

        # Mevcur versiyonu kaydet
        old_version = current_info["version"]

        # Mevcur kurulumu kaldır
        await self.uninstall_plugin(plugin_name)

        # Yeni versiyonu kur
        result = await self.install_plugin(repo_url, current_branch)

        logger.info(f"✅ Plugin updated: {plugin_name} {old_version} → {result['version']}")

        return result

    async def list_installed_plugins(self) -> List[Dict[str, Any]]:
        """Kurulu plugin'leri listele"""

        plugins = []

        for plugin_name, info in self.installed_plugins.items():
            plugins.append(
                {
                    "name": plugin_name,
                    "version": info["version"],
                    "description": info["manifest"]["description"],
                    "author": info["manifest"]["author"],
                    "repository": info["repository"],
                    "installed_at": info["installed_at"],
                    "validated": info.get("validated", False),
                    "is_git": info["is_git"],
                }
            )

        return plugins

    async def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Plugin detayını al"""

        if plugin_name not in self.installed_plugins:
            return None

        info = self.installed_plugins[plugin_name]

        # README'yi oku
        readme_file = info["path"] / "README.md"
        readme_content = None
        if readme_file.exists():
            with open(readme_file) as f:
                readme_content = f.read()

        # Changelog'i oku
        changelog_file = info["path"] / "CHANGELOG.md"
        changelog_content = None
        if changelog_file.exists():
            with open(changelog_file) as f:
                changelog_content = f.read()

        # GitHub repo bilgilerini çek
        repo_stats = await self._get_repo_stats(info["repository"])

        return {
            "name": plugin_name,
            "manifest": info["manifest"],
            "repository": info["repository"],
            "readme": readme_content,
            "changelog": changelog_content,
            "repo_stats": repo_stats,
            "installed_at": info["installed_at"],
        }

    async def _load_manifest(self, plugin_path: Path) -> Dict[str, Any]:
        """Plugin manifest'i yükle"""

        manifest_file = plugin_path / "plugin.yml"

        if not manifest_file.exists():
            raise FileNotFoundError(f"Plugin manifest not found: {manifest_file}")

        if yaml is None:
            raise ImportError("PyYAML not installed. Install: pip install pyyaml")

        with open(manifest_file) as f:
            return yaml.safe_load(f)

    async def _install_dependencies(self, plugin_path: Path):
        """Plugin dependencies'lerini yükle"""

        requirements_file = plugin_path / "requirements.txt"

        if requirements_file.exists():
            logger.info(f"📦 Installing dependencies for {plugin_path.name}...")

            subprocess.run(["pip", "install", "-r", str(requirements_file)], check=True)

    async def _checkout_version(self, plugin_path: Path, version: str):
        """Belirli bir versiyona checkout et"""

        logger.info(f"🔀 Checking out version: {version}")

        subprocess.run(
            ["git", "checkout", version],
            cwd=str(plugin_path),
            check=True,
            capture_output=True,
        )

    async def _validate_plugin(self, plugin_path: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Plugin'i validate et"""

        errors = []
        warnings = []

        # 1. Zorunlu alanlar
        required_fields = [
            "name",
            "version",
            "description",
            "author",
            "repository",
        ]
        for field in required_fields:
            if field not in manifest:
                errors.append(f"Missing required field: {field}")

        # 2. Minder version uyumluluğu
        minder_version = "1.0.0"  # TODO: config'dan al
        min_version = manifest.get("minder", {}).get("min_version", "0.0.0")
        max_version = manifest.get("minder", {}).get("max_version", "999.0.0")

        # Basit version karşılaştırma
        from packaging import version as pv

        try:
            if pv.parse(minder_version) < pv.parse(min_version):
                errors.append(f"Minder version too old. Required: {min_version}")
            if pv.parse(minder_version) > pv.parse(max_version):
                errors.append(f"Minder version too new. Max supported: {max_version}")
        except Exception as e:
            warnings.append(f"Could not verify version compatibility: {e}")

        # 3. Python dosyası kontrolü
        plugin_file = None
        for file in plugin_path.glob("*_plugin.py"):
            plugin_file = file
            break

        if plugin_file is None:
            # _module.py de kabul et
            for file in plugin_path.glob("*_module.py"):
                plugin_file = file
                break

        if plugin_file is None:
            errors.append("No plugin implementation file found (*_plugin.py or *_module.py)")

        # 4. Python syntax kontrolü
        if plugin_file:
            try:
                subprocess.run(
                    ["python3", "-m", "py_compile", str(plugin_file)],
                    check=True,
                    capture_output=True,
                )
            except Exception as e:
                errors.append(f"Syntax error in plugin file: {e}")

        # 5. Güvenlik uyarısı
        if not manifest.get("license"):
            warnings.append("No license specified")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    async def _get_repo_stats(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """GitHub repo istatistiklerini çek"""

        try:
            import aiohttp

            # GitHub URL'den owner/repo çıkar
            # https://github.com/owner/repo -> owner/repo
            parts = repo_url.replace("https://github.com/", "").split("/")
            if len(parts) < 2:
                return None

            owner, repo = parts[0], parts[1]

            # GitHub API'den repo bilgilerini çek
            api_url = f"https://api.github.com/repos/{owner}/{repo}"

            headers = {}
            if self.github_token:
                headers["Authorization"] = f"token {self.github_token}"

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "stars": data.get("stargazers_count", 0),
                            "forks": data.get("forks_count", 0),
                            "open_issues": data.get("open_issues_count", 0),
                            "description": data.get("description", ""),
                            "language": data.get("language", ""),
                            "updated_at": data.get("updated_at", ""),
                        }

        except Exception as e:
            logger.warning(f"Could not fetch repo stats: {e}")

        return None

    async def check_updates(self) -> Dict[str, Any]:
        """Tüm plugin'ler için güncelleme kontrolü"""

        updates = {}

        for plugin_name, info in self.installed_plugins.items():
            if not info["is_git"]:
                continue

            try:
                # Git repo'sunda güncellemeleri kontrol et
                subprocess.run(
                    ["git", "fetch", "origin"],
                    cwd=str(info["path"]),
                    check=True,
                    capture_output=True,
                )

                # Local ve remote version'ı karşılaştır
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(info["path"]),
                    capture_output=True,
                    text=True,
                )

                local_commit = result.stdout.strip()

                result = subprocess.run(
                    [
                        "git",
                        "rev-parse",
                        f'origin/{info["manifest"].get("branch", "main")}',
                    ],
                    cwd=str(info["path"]),
                    capture_output=True,
                    text=True,
                )

                remote_commit = result.stdout.strip()

                if local_commit != remote_commit:
                    # Güncelleme var
                    updates[plugin_name] = {
                        "current_version": info["version"],
                        "update_available": True,
                        "local_commit": local_commit[:8],
                        "remote_commit": remote_commit[:8],
                    }

            except Exception as e:
                logger.warning(f"Could not check updates for {plugin_name}: {e}")

        return updates
