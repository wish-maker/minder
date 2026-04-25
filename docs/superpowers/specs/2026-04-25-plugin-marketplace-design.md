# Minder Plugin Marketplace & AI Tools System - Design Specification

**Date:** 2026-04-25
**Status:** Approved
**Approach:** Dedicated Marketplace Microservice (Approach 2)
**MVP Scope:** Complete (Marketplace API + Licensing + Developer Portal + Admin UI)

---

## Executive Summary

Build a comprehensive plugin marketplace system for Minder that enables:
- Plugin discovery and installation (Grafana-style marketplace)
- Tier-based pricing (free/paid/freemium)
- AI tools per plugin (tier-gated)
- Enable/disable plugin management
- Developer portal for plugin submission
- Complete end-to-end plugin lifecycle management

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     Minder Marketplace System                  │
│                                                                 │
│  ┌──────────────────┐      ┌──────────────────┐               │
│  │   Admin Panel    │      │  Developer Portal│               │
│  │   (Grafana)      │      │   (Web App)      │               │
│  └────────┬─────────┘      └────────┬─────────┘               │
│           │                          │                         │
│           └──────────┬───────────────┘                         │
│                      ▼                                         │
│           ┌──────────────────────┐                            │
│           │  Marketplace API     │                            │
│           │  (FastAPI Service)   │                            │
│           │  Port: 8002          │                            │
│           └──────────┬───────────┘                            │
│                      │                                         │
│      ┌───────────────┼───────────────┐                        │
│      ▼               ▼               ▼                        │
│ ┌──────────┐  ┌──────────┐  ┌──────────┐                    │
│ │PostgreSQL│  │  Redis   │  │   S3     │                    │
│ │Market DB │  │  Cache   │  │Packages  │                    │
│ └──────────┘  └──────────┘  └──────────┘                    │
│                      │                                         │
│                      ▼                                         │
│           ┌──────────────────────┐                            │
│           │  Plugin Registry     │                            │
│           │  (Existing Service)  │                            │
│           │  Port: 8001          │                            │
│           └──────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

### Service Communication

- **Marketplace API** → Plugin Registry: Install/uninstall plugins
- **Plugin Registry** → Marketplace: Verify licenses, get tier config
- **Admin Panel** → Marketplace API: CRUD operations
- **Developer Portal** → Marketplace API: Plugin submission, analytics

---

## Database Schema

### Core Tables

#### `marketplace_plugins`
Plugin metadata and marketplace information.

#### `marketplace_plugin_versions`
Version management and package tracking.

#### `marketplace_plugin_tiers`
Tier definitions with pricing and features.

#### `marketplace_licenses`
User license management and validation.

#### `marketplace_installations`
Per-user plugin installation state.

#### `marketplace_ai_tools`
Central AI tools registry with tier requirements.

**Full SQL schema available in implementation plan.**

---

## API Endpoints

### Plugin Discovery
- `GET /v1/marketplace/plugins` - List all plugins
- `GET /v1/marketplace/plugins/{id}` - Plugin details
- `GET /v1/marketplace/plugins/search` - Search plugins
- `GET /v1/marketplace/plugins/featured` - Featured plugins

### Plugin Management
- `POST /v1/marketplace/plugins/{id}/install` - Install plugin
- `DELETE /v1/marketplace/plugins/{id}/uninstall` - Uninstall plugin
- `POST /v1/marketplace/plugins/{id}/enable` - Enable plugin
- `POST /v1/marketplace/plugins/{id}/disable` - Disable plugin

### AI Tools
- `GET /v1/marketplace/ai/tools` - List all AI tools
- `GET /v1/marketplace/plugins/{id}/tools` - Plugin's AI tools
- `GET /v1/marketplace/ai/tools/{tool_name}` - Tool details

### Licensing
- `POST /v1/marketplace/licenses/validate` - Validate license
- `POST /v1/marketplace/licenses/activate` - Activate license
- `GET /v1/marketplace/licenses` - User's licenses

### Developer Portal
- `POST /v1/marketplace/developer/plugins` - Submit plugin
- `PUT /v1/marketplace/developer/plugins/{id}` - Update plugin
- `GET /v1/marketplace/developer/analytics` - Developer analytics

---

## AI Tools Integration

### Plugin Manifest V2 with AI Tools

```yaml
# src/plugins/crypto/manifest.yml
name: crypto
version: 2.0.0

# Marketplace configuration
marketplace:
  display_name: "Crypto Analyst Pro"
  pricing_model: freemium
  
  tiers:
    community:
      price: 0
      ai_tools: [get_crypto_price]
      
    professional:
      price: 2900  # $29/month
      ai_tools: [get_crypto_price, advanced_crypto_analysis]

# AI tools definitions
ai_tools:
  - name: get_crypto_price
    description: Get current cryptocurrency price
    tier: community
    type: analysis
    endpoint: /ai/price
    method: GET
    parameters:
      symbol:
        type: string
        required: true
        enum: [BTC, ETH, SOL]
    response_format:
      price: float
      market_cap: float
      change_24h: float
      
  - name: advanced_crypto_analysis
    description: Advanced technical analysis
    tier: professional  # Requires paid tier
    type: analysis
    endpoint: /ai/technical-analysis
    method: POST
    parameters:
      symbol: {type: string, required: true}
      indicators: {type: array, items: [RSI, MACD, BB]}
    response_format:
      analysis: object
      signals: array
      confidence: float
```

### Dynamic AI Tools Discovery

```python
# services/plugin-registry/routes/ai_tools.py

@router.get("/v1/plugins/ai/tools")
async def get_all_ai_tools(
    user_tier: str = Depends(get_user_tier)
):
    """Get all AI tools available to user based on tier"""
    tools = []

    # Get all installed plugins
    plugins = await plugin_manager.list_installed()

    for plugin in plugins:
        # Load plugin manifest
        manifest = await load_plugin_manifest(plugin.name)

        # Filter tools by user's tier
        for tool in manifest.get("ai_tools", []):
            if tool.get("tier") == user_tier or tool.get("tier") == "community":
                tools.append({
                    "name": tool["name"],
                    "plugin": plugin.name,
                    "description": tool["description"],
                    "type": tool["type"],
                    "endpoint": f"/v1/plugins/{plugin.name}{tool['endpoint']}",
                    "method": tool["method"],
                    "parameters": tool["parameters"],
                    "tier": tool.get("tier", "community")
                })

    return {"tools": tools}
```

---

## Plugin Manifest V2 Schema

### Enhanced Manifest Structure

```yaml
# Required fields
name: string
version: string (semver)
description: string
author: string

# Marketplace info (NEW)
marketplace:
  display_name: string
  categories: [string]
  tags: [string]
  pricing_model: enum(free, paid, freemium)
  
  tiers:
    tier_name:
      price: integer (cents)
      features: [string]
      limitations: object
      ai_tools: [string] or "all"

# AI tools (NEW - expanded)
ai_tools:
  - name: string
    description: string
    tier: enum(community, professional, enterprise)
    type: enum(analysis, action, query)
    endpoint: string
    method: enum(GET, POST)
    parameters:
      param_name:
        type: enum(string, integer, array)
        required: boolean
        enum: [values]
        default: any
    response_format: object

# Existing fields (preserved)
dependencies: {...}
capabilities: [...]
permissions: {...}
```

---

## Tier-Based Access Control

### License Validation Flow

```python
# services/marketplace/core/licensing.py

class LicenseValidator:
    async def validate_plugin_access(
        self,
        user_id: str,
        plugin_name: str,
        required_feature: str = None
    ) -> Tuple[bool, str]:
        """
        Validate if user can access plugin feature
        
        Returns: (allowed, tier)
        """
        # 1. Get plugin installation
        installation = await self.db.get_installation(user_id, plugin_name)
        if not installation or not installation.enabled:
            return False, "not_installed"

        # 2. Check if plugin is free
        plugin = await self.marketplace.get_plugin(plugin_name)
        if plugin.pricing_model == "free":
            return True, "community"

        # 3. Validate license for paid plugins
        license = await self.db.get_active_license(user_id, plugin_name)
        if not license:
            return False, "no_license"

        # 4. Check license expiration
        if license.valid_until < datetime.now():
            return False, "license_expired"

        # 5. Check tier requirements
        if required_feature:
            tier_config = plugin.tiers[license.tier]
            if required_feature not in tier_config.features:
                return False, f"requires_{tier_config.next_tier}"

        return True, license.tier

    async def get_available_ai_tools(
        self,
        user_id: str,
        plugin_name: str
    ) -> List[Dict]:
        """Get AI tools available to user for specific plugin"""
        allowed, tier = await self.validate_plugin_access(user_id, plugin_name)
        if not allowed:
            return []

        # Get plugin manifest
        manifest = await self.plugin_registry.get_manifest(plugin_name)

        # Filter tools by tier
        available_tools = []
        for tool in manifest.get("ai_tools", []):
            tool_tier = tool.get("tier", "community")
            
            # User can access if their tier >= tool tier
            if self._tier_matches(tier, tool_tier):
                available_tools.append(tool)

        return available_tools
```

### Tier Hierarchy

```python
TIER_HIERARCHY = {
    "community": 1,
    "professional": 2,
    "enterprise": 3
}

def tier_matches(user_tier: str, required_tier: str) -> bool:
    """Check if user's tier has access to required tier"""
    return TIER_HIERARCHY[user_tier] >= TIER_HIERARCHY[required_tier]
```

---

## Plugin Distribution Models

### Hybrid Distribution (Git + Docker)

```python
# services/marketplace/core/distribution.py

class PluginDistributor:
    async def install_plugin(
        self,
        plugin_id: str,
        user_id: str
    ) -> Dict:
        """Install plugin using appropriate distribution method"""
        plugin = await self.marketplace.get_plugin(plugin_id)

        # Route to appropriate installer
        if plugin.distribution_type == "git":
            return await self._install_from_git(plugin, user_id)
        elif plugin.distribution_type == "docker":
            return await self._install_from_docker(plugin, user_id)
        elif plugin.distribution_type == "hybrid":
            # Core plugins use Git, third-party use Docker
            if plugin.is_core_plugin:
                return await self._install_from_git(plugin, user_id)
            else:
                return await self._install_from_docker(plugin, user_id)

    async def _install_from_git(self, plugin, user_id: str):
        """Install plugin from Git repository"""
        # 1. Clone repository
        repo_path = f"/tmp/plugins/{plugin.name}"
        await run_git_clone(plugin.repository_url, repo_path)

        # 2. Validate manifest
        manifest = await self._validate_manifest(repo_path)

        # 3. Call Plugin Registry to load
        result = await self.plugin_registry.load_plugin(
            plugin_name=plugin.name,
            source_path=repo_path
        )

        # 4. Record installation
        await self.db.create_installation(user_id, plugin.id, manifest.version)

        return result

    async def _install_from_docker(self, plugin, user_id: str):
        """Install plugin from Docker image"""
        # 1. Pull Docker image
        await run_docker_pull(plugin.docker_image)

        # 2. Deploy container
        container = await run_docker_container(
            image=plugin.docker_image,
            name=f"minder-plugin-{plugin.name}",
            env=await self._build_plugin_env(plugin, user_id)
        )

        # 3. Register with Plugin Registry
        await self.plugin_registry.register_container_plugin(
            plugin_name=plugin.name,
            container_url=f"http://{container.name}:8080"
        )

        # 4. Record installation
        await self.db.create_installation(user_id, plugin.id, "latest")

        return {"status": "installed", "container_id": container.id}
```

---

## Enable/Disable Plugin Management

### Plugin State Management

```python
# services/plugin-registry/routes/plugin_management.py

@router.post("/v1/plugins/{plugin_name}/enable")
async def enable_plugin(
    plugin_name: str,
    current_user = Depends(get_current_user)
):
    """Enable a plugin for current user"""
    # 1. Check if plugin is installed
    installation = await db.get_installation(current_user.id, plugin_name)
    if not installation:
        raise HTTPException(404, "Plugin not installed")

    # 2. Validate license if paid plugin
    if installation.pricing_model != "free":
        license = await marketplace.validate_license(
            current_user.id, plugin_name
        )
        if not license.valid:
            raise HTTPException(403, "License required")

    # 3. Enable plugin
    await db.update_installation(
        current_user.id, plugin_name, enabled=True
    )

    # 4. Load plugin if not loaded
    if plugin_name not in plugin_manager.loaded_plugins:
        await plugin_manager.load_plugin(plugin_name)

    return {"status": "enabled", "plugin": plugin_name}

@router.post("/v1/plugins/{plugin_name}/disable")
async def disable_plugin(
    plugin_name: str,
    current_user = Depends(get_current_user)
):
    """Disable a plugin for current user"""
    # 1. Get installation
    installation = await db.get_installation(current_user.id, plugin_name)
    if not installation:
        raise HTTPException(404, "Plugin not installed")

    # 2. Disable plugin
    await db.update_installation(
        current_user.id, plugin_name, enabled=False
    )

    # 3. Unload plugin from memory
    if plugin_name in plugin_manager.loaded_plugins:
        await plugin_manager.unload_plugin(plugin_name)

    return {"status": "disabled", "plugin": plugin_name}
```

---

## Default Plugins Configuration

### Core Plugins (Enabled by Default)

```yaml
# config/default_plugins.yml
core_plugins:
  crypto:
    enabled: true
    tier: community
    auto_update: true
    
  news:
    enabled: true
    tier: community
    auto_update: true
    
  network:
    enabled: true
    tier: community
    auto_update: true
    
  weather:
    enabled: true
    tier: community
    auto_update: true
    
  tefas:
    enabled: true
    tier: community
    auto_update: true
```

### Plugin Initialization

```python
# services/plugin-registry/init.py

async def initialize_default_plugins():
    """Initialize default plugins on system startup"""
    config = load_config("config/default_plugins.yml")

    for plugin_name, settings in config.core_plugins.items():
        # Install if not installed
        installation = await db.get_installation("system", plugin_name)
        if not installation:
            await marketplace.install_plugin(plugin_name, user_id="system")

        # Enable if configured
        if settings.enabled:
            await plugin_manager.load_plugin(plugin_name)
            await db.update_installation(
                "system", plugin_name, enabled=True
            )
```

---

## Admin UI (Grafana Dashboard)

### Dashboard Panels

1. **Available Plugins Table**
   - Columns: Name, Version, Pricing Model, Rating, Downloads, Install Button
   - Filters: Category, Price (Free/Paid), Tier
   - Search: By name, description, tags

2. **My Plugins Table**
   - Columns: Name, Status, Tier, Enabled, AI Tools Count, Configure Button
   - Actions: Enable/Disable, Uninstall, Upgrade Tier

3. **AI Tools Registry**
   - Columns: Tool Name, Plugin, Tier Required, Type, Endpoint, Status
   - Filters: Type, Tier, Plugin
   - Search: By tool name, description

4. **License Management**
   - Columns: Plugin, Tier, Valid Until, Status, Actions
   - Actions: Renew, Upgrade, Cancel

5. **Developer Analytics**
   - Downloads over time (chart)
   - Revenue by tier (chart)
   - Active installations (stat)
   - Top plugins (table)

---

## Developer Portal Features

### Plugin Submission

```python
# services/marketplace/routes/developer.py

@router.post("/v1/marketplace/developer/plugins")
async def submit_plugin(
    submission: PluginSubmission,
    developer: Developer = Depends(get_current_developer)
):
    """Submit new plugin to marketplace"""
    # 1. Validate manifest
    manifest = await validate_manifest(submission.manifest_url)

    # 2. Create plugin record
    plugin = await db.create_plugin(
        name=manifest.name,
        developer_id=developer.id,
        manifest=manifest,
        status="pending"  # Requires approval
    )

    # 3. Notify reviewers
    await notification_service.notify_reviewers(plugin.id)

    # 4. Return submission confirmation
    return {
        "plugin_id": plugin.id,
        "status": "pending_approval",
        "message": "Plugin submitted for review"
    }
```

### Version Management

```python
@router.post("/v1/marketplace/developer/plugins/{plugin_id}/versions")
async def release_version(
    plugin_id: str,
    version: PluginVersion,
    developer: Developer = Depends(get_current_developer)
):
    """Release new version of plugin"""
    # 1. Verify ownership
    if not await verify_ownership(developer.id, plugin_id):
        raise HTTPException(403, "Not your plugin")

    # 2. Validate package
    await validate_package(version.package_url)

    # 3. Create version record
    await db.create_version(
        plugin_id=plugin_id,
        version=version.version,
        manifest=version.manifest,
        package_url=version.package_url
    )

    # 4. Update current version
    await db.update_current_version(plugin_id, version.version)

    return {"status": "published", "version": version.version}
```

### Analytics Dashboard

```python
@router.get("/v1/marketplace/developer/analytics")
async def get_analytics(
    developer: Developer = Depends(get_current_developer)
):
    """Get analytics for developer's plugins"""
    plugins = await db.get_developer_plugins(developer.id)

    analytics = []
    for plugin in plugins:
        stats = await db.get_plugin_stats(plugin.id)
        analytics.append({
            "plugin": plugin.name,
            "downloads": stats.downloads,
            "active_installations": stats.active_installations,
            "revenue": stats.revenue,
            "rating": stats.rating,
            "reviews": stats.reviews,
            "tier_breakdown": stats.tier_breakdown
        })

    return {"analytics": analytics}
```

---

## Security Considerations

### License Key Generation

```python
# services/marketplace/core/license_generator.py

import hashlib
import secrets
import base64

class LicenseGenerator:
    def generate_license_key(
        self,
        user_id: str,
        plugin_id: str,
        tier: str
    ) -> str:
        """Generate secure license key"""
        # 1. Create license payload
        payload = f"{user_id}:{plugin_id}:{tier}:{int(time.time())}"

        # 2. Generate signature
        secret = settings.LICENSE_SECRET
        signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).digest()

        # 3. Combine payload + signature
        license_data = f"{payload}:{base64.b64encode(signature).decode()}"

        # 4. Encode as license key (format: XXXX-XXXX-XXXX-XXXX)
        license_key = self._encode_license_key(license_data)

        return license_key

    def validate_license_key(self, license_key: str) -> Dict:
        """Validate license key and return payload"""
        # 1. Decode license key
        license_data = self._decode_license_key(license_key)

        # 2. Split payload and signature
        try:
            payload, signature_b64 = license_data.split(":")
            signature = base64.b64decode(signature_b64)
        except ValueError:
            return {"valid": False, "reason": "invalid_format"}

        # 3. Verify signature
        secret = settings.LICENSE_SECRET
        expected_signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).digest()

        if not hmac.compare_digest(signature, expected_signature):
            return {"valid": False, "reason": "invalid_signature"}

        # 4. Parse payload
        try:
            user_id, plugin_id, tier, timestamp = payload.split(":")
            return {
                "valid": True,
                "user_id": user_id,
                "plugin_id": plugin_id,
                "tier": tier,
                "issued_at": int(timestamp)
            }
        except ValueError:
            return {"valid": False, "reason": "invalid_payload"}
```

### Plugin Sandboxing

```python
# services/plugin-registry/core/sandbox.py

class PluginSandbox:
    async def execute_plugin_tool(
        self,
        plugin_name: str,
        tool_name: str,
        parameters: Dict
    ):
        """Execute AI tool in sandboxed environment"""
        # 1. Get plugin security profile
        profile = await self.get_security_profile(plugin_name)

        # 2. Validate permissions
        if not profile.permissions.allows_tool(tool_name):
            raise PermissionError("Tool not allowed")

        # 3. Execute in sandbox
        async with self.sandbox_context(profile) as sandbox:
            result = await sandbox.execute_tool(tool_name, parameters)

        # 4. Validate output
        return self.sanitize_output(result, profile)
```

---

## Testing Strategy

### Unit Tests
- License validation logic
- Tier matching algorithm
- Plugin manifest validation
- AI tools discovery

### Integration Tests
- Plugin installation flow (Git & Docker)
- License activation flow
- Enable/disable plugin flow
- AI tools execution with tier restrictions

### End-to-End Tests
- Complete marketplace workflow
- Developer submission flow
- Multi-tier plugin usage
- License expiration scenarios

---

## Migration Path

### Phase 1: Core Infrastructure (Week 1-2)
- Create marketplace database schema
- Implement Marketplace API service
- Build Plugin Registry integration

### Phase 2: Licensing System (Week 3-4)
- Implement license generation/validation
- Build tier-based access control
- Create license management endpoints

### Phase 3: AI Tools Integration (Week 5-6)
- Extend plugin manifest schema
- Implement dynamic AI tools discovery
- Build tier-gated tool execution

### Phase 4: Developer Portal (Week 7-8)
- Implement plugin submission flow
- Build version management
- Create analytics dashboard

### Phase 5: Admin UI (Week 9)
- Integrate with Grafana
- Build marketplace panels
- Create license management UI

---

## Success Criteria

✅ Plugins can be discovered and installed via API
✅ Tier-based pricing works (free/paid/freemium)
✅ AI tools are dynamically discovered and tier-gated
✅ Plugins can be enabled/disabled per user
✅ Licenses are validated and enforced
✅ Developers can submit plugins and track analytics
✅ Admin UI provides complete marketplace management
✅ System is secure (license keys, sandboxing)
✅ All existing plugins continue to work

---

## Next Steps

1. **Create Implementation Plan** - Detailed task breakdown
2. **Set up Development Environment** - Marketplace service infrastructure
3. **Implement Core API** - Database + endpoints
4. **Integrate with Plugin Registry** - License validation
5. **Build Admin UI** - Grafana dashboard panels
6. **Test End-to-End** - Complete marketplace workflow
7. **Documentation** - User and developer guides

---

**Status:** Ready for Implementation Planning
**Estimated Timeline:** 9 weeks
**Team Size:** 1-2 developers
