"""
Minder FastAPI Application
Main REST API for Minder platform
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request, Body
from pydantic import BaseModel, field_validator
from typing import Dict, List, Any, Optional
import logging
import os

from core.kernel import MinderKernel
from core.character_system import CharacterEngine, Character
from core.voice_interface import VoiceInterface
from .mobile import setup_mobile_routes, MobileAPIHandler
from . import plugin_store
from .auth import (
    AuthManager, get_auth_manager, get_current_user, get_current_user_optional,
    LoginRequest, LoginResponse
)
from .middleware import setup_middleware, expensive_limiter, limiter
from .security import InputSanitizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
kernel: Optional[MinderKernel] = None
character_engine: Optional[CharacterEngine] = None
voice_interface: Optional[VoiceInterface] = None
mobile_handler: Optional[MobileAPIHandler] = None

# FastAPI app
app = FastAPI(
    title="Minder API",
    description="""
# 🧠 Minder - Modular RAG Platform

AI-powered knowledge management platform with hot-swappable plugins for intelligent data analysis and retrieval.

## 🚀 Key Features

### Plugin System
- **Hot-swappable plugins**: Load/unload plugins without restart
- **Dynamic discovery**: Automatic plugin detection and registration
- **Multi-source support**: News, crypto, weather, network monitoring, financial analysis
- **GitHub integration**: Install plugins directly from GitHub repositories

### AI Capabilities
- **Ollama Integration**: Local LLM support for privacy and speed
- **RAG Pipeline**: Retrieval-augmented generation with vector embeddings
- **Knowledge Graph**: Entity resolution and relationship inference
- **Event Bus**: Real-time updates and cross-plugin correlations

### Security & Performance
- **JWT Authentication**: Token-based auth with configurable expiration
- **Rate Limiting**: Network-aware rate limiting (Local/VPN/Public)
- **Input Validation**: SQL injection, XSS, and command injection prevention
- **Network Detection**: Automatic network type detection and policy enforcement

## 🔐 Authentication

Most endpoints require JWT authentication. Include your token in the Authorization header:

```bash
curl -H \"Authorization: Bearer YOUR_TOKEN\" http://localhost:8000/plugins
```

### Get Your Token
1. **Default credentials**: `admin` / `admin123`
2. **Login endpoint**: `POST /auth/login`
3. **Token expiration**: 30 minutes (configurable)

### Network-Based Rate Limits
- **Local Network** (192.168.68.x): Unlimited access
- **VPN/Tailscale** (100.x.x.x): 200 requests/hour
- **Public Network**: 50 requests/hour

## 📚 API Documentation

- **Swagger UI**: [`/docs`](/docs) - Interactive API documentation
- **ReDoc**: [`/redoc`](/redoc) - Alternative documentation viewer
- **OpenAPI JSON**: [`/openapi.json`](/openapi.json) - Machine-readable spec

## 🔧 Quick Start

```python
import requests

# 1. Login and get token
response = requests.post('http://localhost:8000/auth/login', json={
    'username': 'admin',
    'password': 'admin123'
})
token = response.json()['access_token']

# 2. Use the token
headers = {'Authorization': f'Bearer {token}'}

# 3. List plugins
plugins = requests.get('http://localhost:8000/plugins', headers=headers).json()

# 4. Chat with AI
chat = requests.post('http://localhost:8000/chat',
    headers=headers,
    json={'message': 'What are the latest crypto prices?'}
).json()
```

## 🧩 Plugin Development

Create your own plugins by extending `BaseModule`:

```python
from core.module_interface import BaseModule, ModuleMetadata

class MyPlugin(BaseModule):
    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name=\"my_plugin\",
            version=\"1.0.0\",
            description=\"My awesome plugin\",
            author=\"Your Name\"
        )

    async def collect_data(self, since=None):
        return {'records_collected': 100}
```

For detailed plugin development guide, see the [`/plugins/docs`](/plugins/docs) endpoint.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "Minder AI Team",
        "url": "https://github.com/minder-project",
        "email": "info@minder.ai"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    openapi_tags=[
        {
            "name": "Authentication",
            "description": "JWT authentication and user management endpoints"
        },
        {
            "name": "Plugins",
            "description": "Plugin discovery, loading, and management endpoints"
        },
        {
            "name": "AI Chat",
            "description": "AI-powered chat interface with Ollama LLM integration"
        },
        {
            "name": "System",
            "description": "System health, monitoring, and configuration endpoints"
        },
        {
            "name": "Plugin Store",
            "description": "GitHub plugin installation and management"
        },
        {
            "name": "Knowledge Graph",
            "description": "Entity relationships and knowledge graph operations"
        },
        {
            "name": "Voice Interface",
            "description": "Speech-to-text and text-to-speech capabilities"
        }
    ]
)

# Get allowed origins from environment
ALLOWED_ORIGINS = os.getenv(
    'ALLOWED_ORIGINS',
    'http://localhost:3000,http://192.168.68.*'
).split(',')

# Setup security middleware (CORS, rate limiting, network detection)
setup_middleware(app, ALLOWED_ORIGINS)

# Include Plugin Store router
app.include_router(plugin_store.router)

# Request/Response models
class ChatRequest(BaseModel):
    message: str
    character: Optional[str] = None
    voice_mode: bool = False

    @field_validator('message')
    @classmethod
    def validate_message(cls, v):
        """Validate and sanitize chat message"""
        # Check for security issues
        is_valid, error_msg = InputSanitizer.validate_input(v)
        if not is_valid:
            raise ValueError(error_msg)

        # Sanitize input
        return InputSanitizer.sanitize_string(v, max_length=5000)

    @field_validator('character')
    @classmethod
    def validate_character(cls, v):
        """Validate character name"""
        if v is None:
            return v

        # Check for security issues
        is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False, check_xss=False)
        if not is_valid:
            raise ValueError(error_msg)

        # Sanitize input
        return InputSanitizer.sanitize_string(v, max_length=50)

class PipelineRequest(BaseModel):
    module: str
    pipeline: Optional[List[str]] = None

    @field_validator('module')
    @classmethod
    def validate_module(cls, v):
        """Validate module name"""
        # Check for security issues
        is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False, check_xss=False)
        if not is_valid:
            raise ValueError(error_msg)

        # Sanitize input
        return InputSanitizer.sanitize_string(v, max_length=100)

    @field_validator('pipeline')
    @classmethod
    def validate_pipeline(cls, v):
        """Validate pipeline steps"""
        if v is None:
            return v

        # Sanitize all pipeline steps
        sanitized = []
        for step in v:
            if step is None:
                continue
            # Check for security issues
            is_valid, error_msg = InputSanitizer.validate_input(step, check_sql=False, check_xss=False)
            if not is_valid:
                raise ValueError(error_msg)
            # Sanitize input
            sanitized.append(InputSanitizer.sanitize_string(step, max_length=100))

        return sanitized

class CharacterCreateRequest(BaseModel):
    name: str
    description: str
    personality: Dict[str, float]
    voice_profile: Dict[str, Any]
    system_prompt: str

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Validate character name"""
        is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False, check_xss=False)
        if not is_valid:
            raise ValueError(error_msg)

        return InputSanitizer.sanitize_string(v, max_length=100)

    @field_validator('description')
    @classmethod
    def validate_description(cls, v):
        """Validate character description"""
        is_valid, error_msg = InputSanitizer.validate_input(v)
        if not is_valid:
            raise ValueError(error_msg)

        return InputSanitizer.sanitize_string(v, max_length=1000)

    @field_validator('system_prompt')
    @classmethod
    def validate_system_prompt(cls, v):
        """Validate system prompt"""
        is_valid, error_msg = InputSanitizer.validate_input(v)
        if not is_valid:
            raise ValueError(error_msg)

        return InputSanitizer.sanitize_string(v, max_length=5000)

# Startup/Shutdown
@app.on_event("startup")
async def startup():
    """Initialize Minder on startup"""
    global kernel, character_engine, voice_interface

    logger.info("🚀 Starting Minder API...")

    # Validate required secrets
    _validate_secrets()

    config = {
        'fund': {
            'database': {
                'host': 'postgres',
                'port': 5432,
                'database': 'fundmind',
                'user': 'postgres',
                'password': os.getenv('POSTGRES_PASSWORD', 'id8O+LtRz2OONDKYT9ev+tzOwF/f5lcEcv7eUbIJGI4=')
            }
        },
        'plugins': {
            'network': {},
            'weather': {},
            'crypto': {},
            'news': {}
        },
        'plugin_store': {
            'enabled': True,
            'store_path': '/var/lib/minder/plugins',
            'index_url': 'https://raw.githubusercontent.com/minder-plugins/plugin-index/main/plugins.json',
            'github_token': ''
        }
    }

    # Initialize authentication manager
    from . import auth
    auth.auth_manager = AuthManager()
    logger.info("✅ Authentication manager initialized")

    kernel = MinderKernel(config)
    await kernel.start()

    # Set kernel reference for plugin store router
    plugin_store.set_kernel(kernel)

    character_engine = CharacterEngine(config)
    voice_interface = VoiceInterface(config.get('voice', {}))

    logger.info("✅ Minder API ready")


def _validate_secrets():
    """Validate required secrets are present and production-ready"""
    required_secrets = {
        'JWT_SECRET_KEY': 'JWT_SECRET_KEY',
        'POSTGRES_PASSWORD': 'POSTGRES_PASSWORD',
        'INFLUXDB_PASSWORD': 'INFLUXDB_PASSWORD'
    }

    missing = []
    using_defaults = []
    weak_secrets = []

    for env_var, display_name in required_secrets.items():
        value = os.getenv(env_var)
        if not value:
            # Check if value is set but empty
            missing.append(display_name)
        elif env_var == 'JWT_SECRET_KEY' and value == 'change-this-in-production':
            using_defaults.append(display_name)
        elif env_var == 'INFLUXDB_PASSWORD' and value == 'minder123':
            weak_secrets.append(display_name)

    # Check if running in production mode
    production_mode = os.getenv('PRODUCTION_MODE', 'false').lower() == 'true'

    if missing:
        raise RuntimeError(
            f"❌ Missing required environment variables: {', '.join(missing)}. "
            f"Please set them in .env file before starting."
        )

    if using_defaults:
        if production_mode:
            raise RuntimeError(
                f"❌ Using default values for: {', '.join(using_defaults)}. "
                "This is not safe for production! Please set strong secrets in .env file."
            )
        else:
            logger.warning(
                f"⚠️  Using default values for: {', '.join(using_defaults)}. "
                "This is not safe for production!"
            )

    if weak_secrets:
        if production_mode:
            raise RuntimeError(
                f"❌ Weak secrets detected for: {', '.join(weak_secrets)}. "
                "Please generate strong secrets using: openssl rand -base64 32"
            )
        else:
            logger.warning(
                f"⚠️  Weak secrets detected for: {', '.join(weak_secrets)}. "
                "Please generate strong secrets before production deployment!"
            )

    # Log secret validation status
    if production_mode:
        logger.info("✅ Production secrets validated successfully")
    else:
        logger.info("✅ Development mode: Secrets validated (production checks disabled)")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    global kernel

    if kernel:
        await kernel.stop()
    logger.info("✅ Minder API stopped")

# Endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Minder API",
        "version": "1.0.0",
        "status": "running",
        "authentication": "enabled",
        "network_access": "dual (local + VPN)"
    }

@app.post("/auth/login")
@limiter.limit("10/minute")  # Brute force protection
async def login(request: Request, login_request: LoginRequest):
    """
    Login endpoint - returns JWT access token

    This endpoint can be accessed from trusted networks without authentication
    Rate limited: 10/minute for VPN/public, unlimited for local
    """
    from .auth import LoginResponse, get_auth_manager

    auth_mgr = get_auth_manager()

    # Authenticate user
    user = await auth_mgr.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # Generate access token
    access_token = auth_mgr.create_access_token({
        "sub": user['username'],
        "role": user['role']
    })

    logger.info(f"✅ User logged in: {user['username']} (role: {user['role']})")

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=30 * 60,  # 30 minutes
        user={
            "username": user['username'],
            "role": user['role']
        }
    )

@app.get("/health")
async def health():
    """Health check - publicly accessible"""
    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    status = await kernel.get_system_status()
    return {
        "status": "healthy" if status['status'] == 'running' else "unhealthy",
        "system": status,
        "authentication": "enabled",
        "network_detection": "enabled"
    }

@app.get("/plugins")
@limiter.limit("200/hour")  # Standard API endpoint
async def list_plugins(
    request: Request,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user_optional)
):
    """
    List all plugins

    Accessible from:
    - Trusted networks (local/VPN): No authentication required
    - Public networks: JWT authentication required

    Rate limited: 200/hour for VPN, 50/hour for public, unlimited for local
    """
    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    plugins = await kernel.registry.list_plugins(status=status)

    # Add enabled status for each plugin
    for plugin in plugins:
        plugin_name = plugin['name']
        plugin['enabled'] = kernel.registry.is_plugin_enabled(plugin_name)

    # Also list available but disabled plugins
    available_plugins = kernel.registry.list_available_plugins()
    loaded_plugin_names = {p['name'] for p in plugins}

    disabled_plugins = [
        {
            "name": name,
            "enabled": False,
            "status": "disabled"
        }
        for name in available_plugins
        if name not in loaded_plugin_names
    ]

    return {
        "plugins": plugins + disabled_plugins,
        "total": len(plugins) + len(disabled_plugins),
        "enabled": len(plugins),
        "disabled": len(disabled_plugins),
        "authenticated": current_user is not None,
        "network_type": "trusted" if current_user and not current_user.get('authenticated', True) else "public"
    }

@app.post("/plugins/{plugin_name}/pipeline")
async def run_pipeline(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Run pipeline on a plugin"""
    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    try:
        results = await kernel.run_plugin_pipeline(
            request.plugin,
            request.pipeline
        )
        return {"plugin": request.plugin, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plugins/{plugin_name}/enable")
async def enable_plugin(plugin_name: str):
    """Enable a plugin at runtime"""
    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    try:
        success = await kernel.registry.enable_plugin(plugin_name)
        if success:
            return {
                "plugin": plugin_name,
                "status": "enabled",
                "message": f"Plugin {plugin_name} will be enabled on next restart"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to enable plugin")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plugins/{plugin_name}/disable")
async def disable_plugin(plugin_name: str):
    """Disable a plugin at runtime"""
    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    try:
        success = await kernel.registry.disable_plugin(plugin_name)
        if success:
            return {
                "plugin": plugin_name,
                "status": "disabled",
                "message": f"Plugin {plugin_name} has been disabled and unloaded"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to disable plugin")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
@expensive_limiter.limit("10/minute")  # Expensive operation (AI)
async def chat(request: Request, chat_request: ChatRequest, current_user: dict = Depends(get_current_user_optional)):
    """Chat with Minder AI - Rate limited: 10/minute for VPN, 5/minute for public"""
    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    try:
        # Get character
        character_name = chat_request.character or "finbot"
        character = character_engine.get_character(character_name)
        if not character:
            character = character_engine.presets['finbot']

        # Query plugins for context
        plugin_results = await kernel.query_plugins(chat_request.message)

        # Generate AI response using Ollama
        response = await _generate_ai_response(
            chat_request.message,
            plugin_results,
            character
        )

        return {
            "response": response,
            "character": character.name,
            "plugins_used": [r['plugin'] for r in plugin_results],
            "model": "ollama"
        }

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/characters")
async def list_characters():
    """List all characters"""
    if not character_engine:
        raise HTTPException(status_code=503, detail="Character engine not initialized")

    return {
        "characters": character_engine.list_characters()
    }

@app.post("/characters")
async def create_character(request: CharacterCreateRequest):
    """Create custom character"""
    if not character_engine:
        raise HTTPException(status_code=503, detail="Character engine not initialized")

    try:
        from ..core.character_system import Personality, VoiceProfile

        personality = Personality(**request.personality)
        voice_profile = VoiceProfile(**request.voice_profile)

        character = character_engine.create_character(
            name=request.name,
            description=request.description,
            personality=personality,
            voice_profile=voice_profile,
            system_prompt=request.system_prompt
        )

        return {
            "character": request.name,
            "status": "created"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/correlations")
async def get_correlations():
    """Get all correlations"""
    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    return await kernel.correlation_engine.get_all_correlations()


# Plugin Store helper endpoints
@app.get("/store")
async def plugin_store_info():
    """Get plugin store info"""
    from plugins.store import PluginStore

    if not kernel or not kernel.plugin_store:
        return {
            "enabled": False,
            "message": "Plugin store is not enabled"
        }

    installed = await kernel.plugin_store.list_installed_plugins()

    return {
        "enabled": True,
        "plugins": installed,
        "total": len(installed),
        "store_path": str(kernel.plugin_store.store_path)
    }

@app.get("/system/status")
async def system_status():
    """Get detailed system status"""
    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    return await kernel.get_system_status()

async def _generate_ai_response(
    message: str,
    plugin_results: List[Dict],
    character: Character
) -> str:
    """Generate AI response using Ollama"""

    import httpx
    import json

    # Build context from plugins
    context_parts = []
    if plugin_results:
        for result in plugin_results:
            plugin_name = result.get('plugin', 'unknown')
            data = result.get('data', {})
            if data:
                context_parts.append(f"{plugin_name}: {json.dumps(data, ensure_ascii=False)[:200]}")

    # Build system prompt
    system_prompt = character.system_prompt if hasattr(character, 'system_prompt') else (
        "Sen Minder adlı yapay zeka bir asistansın. Türkçe konuşuyorsun. "
        "Kullanıcıya yardımcı ol, bilgileri net ve açık şekilde sun."
    )

    # Build user prompt
    user_prompt = f"Kullanıcı mesajı: {message}\n"
    if context_parts:
        user_prompt += f"\nEklenti bilgileri:\n" + "\n".join(context_parts)

    try:
        # Call Ollama API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://ollama:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": user_prompt,
                    "system": system_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_ctx": 2048
                    }
                }
            )

            if response.status_code == 200:
                result = response.json()
                ai_response = result.get('response', '')
                if ai_response:
                    return ai_response.strip()
                else:
                    logger.warning("Ollama returned empty response")
                    return "Üzgünüm, şu an yanıt veremiyorum."
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                return "AI servisi şu an kullanılamıyor."

    except Exception as e:
        logger.error(f"Ollama connection error: {e}")
        # Fallback to simple response
        if plugin_results:
            plugins_used = ", ".join([r['plugin'] for r in plugin_results])
            return f"Minder olarak {plugins_used} eklentilerinden bilgiler topladım. Size nasıl yardımcı olabilirim?"

        return "Minder olarak size nasıl yardımcı olabilirim? Fon analizi, network monitoring veya başka bir konu hakkında bilgi alabilirsiniz."

# Setup mobile routes
@app.on_event("startup")
async def setup_mobile():
    """Setup mobile routes after startup"""
    global mobile_handler

    if kernel and character_engine:
        mobile_handler = MobileAPIHandler(kernel, character_engine)
        setup_mobile_routes(app, kernel, character_engine)

