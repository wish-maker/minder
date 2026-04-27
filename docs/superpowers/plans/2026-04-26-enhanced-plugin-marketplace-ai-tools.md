# Enhanced Plugin Marketplace & AI Tools System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete plugin marketplace system with tier-based pricing, AI tools integration, dynamic tool configuration, enable/disable management, and developer portal.

**Architecture:** Enhanced Marketplace microservice with PostgreSQL database, Redis cache, integration with existing Plugin Registry service, and advanced AI tools management.

**Tech Stack:** FastAPI, PostgreSQL, Redis, Docker, Pydantic, pytest, httpx, Grafana

**Key Enhancements from Original Plan:**
1. **AI Tools Management**: Plugin-level AI tools with dynamic configuration
2. **Tier-based Access Control**: Granular access control for AI tools
3. **Tool Enable/Disable**: Individual tool management within plugins
4. **Enhanced Modularity**: Plugin-based extensibility for AI tools
5. **Marketplace Integration**: Grafana-like plugin store experience

---

## File Structure

### New Files

```
services/marketplace/
├── main.py                          # FastAPI application
├── config.py                        # Settings and environment
├── requirements.txt                 # Dependencies
├── Dockerfile                       # Container definition
├── core/
│   ├── __init__.py
│   ├── database.py                  # Database connection pool
│   ├── licensing.py                 # License generation/validation
│   ├── distribution.py              # Plugin installation (Git/Docker)
│   ├── security.py                  # License key generation
│   └── ai_tools_manager.py          # AI tools lifecycle management ⭐ NEW
├── models/
│   ├── __init__.py
│   ├── plugin.py                    # Plugin data models
│   ├── license.py                   # License data models
│   ├── installation.py              # Installation data models
│   └── ai_tools.py                  # AI tools data models ⭐ NEW
├── routes/
│   ├── __init__.py
│   ├── marketplace.py               # Plugin discovery endpoints
│   ├── management.py                # Install/uninstall/enable/disable
│   ├── ai_tools.py                  # AI tools registry & management ⭐ ENHANCED
│   ├── licensing.py                 # License validation
│   └── developer.py                 # Developer portal
├── tests/
│   ├── __init__.py
│   ├── test_marketplace_api.py
│   ├── test_licensing.py
│   ├── test_distribution.py
│   └── test_ai_tools_management.py  # AI tools tests ⭐ NEW
└── migrations/
    ├── 001_initial_schema.sql       # Database schema
    └── 002_ai_tools_enhancements.sql # AI tools enhancements ⭐ NEW

infrastructure/docker/
├── docker-compose.marketplace.yml   # Marketplace service
└── .env.marketplace.example         # Environment variables

src/core/
├── manifest_schema_v3.py            # Enhanced manifest with AI tools ⭐ UPGRADED
├── tier_manager.py                  # Tier-based access control ⭐ ENHANCED
└── ai_tools_config.py               # AI tools configuration manager ⭐ NEW

src/shared/ai/
├── tool_registry.py                 # Central AI tools registry ⭐ ENHANCED
├── tier_validator.py                # Tier validation for AI tools ⭐ ENHANCED
└── tool_lifecycle.py                # Tool enable/disable manager ⭐ NEW

src/plugins/
└── [all plugins]/
    └── manifest.yml                 # Enhanced with ai_tools_config ⭐ ENHANCED

tests/integration/
├── test_marketplace_integration.py  # End-to-end tests
└── test_ai_tools_integration.py     # AI tools integration tests ⭐ NEW

docs/
├── MARKETPLACE_USER_GUIDE.md        # User documentation
├── MARKETPLACE_DEVELOPER_GUIDE.md   # Developer documentation
├── MARKETPLACE_API_REFERENCE.md     # API documentation
└── AI_TOOLS_GUIDE.md                # AI tools configuration guide ⭐ NEW
```

---

## Phase 1: Enhanced Core Infrastructure (Week 1-2)

### Task 1: Enhanced Database Schema with AI Tools

**Files:**
- Create: `services/marketplace/migrations/002_ai_tools_enhancements.sql`
- Test: `services/marketplace/tests/test_ai_tools_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# services/marketplace/tests/test_ai_tools_schema.py
import asyncpg
from pathlib import Path

async def test_ai_tools_enhanced_schema():
    """Test that AI tools enhancements are applied correctly"""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="minder",
        password="dev_password_change_me",
        database="minder_marketplace"
    )
    
    # Check new AI tools tables exist
    tables = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        AND table_name LIKE 'ai_%'
        ORDER BY table_name
    """)
    
    table_names = [row['table_name'] for row in tables]
    
    # New AI tools tables
    assert 'marketplace_ai_tools_configurations' in table_names
    assert 'marketplace_ai_tools_registrations' in table_names
    assert 'marketplace_plugin_ai_tools' in table_names
    
    # Check indexes
    indexes = await conn.fetch("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE schemaname = 'public'
        AND indexname LIKE 'ai_%'
        ORDER BY indexname
    """)
    
    index_names = [row['indexname'] for row in indexes]
    assert len(index_names) > 0
    
    # Check new columns
    columns = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'marketplace_ai_tools'
        ORDER BY column_name
    """)
    
    column_names = [row['column_name'] for row in columns]
    
    # Enhanced columns
    assert 'configuration_schema' in column_names
    assert 'default_configuration' in column_names
    assert 'is_enabled' in column_names
    assert 'required_tier' in column_names
    
    await conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/minder && python -m pytest services/marketplace/tests/test_ai_tools_schema.py::test_ai_tools_enhanced_schema -v`

Expected: FAIL with "relation "marketplace_ai_tools_configurations" does not exist"

- [ ] **Step 3: Create enhanced AI tools schema**

```sql
-- services/marketplace/migrations/002_ai_tools_enhancements.sql

-- AI Tools Configuration Storage
CREATE TABLE marketplace_ai_tools_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    
    -- Configuration Schema
    configuration_schema JSONB NOT NULL, -- Schema for tool configuration
    default_configuration JSONB NOT NULL, -- Default values
    
    -- Validation
    required_parameters JSONB, -- Parameters that must be configured
    optional_parameters JSONB, -- Optional parameters
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(plugin_id, tool_name)
);

-- AI Tools Registrations (plugin tool instances)
CREATE TABLE marketplace_ai_tools_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    installation_id UUID REFERENCES marketplace_installations(id) ON DELETE CASCADE,
    
    -- Instance Configuration
    configuration JSONB NOT NULL, -- Actual configuration for this instance
    
    -- State Management
    is_enabled BOOLEAN DEFAULT TRUE,
    activation_status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'active', 'inactive', 'error'
    
    -- Validation
    last_validated_at TIMESTAMP,
    validation_status VARCHAR(20), -- 'valid', 'invalid', 'pending'
    validation_errors JSONB,
    
    -- Usage Tracking
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    
    -- Timestamps
    registered_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(plugin_id, tool_name, installation_id)
);

-- Plugin AI Tools Relationship
CREATE TABLE marketplace_plugin_ai_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID REFERENCES marketplace_plugins(id) ON DELETE CASCADE,
    tool_id UUID REFERENCES marketplace_ai_tools(id) ON DELETE CASCADE,
    
    -- Tool Assignment
    is_default BOOLEAN DEFAULT FALSE, -- Included in default plugin installation
    required_tier VARCHAR(50) DEFAULT 'community', -- Tier required to use
    
    -- Configuration Override
    configuration_override JSONB, -- Plugin-specific configuration override
    
    -- State
    is_enabled BOOLEAN DEFAULT TRUE, -- Master enable/disable for this plugin-tool pair
    
    -- Priority
    display_order INTEGER DEFAULT 0, -- Order in tool listings
    
    UNIQUE(plugin_id, tool_id)
);

-- Add columns to existing marketplace_ai_tools table
ALTER TABLE marketplace_ai_tools
ADD COLUMN IF NOT EXISTS configuration_schema JSONB,
ADD COLUMN IF NOT EXISTS default_configuration JSONB,
ADD COLUMN IF NOT EXISTS is_enabled BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS required_tier VARCHAR(50) DEFAULT 'community',
ADD COLUMN IF NOT EXISTS category VARCHAR(50), -- 'analysis', 'action', 'query'
ADD COLUMN IF NOT EXISTS tags JSONB; -- For better discoverability

-- Create indexes for AI tools
CREATE INDEX idx_ai_tools_configurations_plugin ON marketplace_ai_tools_configurations(plugin_id);
CREATE INDEX idx_ai_tools_configurations_tool ON marketplace_ai_tools_configurations(tool_name);

CREATE INDEX idx_ai_tools_registrations_plugin ON marketplace_ai_tools_registrations(plugin_id);
CREATE INDEX idx_ai_tools_registrations_installation ON marketplace_ai_tools_registrations(installation_id);
CREATE INDEX idx_ai_tools_registrations_enabled ON marketplace_ai_tools_registrations(is_enabled) WHERE is_enabled = TRUE;
CREATE INDEX idx_ai_tools_registrations_status ON marketplace_ai_tools_registrations(activation_status);

CREATE INDEX idx_plugin_ai_tools_plugin ON marketplace_plugin_ai_tools(plugin_id);
CREATE INDEX idx_plugin_ai_tools_tool ON marketplace_plugin_ai_tools(tool_id);
CREATE INDEX idx_plugin_ai_tools_enabled ON marketplace_plugin_ai_tools(is_enabled) WHERE is_enabled = TRUE;

CREATE INDEX idx_ai_tools_tier ON marketplace_ai_tools(required_tier);
CREATE INDEX idx_ai_tools_category ON marketplace_ai_tools(category);
CREATE INDEX idx_ai_tools_enabled ON marketplace_ai_tools(is_enabled) WHERE is_enabled = TRUE;
```

- [ ] **Step 4: Apply schema to database**

Run: `cd /root/minder && docker exec -i minder-postgres psql -U minder -d minder_marketplace < services/marketplace/migrations/002_ai_tools_enhancements.sql`

Expected: Schema applied successfully

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /root/minder && python -m pytest services/marketplace/tests/test_ai_tools_schema.py::test_ai_tools_enhanced_schema -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/marketplace/migrations/002_ai_tools_enhancements.sql
git add services/marketplace/tests/test_ai_tools_schema.py
git commit -m "feat(marketplace): add enhanced AI tools schema with configuration"
```

---

### Task 2: Enhanced AI Tools Data Models

**Files:**
- Create: `services/marketplace/models/ai_tools.py`
- Test: `services/marketplace/tests/test_ai_tools_models.py`

- [ ] **Step 1: Write the failing test**

```python
# services/marketplace/tests/test_ai_tools_models.py
from datetime import datetime
from services.marketplace.models.ai_tools import (
    AIToolConfigurationCreate,
    AIToolRegistrationCreate,
    AIToolResponse,
    PluginAIToolAssignment
)

def test_ai_tool_configuration_model():
    """Test AI tool configuration model"""
    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {"type": "string"},
            "timeout": {"type": "integer", "default": 30}
        }
    }
    
    data = {
        "plugin_id": "test-plugin-id",
        "tool_name": "crypto_analyzer",
        "configuration_schema": config_schema,
        "default_configuration": {"timeout": 30}
    }
    
    config = AIToolConfigurationCreate(**data)
    
    assert config.tool_name == "crypto_analyzer"
    assert config.configuration_schema == config_schema

def test_ai_tool_registration_model():
    """Test AI tool registration model"""
    data = {
        "plugin_id": "test-plugin-id",
        "tool_name": "crypto_analyzer",
        "installation_id": "installation-id",
        "configuration": {"api_key": "test-key"}
    }
    
    registration = AIToolRegistrationCreate(**data)
    
    assert registration.tool_name == "crypto_analyzer"
    assert registration.configuration["api_key"] == "test-key"

def test_ai_tool_response_model():
    """Test AI tool response model"""
    data = {
        "id": "tool-id",
        "plugin_id": "plugin-id",
        "plugin_name": "crypto",
        "tool_name": "crypto_analyzer",
        "type": "analysis",
        "description": "Analyzes crypto markets",
        "endpoint": "/analyze",
        "method": "GET",
        "required_tier": "professional",
        "is_enabled": True,
        "category": "analysis"
    }
    
    tool = AIToolResponse(**data)
    
    assert tool.tool_name == "crypto_analyzer"
    assert tool.required_tier == "professional"
    assert tool.is_enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/minder && python -m pytest services/marketplace/tests/test_ai_tools_models.py::test_ai_tool_configuration_model -v`

Expected: FAIL with "module 'services.marketplace.models.ai_tools' not found"

- [ ] **Step 3: Create AI tools models**

```python
# services/marketplace/models/ai_tools.py
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class AIToolType(str, Enum):
    """AI tool types"""
    ANALYSIS = "analysis"
    ACTION = "action"
    QUERY = "query"


class AIToolCategory(str, Enum):
    """AI tool categories"""
    DATA = "data"
    ANALYSIS = "analysis"
    AUTOMATION = "automation"
    INTEGRATION = "integration"
    CUSTOM = "custom"


class ActivationStatus(str, Enum):
    """AI tool activation status"""
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class AIToolConfigurationCreate(BaseModel):
    """Model for creating AI tool configuration"""
    plugin_id: str
    tool_name: str = Field(..., min_length=1, max_length=100)
    configuration_schema: Dict[str, Any] = Field(..., description="JSON Schema for configuration")
    default_configuration: Dict[str, Any] = Field(..., description="Default configuration values")
    required_parameters: Optional[Dict[str, Any]] = None
    optional_parameters: Optional[Dict[str, Any]] = None


class AIToolConfigurationResponse(BaseModel):
    """Model for AI tool configuration response"""
    id: str
    plugin_id: str
    tool_name: str
    configuration_schema: Dict[str, Any]
    default_configuration: Dict[str, Any]
    required_parameters: Optional[Dict[str, Any]]
    optional_parameters: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class AIToolRegistrationCreate(BaseModel):
    """Model for creating AI tool registration"""
    plugin_id: str
    tool_name: str
    installation_id: str
    configuration: Dict[str, Any] = Field(default_factory=dict)


class AIToolRegistrationUpdate(BaseModel):
    """Model for updating AI tool registration"""
    configuration: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    activation_status: Optional[ActivationStatus] = None


class AIToolRegistrationResponse(BaseModel):
    """Model for AI tool registration response"""
    id: str
    plugin_id: str
    tool_name: str
    installation_id: str
    configuration: Dict[str, Any]
    is_enabled: bool
    activation_status: str
    last_validated_at: Optional[datetime]
    validation_status: Optional[str]
    validation_errors: Optional[Dict[str, Any]]
    usage_count: int
    last_used_at: Optional[datetime]
    registered_at: datetime
    updated_at: datetime


class AIToolResponse(BaseModel):
    """Model for AI tool response"""
    id: str
    plugin_id: str
    plugin_name: str
    tool_name: str
    type: str
    description: Optional[str]
    endpoint: str
    method: str
    parameters: Optional[Dict[str, Any]]
    response_format: Optional[Dict[str, Any]]
    required_tier: str
    is_enabled: bool
    category: Optional[str]
    tags: Optional[List[str]]
    
    class Config:
        from_attributes = True


class PluginAIToolAssignment(BaseModel):
    """Model for assigning AI tool to plugin"""
    tool_id: str
    is_default: bool = False
    required_tier: str = "community"
    configuration_override: Optional[Dict[str, Any]] = None
    is_enabled: bool = True
    display_order: int = 0


class AIToolListResponse(BaseModel):
    """Model for AI tool list response"""
    tools: List[AIToolResponse]
    count: int
    page: int
    page_size: int
    total_pages: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /root/minder && python -m pytest services/marketplace/tests/test_ai_tools_models.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/marketplace/models/ai_tools.py
git add services/marketplace/tests/test_ai_tools_models.py
git commit -m "feat(marketplace): add AI tools data models"
```

---

### Task 3: AI Tools Manager Service

**Files:**
- Create: `services/marketplace/core/ai_tools_manager.py`
- Test: `services/marketplace/tests/test_ai_tools_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# services/marketplace/tests/test_ai_tools_manager.py
import pytest
from services.marketplace.core.ai_tools_manager import AIToolsManager

@pytest.mark.asyncio
async def test_register_tool_configuration():
    """Test registering AI tool configuration"""
    manager = AIToolsManager()
    
    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {"type": "string"},
            "timeout": {"type": "integer", "default": 30}
        }
    }
    
    result = await manager.register_tool_configuration(
        plugin_id="test-plugin-id",
        tool_name="test-tool",
        configuration_schema=config_schema,
        default_configuration={"timeout": 30}
    )
    
    assert result["tool_name"] == "test-tool"
    assert result["configuration_schema"] == config_schema

@pytest.mark.asyncio
async def test_enable_tool_for_installation():
    """Test enabling tool for specific installation"""
    manager = AIToolsManager()
    
    result = await manager.enable_tool_for_installation(
        plugin_id="test-plugin-id",
        tool_name="test-tool",
        installation_id="installation-id",
        configuration={"api_key": "test-key"}
    )
    
    assert result["is_enabled"] is True
    assert result["activation_status"] == "active"

@pytest.mark.asyncio
async def test_disable_tool():
    """Test disabling a tool"""
    manager = AIToolsManager()
    
    result = await manager.disable_tool(
        plugin_id="test-plugin-id",
        tool_name="test-tool"
    )
    
    assert result["is_enabled"] is False

@pytest.mark.asyncio
async def test_validate_tool_configuration():
    """Test validating tool configuration"""
    manager = AIToolsManager()
    
    result = await manager.validate_tool_configuration(
        plugin_id="test-plugin-id",
        tool_name="test-tool",
        configuration={"api_key": "valid-key"}
    )
    
    assert result["is_valid"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/minder && python -m pytest services/marketplace/tests/test_ai_tools_manager.py::test_register_tool_configuration -v`

Expected: FAIL with "module 'services.marketplace.core.ai_tools_manager' not found"

- [ ] **Step 3: Create AI tools manager**

```python
# services/marketplace/core/ai_tools_manager.py
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from jsonschema import validate, ValidationError as JSONSchemaValidationError

from services.marketplace.core.database import get_pool
from services.marketplace.models.ai_tools import (
    AIToolConfigurationCreate,
    AIToolRegistrationCreate,
    AIToolResponse
)

logger = logging.getLogger("minder.marketplace.ai_tools")


class AIToolsManager:
    """Manage AI tools lifecycle"""
    
    async def register_tool_configuration(
        self,
        plugin_id: str,
        tool_name: str,
        configuration_schema: Dict[str, Any],
        default_configuration: Dict[str, Any],
        required_parameters: Optional[Dict[str, Any]] = None,
        optional_parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Register AI tool configuration schema
        
        Args:
            plugin_id: Plugin ID
            tool_name: Tool name
            configuration_schema: JSON Schema for configuration
            default_configuration: Default configuration values
            required_parameters: Required parameters
            optional_parameters: Optional parameters
            
        Returns:
            Created configuration
        """
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            # Check if configuration exists
            existing = await conn.fetchrow(
                """
                SELECT * FROM marketplace_ai_tools_configurations
                WHERE plugin_id = $1 AND tool_name = $2
                """,
                plugin_id, tool_name
            )
            
            if existing:
                # Update existing
                row = await conn.fetchrow(
                    """
                    UPDATE marketplace_ai_tools_configurations
                    SET configuration_schema = $3, default_configuration = $4,
                        required_parameters = $5, optional_parameters = $6, updated_at = NOW()
                    WHERE id = $7
                    RETURNING id, plugin_id, tool_name, configuration_schema, default_configuration
                    """,
                    configuration_schema, default_configuration, 
                    required_parameters, optional_parameters, existing["id"]
                )
            else:
                # Create new
                row = await conn.fetchrow(
                    """
                    INSERT INTO marketplace_ai_tools_configurations 
                    (plugin_id, tool_name, configuration_schema, default_configuration, 
                     required_parameters, optional_parameters)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id, plugin_id, tool_name, configuration_schema, default_configuration
                    """,
                    plugin_id, tool_name, configuration_schema, default_configuration,
                    required_parameters, optional_parameters
                )
            
            return {
                "id": str(row["id"]),
                "plugin_id": row["plugin_id"],
                "tool_name": row["tool_name"],
                "configuration_schema": row["configuration_schema"],
                "default_configuration": row["default_configuration"]
            }
    
    async def enable_tool_for_installation(
        self,
        plugin_id: str,
        tool_name: str,
        installation_id: str,
        configuration: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enable AI tool for specific installation
        
        Args:
            plugin_id: Plugin ID
            tool_name: Tool name
            installation_id: Installation ID
            configuration: Tool configuration
            
        Returns:
            Tool registration details
        """
        pool = await get_pool()
        
        # Get default configuration if not provided
        if configuration is None:
            async with pool.acquire() as conn:
                config_row = await conn.fetchrow(
                    """
                    SELECT default_configuration 
                    FROM marketplace_ai_tools_configurations
                    WHERE plugin_id = $1 AND tool_name = $2
                    """,
                    plugin_id, tool_name
                )
                
                if config_row:
                    configuration = config_row["default_configuration"]
                else:
                    configuration = {}
        
        async with pool.acquire() as conn:
            # Check if registration exists
            existing = await conn.fetchrow(
                """
                SELECT * FROM marketplace_ai_tools_registrations
                WHERE plugin_id = $1 AND tool_name = $2 AND installation_id = $3
                """,
                plugin_id, tool_name, installation_id
            )
            
            if existing:
                # Update existing
                row = await conn.fetchrow(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET configuration = $4, is_enabled = TRUE, activation_status = 'active',
                        updated_at = NOW()
                    WHERE id = $5
                    RETURNING id, plugin_id, tool_name, installation_id, configuration, 
                             is_enabled, activation_status
                    """,
                    configuration, existing["id"]
                )
            else:
                # Create new
                row = await conn.fetchrow(
                    """
                    INSERT INTO marketplace_ai_tools_registrations
                    (plugin_id, tool_name, installation_id, configuration, is_enabled, activation_status)
                    VALUES ($1, $2, $3, $4, TRUE, 'active')
                    RETURNING id, plugin_id, tool_name, installation_id, configuration,
                             is_enabled, activation_status
                    """,
                    plugin_id, tool_name, installation_id, configuration
                )
            
            return {
                "id": str(row["id"]),
                "plugin_id": row["plugin_id"],
                "tool_name": row["tool_name"],
                "installation_id": row["installation_id"],
                "configuration": row["configuration"],
                "is_enabled": row["is_enabled"],
                "activation_status": row["activation_status"]
            }
    
    async def disable_tool(
        self,
        plugin_id: str,
        tool_name: str,
        installation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Disable AI tool
        
        Args:
            plugin_id: Plugin ID
            tool_name: Tool name
            installation_id: Optional installation ID (if None, disable for all)
            
        Returns:
            Updated tool status
        """
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            if installation_id:
                # Disable for specific installation
                row = await conn.fetchrow(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET is_enabled = FALSE, activation_status = 'inactive', updated_at = NOW()
                    WHERE plugin_id = $1 AND tool_name = $2 AND installation_id = $3
                    RETURNING id, is_enabled, activation_status
                    """,
                    plugin_id, tool_name, installation_id
                )
            else:
                # Disable for all installations
                row = await conn.fetchrow(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET is_enabled = FALSE, activation_status = 'inactive', updated_at = NOW()
                    WHERE plugin_id = $1 AND tool_name = $2
                    RETURNING id, is_enabled, activation_status
                    """,
                    plugin_id, tool_name
                )
            
            if not row:
                raise ValueError(f"Tool registration not found: {plugin_id}/{tool_name}")
            
            return {
                "id": str(row["id"]),
                "is_enabled": row["is_enabled"],
                "activation_status": row["activation_status"]
            }
    
    async def validate_tool_configuration(
        self,
        plugin_id: str,
        tool_name: str,
        configuration: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate tool configuration against schema
        
        Args:
            plugin_id: Plugin ID
            tool_name: Tool name
            configuration: Configuration to validate
            
        Returns:
            Validation result
        """
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            # Get configuration schema
            row = await conn.fetchrow(
                """
                SELECT configuration_schema, required_parameters 
                FROM marketplace_ai_tools_configurations
                WHERE plugin_id = $1 AND tool_name = $2
                """,
                plugin_id, tool_name
            )
            
            if not row:
                return {
                    "is_valid": False,
                    "errors": ["Configuration schema not found"]
                }
            
            schema = row["configuration_schema"]
            required_params = row["required_parameters"] or {}
            
            # Validate against schema
            try:
                validate(instance=configuration, schema=schema)
                
                # Check required parameters
                missing_params = []
                for param_name, param_def in required_params.items():
                    if param_name not in configuration:
                        missing_params.append(param_name)
                
                if missing_params:
                    return {
                        "is_valid": False,
                        "errors": [f"Missing required parameters: {', '.join(missing_params)}"]
                    }
                
                # Update validation status in database
                await conn.execute(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET validation_status = 'valid', last_validated_at = NOW(),
                        validation_errors = NULL
                    WHERE plugin_id = $1 AND tool_name = $2
                    """,
                    plugin_id, tool_name
                )
                
                return {
                    "is_valid": True,
                    "errors": []
                }
                
            except JSONSchemaValidationError as e:
                errors = [str(e.message)]
                
                # Update validation status in database
                await conn.execute(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET validation_status = 'invalid', last_validated_at = NOW(),
                        validation_errors = $3
                    WHERE plugin_id = $1 AND tool_name = $2
                    """,
                    plugin_id, tool_name, json.dumps(errors)
                )
                
                return {
                    "is_valid": False,
                    "errors": errors
                }
    
    async def get_tools_for_plugin(
        self,
        plugin_id: str,
        include_disabled: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all tools for a plugin
        
        Args:
            plugin_id: Plugin ID
            include_disabled: Include disabled tools
            
        Returns:
            List of tools
        """
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            query = """
                SELECT 
                    at.id, at.plugin_id, at.tool_name, at.tool_type, at.description,
                    at.endpoint_path, at.http_method, at.parameters_schema, at.response_schema,
                    at.required_tier, at.is_enabled, at.category, at.tags,
                    p.name as plugin_name
                FROM marketplace_ai_tools at
                JOIN marketplace_plugins p ON at.plugin_id = p.id
                WHERE at.plugin_id = $1
            """
            
            if not include_disabled:
                query += " AND at.is_enabled = TRUE"
            
            query += " ORDER BY at.tool_name"
            
            rows = await conn.fetch(query, plugin_id)
            
            tools = []
            for row in rows:
                tools.append({
                    "id": str(row["id"]),
                    "plugin_id": str(row["plugin_id"]),
                    "plugin_name": row["plugin_name"],
                    "tool_name": row["tool_name"],
                    "type": row["tool_type"],
                    "description": row["description"],
                    "endpoint": row["endpoint_path"],
                    "method": row["http_method"],
                    "parameters": row["parameters_schema"],
                    "response_format": row["response_schema"],
                    "required_tier": row["required_tier"],
                    "is_enabled": row["is_enabled"],
                    "category": row["category"],
                    "tags": row["tags"]
                })
            
            return tools
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /root/minder && python -m pytest services/marketplace/tests/test_ai_tools_manager.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/marketplace/core/ai_tools_manager.py
git add services/marketplace/tests/test_ai_tools_manager.py
git commit -m "feat(marketplace): add AI tools manager service"
```

---

## Phase 2: Enhanced Plugin Manifest (Week 2-3)

### Task 4: Enhanced Manifest Schema V3

**Files:**
- Create: `src/core/manifest_schema_v3.py`
- Modify: `src/shared/ai/tool_validator.py` (enhance validation)
- Test: `tests/integration/test_manifest_v3_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_manifest_v3_integration.py
from pathlib import Path
from src.core.manifest_schema_v3 import validate_manifest_v3

def test_validate_ai_tools_configuration():
    """Test validating AI tools configuration in manifest"""
    manifest = {
        "name": "test-plugin",
        "version": "1.0.0",
        "ai_tools": [
            {
                "name": "analyzer",
                "description": "Analysis tool",
                "type": "analysis",
                "endpoint": "/analyze",
                "method": "GET",
                "configuration_schema": {
                    "type": "object",
                    "properties": {
                        "api_key": {"type": "string"},
                        "timeout": {"type": "integer", "default": 30}
                    }
                },
                "default_configuration": {"timeout": 30},
                "required_tier": "professional"
            }
        ]
    }
    
    result = validate_manifest_v3(manifest)
    
    assert result["valid"] is True
    assert "ai_tools" in result["validated_manifest"]
    assert len(result["validated_manifest"]["ai_tools"]) == 1

def test_validate_tool_enable_disable():
    """Test tool enable/disable configuration"""
    manifest = {
        "name": "test-plugin",
        "version": "1.0.0",
        "ai_tools_config": {
            "default_enabled": True,
            "tools": {
                "analyzer": {
                    "enabled": True,
                    "required_tier": "community"
                },
                "exporter": {
                    "enabled": False,
                    "required_tier": "professional"
                }
            }
        }
    }
    
    result = validate_manifest_v3(manifest)
    
    assert result["valid"] is True
    tools_config = result["validated_manifest"]["ai_tools_config"]
    assert tools_config["tools"]["analyzer"]["enabled"] is True
    assert tools_config["tools"]["exporter"]["enabled"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/minder && python -m pytest tests/integration/test_manifest_v3_integration.py::test_validate_ai_tools_configuration -v`

Expected: FAIL with "module 'src.core.manifest_schema_v3' not found"

- [ ] **Step 3: Create enhanced manifest schema**

```python
# src/core/manifest_schema_v3.py
"""
Enhanced Plugin Manifest Schema V3
Supports advanced AI tools configuration, tier-based access, and tool lifecycle management
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator
from jsonschema import validate, ValidationError as JSONSchemaValidationError

logger = logging.getLogger(__name__)


class ToolParameterSchema(BaseModel):
    """Tool parameter schema definition"""
    type: str = Field(..., description="Parameter type (string, integer, float, boolean, array, object)")
    description: str = Field(..., description="Parameter description")
    enum: Optional[List[str]] = Field(None, description="Allowed values for enum")
    default: Optional[Any] = Field(None, description="Default value")
    required: bool = Field(False, description="Whether parameter is required")
    minimum: Optional[float] = Field(None, description="Minimum value for numbers")
    maximum: Optional[float] = Field(None, description="Maximum value for numbers")
    pattern: Optional[str] = Field(None, description="Regex pattern for strings")


class AIToolConfigurationSchema(BaseModel):
    """AI tool configuration schema"""
    type: str = Field(default="object", description="JSON Schema type")
    properties: Dict[str, ToolParameterSchema] = Field(default_factory=dict, description="Configuration properties")
    required: List[str] = Field(default_factory=list, description="Required configuration keys")
    additional_properties: bool = Field(default=False, description="Allow additional properties")


class EnhancedAIToolDefinition(BaseModel):
    """Enhanced AI tool definition with configuration support"""
    name: str = Field(..., description="Tool name (unique within plugin)")
    description: str = Field(..., description="Tool description for LLM")
    type: str = Field("analysis", description="Tool type: analysis, action, query")
    category: str = Field("custom", description="Tool category: data, analysis, automation, integration, custom")
    endpoint: str = Field(..., description="Plugin endpoint path")
    method: str = Field("GET", description="HTTP method")
    
    # Configuration Schema
    configuration_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema for tool configuration")
    default_configuration: Dict[str, Any] = Field(default_factory=dict, description="Default configuration")
    
    # Access Control
    required_tier: str = Field("community", description="Required tier: community, professional, enterprise")
    enabled_by_default: bool = Field(True, description="Enable tool by default")
    
    # Parameters
    parameters: Dict[str, ToolParameterSchema] = Field(default_factory=dict, description="Tool parameters")
    response_format: Optional[Dict[str, Any]] = Field(None, description="Response format schema")
    
    # Metadata
    tags: List[str] = Field(default_factory=list, description="Tool tags for discoverability")
    version: str = Field("1.0.0", description="Tool version")
    
    # Validation
    requires_configuration: bool = Field(False, description="Whether tool requires configuration")
    allow_user_configuration: bool = Field(True, description="Allow users to configure tool")
    
    @validator('configuration_schema')
    def validate_configuration_schema(cls, v):
        """Validate that configuration_schema is valid JSON Schema"""
        if v is not None:
            try:
                # Basic JSON Schema validation
                if not isinstance(v, dict):
                    raise ValueError("configuration_schema must be a dictionary")
                if "type" not in v:
                    v["type"] = "object"
            except Exception as e:
                raise ValueError(f"Invalid JSON Schema: {e}")
        return v


class AIToolsConfigSection(BaseModel):
    """AI tools configuration section in manifest"""
    default_enabled: bool = Field(True, description="Enable all tools by default")
    tools: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Tool-specific overrides")
    
    @validator('tools')
    def validate_tools_overrides(cls, v):
        """Validate tool override configuration"""
        for tool_name, config in v.items():
            if "enabled" not in config:
                config["enabled"] = True
            if "required_tier" not in config:
                config["required_tier"] = "community"
        return v


class PluginManifestV3(BaseModel):
    """Enhanced plugin manifest schema V3"""
    name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(..., description="Plugin version (semver)")
    description: str = Field(..., description="Plugin description")
    author: str = Field(..., description="Plugin author")
    license: str = Field(..., description="Plugin license")
    
    # AI Tools
    ai_tools: Optional[List[EnhancedAIToolDefinition]] = Field(None, description="AI tools provided by plugin")
    ai_tools_config: Optional[AIToolsConfigSection] = Field(None, description="AI tools configuration")
    
    # Marketplace Integration
    marketplace: Optional[Dict[str, Any]] = Field(None, description="Marketplace integration settings")
    pricing_model: str = Field("free", description="Pricing model: free, paid, freemium")
    base_tier: str = Field("community", description="Base tier: community, professional, enterprise")


def validate_manifest_v3(manifest_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate plugin manifest V3
    
    Args:
        manifest_data: Raw manifest dictionary
        
    Returns:
        Validation result with validated manifest
    """
    try:
        manifest = PluginManifestV3(**manifest_data)
        
        # Additional validation for AI tools
        if manifest.ai_tools:
            for tool in manifest.ai_tools:
                # Validate configuration schema
                if tool.configuration_schema:
                    try:
                        validate(instance={}, schema=tool.configuration_schema)
                    except JSONSchemaValidationError as e:
                        return {
                            "valid": False,
                            "errors": [f"Invalid configuration schema for tool {tool.name}: {e}"]
                        }
                
                # Validate default configuration against schema
                if tool.configuration_schema and tool.default_configuration:
                    try:
                        validate(instance=tool.default_configuration, schema=tool.configuration_schema)
                    except JSONSchemaValidationError as e:
                        return {
                            "valid": False,
                            "errors": [f"Default configuration doesn't match schema for tool {tool.name}: {e}"]
                        }
        
        return {
            "valid": True,
            "validated_manifest": manifest.dict(),
            "errors": []
        }
        
    except Exception as e:
        return {
            "valid": False,
            "validated_manifest": None,
            "errors": [str(e)]
        }


def load_and_validate_manifest(manifest_path: Path) -> Dict[str, Any]:
    """
    Load and validate manifest from file
    
    Args:
        manifest_path: Path to manifest.yml file
        
    Returns:
        Validation result
    """
    import yaml
    
    with open(manifest_path, 'r') as f:
        manifest_data = yaml.safe_load(f)
    
    return validate_manifest_v3(manifest_data)
```

- [ ] **Step 4: Enhance AI tool validator**

```python
# src/shared/ai/tool_validator.py (enhanced)
"""
Plugin AI Tools Validator - Enhanced
Validates ai_tools section in plugin manifests with V3 schema support
"""

import logging
from typing import Any, Dict, List

from pydantic import ValidationError
from pathlib import Path

from .tool_schema import AIToolDefinition, PluginAITools

logger = logging.getLogger(__name__)


def validate_ai_tools(manifest: Dict[str, Any], schema_version: str = "v2") -> List[AIToolDefinition]:
    """
    Validate AI tools section in plugin manifest
    
    Args:
        manifest: Plugin manifest dictionary
        schema_version: Manifest schema version (v2 or v3)
        
    Returns:
        List of validated AIToolDefinition objects
        
    Raises:
        ValidationError: If ai_tools section is invalid
    """
    ai_tools_section = manifest.get("ai_tools")
    
    if not ai_tools_section:
        return []
    
    # Handle V3 enhanced schema
    if schema_version == "v3":
        return _validate_ai_tools_v3(ai_tools_section)
    
    # Handle V2 legacy schema
    return _validate_ai_tools_v2(ai_tools_section)


def _validate_ai_tools_v2(ai_tools_section: Any) -> List[AIToolDefinition]:
    """Validate V2 AI tools format"""
    # Handle both list and dict formats
    if isinstance(ai_tools_section, list):
        tools_data = {"tools": ai_tools_section}
    elif isinstance(ai_tools_section, dict):
        tools_data = ai_tools_section
    else:
        raise ValidationError(f"ai_tools must be a list or dict, got {type(ai_tools_section)}")
    
    # Validate with Pydantic
    try:
        plugin_tools = PluginAITools(**tools_data)
        logger.info(f"Validated {len(plugin_tools.tools)} AI tools (V2 format)")
        return plugin_tools.tools
    except ValidationError as e:
        logger.error(f"AI tools validation failed: {e}")
        raise


def _validate_ai_tools_v3(ai_tools_section: Any) -> List[AIToolDefinition]:
    """Validate V3 enhanced AI tools format"""
    from src.core.manifest_schema_v3 import EnhancedAIToolDefinition, AIToolsConfigSection
    
    if not isinstance(ai_tools_section, list):
        raise ValidationError(f"V3 ai_tools must be a list, got {type(ai_tools_section)}")
    
    validated_tools = []
    for tool_data in ai_tools_section:
        try:
            enhanced_tool = EnhancedAIToolDefinition(**tool_data)
            
            # Convert to V2 format for backward compatibility
            tool_v2 = AIToolDefinition(
                name=enhanced_tool.name,
                description=enhanced_tool.description,
                type=enhanced_tool.type,
                endpoint=enhanced_tool.endpoint,
                method=enhanced_tool.method,
                parameters=enhanced_tool.parameters,
                response_format=enhanced_tool.response_format
            )
            
            validated_tools.append(tool_v2)
            
        except ValidationError as e:
            logger.error(f"Tool validation failed for {tool_data.get('name', 'unknown')}: {e}")
            raise
    
    logger.info(f"Validated {len(validated_tools)} AI tools (V3 format)")
    return validated_tools


def extract_ai_tools_config(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract AI tools configuration from manifest
    
    Args:
        manifest: Plugin manifest dictionary
        
    Returns:
        AI tools configuration
    """
    # Check for V3 format
    if "ai_tools_config" in manifest:
        return manifest["ai_tools_config"]
    
    # Check for V2 format (basic enabled/disabled)
    ai_tools = manifest.get("ai_tools", [])
    if isinstance(ai_tools, list):
        return {
            "default_enabled": True,
            "tools": {
                tool.get("name", tool.get("name", "")): {
                    "enabled": tool.get("enabled", True),
                    "required_tier": tool.get("required_tier", "community")
                }
                for tool in ai_tools
            }
        }
    
    return {"default_enabled": True, "tools": {}}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /root/minder && python -m pytest tests/integration/test_manifest_v3_integration.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/core/manifest_schema_v3.py
git add src/shared/ai/tool_validator.py
git add tests/integration/test_manifest_v3_integration.py
git commit -m "feat(plugins): add enhanced manifest schema V3 with AI tools configuration"
```

---

## Due to length constraints, continuing with remaining tasks in subsequent responses.

**Next tasks to implement:**

**Phase 3: Enhanced AI Tools API (Week 3-4)**
- Task 5: Enhanced AI Tools API Endpoints
- Task 6: Tool Enable/Disable API
- Task 7: Tool Configuration API
- Task 8: Tier-based Access Control API

**Phase 4: Plugin Registry Integration (Week 4-5)**
- Task 9: Enhanced Plugin Registry with AI Tools
- Task 10: Dynamic Tool Discovery
- Task 11: Tool Lifecycle Management
- Task 12: Marketplace Synchronization

**Phase 5: Developer Portal (Week 5-6)**
- Task 13: Plugin Upload with AI Tools
- Task 14: Tool Configuration UI
- Task 15: Analytics Dashboard
- Task 16: Documentation Generator

**Phase 6: Testing & Deployment (Week 6-7)**
- Task 17-20: Integration Tests
- Task 21-25: Documentation
- Task 26-30: Deployment

**Total Tasks:** 30+
**Timeline:** 7 weeks
**Status:** Ready for execution

---

## Key Enhancements Summary

### 1. **AI Tools Configuration Management**
- Schema-based tool configuration
- Per-installation configuration
- Default and custom configurations
- Configuration validation

### 2. **Tool Enable/Disable System**
- Master enable/disable per plugin-tool pair
- Per-installation enable/disable
- Activation status tracking
- Validation status management

### 3. **Tier-based Access Control**
- Granular tier requirements per tool
- Tier validation at tool execution
- Plugin-level tier defaults
- User tier inheritance

### 4. **Enhanced Plugin Manifest**
- V3 schema with AI tools configuration
- Tool metadata and categorization
- Configuration schema definitions
- Marketplace integration settings

### 5. **Marketplace Integration**
- Grafana-like plugin store experience
- Tool discovery and search
- Category-based browsing
- Tier-based filtering

---

**Plan saved to `docs/superpowers/plans/2026-04-26-enhanced-plugin-marketplace-ai-tools.md`**
