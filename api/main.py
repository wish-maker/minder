"""
Minder FastAPI Application
Main REST API for Minder platform
"""
from fastapi import FastAPI, Request
import logging
import os

from core.kernel import MinderKernel
from core.character_system import CharacterEngine
from core.voice_interface import VoiceInterface
from . import plugin_store
from . import auth
from .auth import AuthManager
from .middleware import setup_middleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
kernel = None
character_engine = None
voice_interface = None

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
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/plugins
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
            name="my_plugin",
            version="1.0.0",
            description="My awesome plugin",
            author="Your Name"
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
            "name": "Characters",
            "description": "AI character system management"
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
    auth.auth_manager = AuthManager()
    logger.info("✅ Authentication manager initialized")

    kernel = MinderKernel(config)
    await kernel.start()

    # Set kernel reference for plugin store router
    plugin_store.set_kernel(kernel)

    character_engine = CharacterEngine(config)
    voice_interface = VoiceInterface(config.get('voice', {}))

    # Setup modular routes
    _setup_routes(kernel, character_engine)

    logger.info("✅ Minder API ready")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    global kernel

    if kernel:
        await kernel.stop()
    logger.info("✅ Minder API stopped")


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


def _setup_routes(kernel, character_engine):
    """Setup modular routes"""
    from .auth import endpoints as auth_endpoints
    from .plugins import endpoints as plugins_endpoints
    from .chat import endpoints as chat_endpoints
    from .characters import endpoints as characters_endpoints
    from .system import endpoints as system_endpoints
    from .correlations import endpoints as correlations_endpoints

    # Include routers
    app.include_router(auth_endpoints.router)
    app.include_router(plugins_endpoints.setup_plugin_routes(plugins_endpoints.router, kernel))
    app.include_router(chat_endpoints.setup_chat_routes(chat_endpoints.router, kernel, character_engine))
    app.include_router(characters_endpoints.setup_character_routes(characters_endpoints.router, character_engine))
    app.include_router(system_endpoints.setup_system_routes(system_endpoints.router, kernel))
    app.include_router(correlations_endpoints.setup_correlation_routes(correlations_endpoints.router, kernel))


# Root endpoint
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
