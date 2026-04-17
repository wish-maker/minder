"""
Plugin Store Security Module
Malware scanning, author verification, and security policies
"""

import logging
import os
import re
from enum import Enum
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security policy levels"""

    PERMISSIVE = "permissive"
    MODERATE = "moderate"
    STRICT = "strict"
    PARANOID = "paranoid"


class PluginSecurityPolicy:
    """Security policy for plugin installation"""

    def __init__(
        self,
        security_level: SecurityLevel = SecurityLevel.MODERATE,
        trusted_authors: Optional[Set[str]] = None,
        blocked_authors: Optional[Set[str]] = None,
        require_signature: bool = False,
        max_plugin_size: int = 10 * 1024 * 1024,
    ):
        self.security_level = security_level
        self.trusted_authors = trusted_authors or set()
        self.blocked_authors = blocked_authors or set()
        self.require_signature = require_signature
        self.max_plugin_size = max_plugin_size
        self._load_from_env()

    def _load_from_env(self):
        """Load security policy from environment variables"""
        level = os.getenv("PLUGIN_SECURITY_LEVEL", "moderate").lower()
        try:
            self.security_level = SecurityLevel(level)
        except ValueError:
            logger.warning(f"Invalid security level: {level}, using moderate")
            self.security_level = SecurityLevel.MODERATE

        trusted = os.getenv("PLUGIN_TRUSTED_AUTHORS", "")
        if trusted:
            self.trusted_authors.update(auth.strip() for auth in trusted.split(","))

        blocked = os.getenv("PLUGIN_BLOCKED_AUTHORS", "")
        if blocked:
            self.blocked_authors.update(auth.strip() for auth in blocked.split(","))

        self.require_signature = os.getenv("PLUGIN_REQUIRE_SIGNATURE", "false").lower() == "true"

        max_size = os.getenv("PLUGIN_MAX_SIZE_MB", "10")
        try:
            self.max_plugin_size = int(max_size) * 1024 * 1024
        except ValueError:
            logger.warning(f"Invalid max size: {max_size}MB, using 10MB")
            self.max_plugin_size = 10 * 1024 * 1024

        logger.info(f"✅ Plugin security policy: {self.security_level.value}")
        logger.info(f"   - Trusted authors: {len(self.trusted_authors)}")
        logger.info(f"   - Blocked authors: {len(self.blocked_authors)}")


class MalwareScanner:
    """Scan plugin code for malicious patterns"""

    DANGEROUS_PATTERNS = {
        "command_injection": [
            r"os\.system\s*\(",
            r"subprocess\.call\s*\(",
            r"eval\s*\(",
            r"exec\s*\(",
        ],
        "data_exfiltration": [
            r"urllib\.request\.urlopen\s*\(",
            r"requests\.(get|post)\s*\(",
            r"socket\.socket\s*\(",
        ],
        "file_manipulation": [
            r"shutil\.rmtree\s*\(",
            r"os\.remove\s*\(",
        ],
    }

    SUSPICIOUS_IMPORTS = {
        "network": ["socket", "httplib", "urllib", "requests"],
        "system": ["os", "subprocess", "pty"],
    }

    def __init__(self, security_policy):
        self.policy = security_policy

    def scan_plugin_code(self, code: str, plugin_name: str) -> tuple[bool, List[str]]:
        """Scan plugin code for malicious patterns"""
        issues = []

        for category, patterns in self.DANGEROUS_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, code, re.IGNORECASE):
                    issues.append(f"Dangerous {category} pattern")
                    logger.warning(f"Malware scan [{plugin_name}]: {category}")

        for category, modules in self.SUSPICIOUS_IMPORTS.items():
            for module in modules:
                if re.search(rf"import\s+{module}\b", code, re.IGNORECASE):
                    issues.append(f"Suspicious {category} import: {module}")

        is_safe = len(issues) == 0
        return is_safe, issues


class AuthorVerifier:
    """Verify plugin authors"""

    def __init__(self, security_policy):
        self.policy = security_policy

    def verify_author(self, author: str, plugin_name: str) -> tuple[bool, Optional[str]]:
        """Verify if author is allowed"""
        if author.lower() in (a.lower() for a in self.policy.blocked_authors):
            return False, f"Author '{author}' is blocked"

        if self.policy.security_level in [
            SecurityLevel.STRICT,
            SecurityLevel.PARANOID,
        ]:
            if author.lower() not in (a.lower() for a in self.policy.trusted_authors):
                return False, f"Author '{author}' not in trusted list"

        return True, None


class PluginSecurityValidator:
    """Main security validator"""

    def __init__(self, security_policy=None):
        self.policy = security_policy or PluginSecurityPolicy()
        self.malware_scanner = MalwareScanner(self.policy)
        self.author_verifier = AuthorVerifier(self.policy)

    def validate_plugin(self, plugin_path: Path, plugin_name: str, author: str) -> tuple[bool, List[str]]:
        """Validate plugin before installation"""
        errors = []

        author_allowed, author_reason = self.author_verifier.verify_author(author, plugin_name)
        if not author_allowed:
            errors.append(author_reason)

        try:
            safe, issues = self.malware_scanner.scan_plugin_files(plugin_path, plugin_name)
            if not safe:
                errors.extend(issues)
        except Exception as e:
            logger.warning(f"Could not scan plugin {plugin_name}: {e}")

        is_valid = len(errors) == 0
        return is_valid, errors


def get_default_security_validator() -> PluginSecurityValidator:
    """Get default security validator"""
    policy = PluginSecurityPolicy()
    return PluginSecurityValidator(policy)
