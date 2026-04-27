"""
Minder Agent Framework
Plugin agent capabilities for external API integration and tool execution
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of agent actions"""

    HTTP_GET = "http_get"
    HTTP_POST = "http_post"
    HTTP_PUT = "http_put"
    HTTP_DELETE = "http_delete"
    EXECUTE_COMMAND = "execute_command"
    DATABASE_QUERY = "database_query"
    CUSTOM_FUNCTION = "custom_function"


class AgentAction:
    """Represents an executable action"""

    def __init__(
        self,
        name: str,
        description: str,
        action_type: ActionType,
        parameters: Dict[str, Any],
        handler: Optional[Callable] = None,
    ):
        self.name = name
        self.description = description
        self.action_type = action_type
        self.parameters = parameters
        self.handler = handler
        self.created_at = datetime.now()


class ServiceRegistry:
    """Registry of discoverable services"""

    def __init__(self):
        self.services: Dict[str, Dict[str, Any]] = {}

    def register_service(
        self,
        service_id: str,
        name: str,
        base_url: str,
        auth_type: str = "none",
        auth_config: Dict[str, Any] = None,
        endpoints: List[Dict[str, Any]] = None,
    ):
        """Register a service"""
        self.services[service_id] = {
            "id": service_id,
            "name": name,
            "base_url": base_url,
            "auth_type": auth_type,
            "auth_config": auth_config or {},
            "endpoints": endpoints or [],
            "registered_at": datetime.now().isoformat(),
        }
        logger.info(f"✅ Registered service: {service_id} ({name})")

    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get service by ID"""
        return self.services.get(service_id)

    def list_services(self) -> List[Dict[str, Any]]:
        """List all services"""
        return list(self.services.values())

    def discover_services(self, base_url: str = "http://localhost:8000") -> List[Dict[str, Any]]:
        """Auto-discover services from API Gateway"""
        # Implementation would query API Gateway for available services
        # For now, return known services
        return self.list_services()


class AgentExecutor:
    """Execute agent actions"""

    def __init__(self, service_registry: ServiceRegistry):
        self.registry = service_registry
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()
        logger.info("✅ Agent executor initialized")

    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
            logger.info("✅ Agent executor cleaned up")

    async def execute_action(
        self, action: AgentAction, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Execute an agent action"""
        context = context or {}

        try:
            if action.action_type == ActionType.HTTP_GET:
                return await self._http_get(action, context)
            elif action.action_type == ActionType.HTTP_POST:
                return await self._http_post(action, context)
            elif action.action_type == ActionType.HTTP_PUT:
                return await self._http_put(action, context)
            elif action.action_type == ActionType.HTTP_DELETE:
                return await self._http_delete(action, context)
            elif action.action_type == ActionType.EXECUTE_COMMAND:
                return await self._execute_command(action, context)
            elif action.action_type == ActionType.CUSTOM_FUNCTION:
                if action.handler:
                    return await action.handler(action, context)
                else:
                    raise ValueError("Custom function action requires handler")
            else:
                raise ValueError(f"Unknown action type: {action.action_type}")

        except Exception as e:
            logger.error(f"❌ Action execution failed: {action.name} - {e}")
            return {
                "success": False,
                "error": str(e),
                "action": action.name,
            }

    async def _http_get(self, action: AgentAction, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute HTTP GET request"""
        url = action.parameters.get("url")
        service_id = action.parameters.get("service_id")

        if service_id:
            service = self.registry.get_service(service_id)
            if not service:
                raise ValueError(f"Service not found: {service_id}")
            url = f"{service['base_url']}{url}"

        headers = await self._build_headers(service_id if service_id else None)

        async with self.session.get(url, headers=headers) as response:
            data = (
                await response.json()
                if response.content_type == "application/json"
                else await response.text()
            )

            return {
                "success": response.status < 400,
                "status_code": response.status,
                "data": data,
                "action": action.name,
            }

    async def _http_post(self, action: AgentAction, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute HTTP POST request"""
        url = action.parameters.get("url")
        service_id = action.parameters.get("service_id")
        payload = action.parameters.get("payload", {})

        if service_id:
            service = self.registry.get_service(service_id)
            if not service:
                raise ValueError(f"Service not found: {service_id}")
            url = f"{service['base_url']}{url}"

        headers = await self._build_headers(service_id if service_id else None)
        headers["Content-Type"] = "application/json"

        async with self.session.post(url, json=payload, headers=headers) as response:
            data = (
                await response.json()
                if response.content_type == "application/json"
                else await response.text()
            )

            return {
                "success": response.status < 400,
                "status_code": response.status,
                "data": data,
                "action": action.name,
            }

    async def _http_put(self, action: AgentAction, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute HTTP PUT request"""
        url = action.parameters.get("url")
        service_id = action.parameters.get("service_id")
        payload = action.parameters.get("payload", {})

        if service_id:
            service = self.registry.get_service(service_id)
            if not service:
                raise ValueError(f"Service not found: {service_id}")
            url = f"{service['base_url']}{url}"

        headers = await self._build_headers(service_id if service_id else None)
        headers["Content-Type"] = "application/json"

        async with self.session.put(url, json=payload, headers=headers) as response:
            data = (
                await response.json()
                if response.content_type == "application/json"
                else await response.text()
            )

            return {
                "success": response.status < 400,
                "status_code": response.status,
                "data": data,
                "action": action.name,
            }

    async def _http_delete(self, action: AgentAction, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute HTTP DELETE request"""
        url = action.parameters.get("url")
        service_id = action.parameters.get("service_id")

        if service_id:
            service = self.registry.get_service(service_id)
            if not service:
                raise ValueError(f"Service not found: {service_id}")
            url = f"{service['base_url']}{url}"

        headers = await self._build_headers(service_id if service_id else None)

        async with self.session.delete(url, headers=headers) as response:
            data = (
                await response.json()
                if response.content_type == "application/json"
                else await response.text()
            )

            return {
                "success": response.status < 400,
                "status_code": response.status,
                "data": data,
                "action": action.name,
            }

    async def _execute_command(
        self, action: AgentAction, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute shell command (use with caution!)"""
        command = action.parameters.get("command")
        if not command:
            raise ValueError("Command not specified")

        import subprocess

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=action.parameters.get("timeout", 30),
            )

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "action": action.name,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Command timed out",
                "action": action.name,
            }

    async def _build_headers(self, service_id: str) -> Dict[str, str]:
        """Build HTTP headers with authentication"""
        headers = {}

        if not service_id:
            return headers

        service = self.registry.get_service(service_id)
        if not service:
            return headers

        auth_type = service.get("auth_type", "none")
        auth_config = service.get("auth_config", {})

        if auth_type == "bearer":
            token = auth_config.get("token")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        elif auth_type == "api_key":
            api_key = auth_config.get("api_key")
            header_name = auth_config.get("header_name", "X-API-Key")
            if api_key:
                headers[header_name] = api_key

        elif auth_type == "basic":
            username = auth_config.get("username")
            password = auth_config.get("password")
            if username and password:
                import base64

                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers["Authorization"] = f"Basic {credentials}"

        return headers


class AgentCapability:
    """Agent capability for plugins"""

    def __init__(self, plugin_id: str, service_registry: ServiceRegistry, executor: AgentExecutor):
        self.plugin_id = plugin_id
        self.registry = service_registry
        self.executor = executor
        self.actions: Dict[str, AgentAction] = {}

    def register_action(
        self,
        name: str,
        description: str,
        action_type: ActionType,
        parameters: Dict[str, Any],
        handler: Optional[Callable] = None,
    ):
        """Register a new action"""
        action = AgentAction(name, description, action_type, parameters, handler)
        self.actions[name] = action
        logger.info(f"✅ Plugin {self.plugin_id} registered action: {name}")

    async def execute_action(
        self, action_name: str, parameters: Dict[str, Any] = None, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Execute a registered action"""
        if action_name not in self.actions:
            raise ValueError(f"Action not found: {action_name}")

        action = self.actions[action_name]

        # Override parameters if provided
        if parameters:
            action.parameters.update(parameters)

        return await self.executor.execute_action(action, context)

    def list_actions(self) -> List[Dict[str, Any]]:
        """List available actions"""
        return [
            {
                "name": action.name,
                "description": action.description,
                "type": action.action_type.value,
                "parameters": action.parameters,
            }
            for action in self.actions.values()
        ]


class AgentManager:
    """Manager for all plugin agent capabilities"""

    def __init__(self):
        self.registry = ServiceRegistry()
        self.executor = AgentExecutor(self.registry)
        self.capabilities: Dict[str, AgentCapability] = {}

    async def initialize(self):
        """Initialize agent manager"""
        await self.executor.initialize()

        # Register core Minder services
        self._register_core_services()

        logger.info("✅ Agent manager initialized")

    async def cleanup(self):
        """Cleanup resources"""
        await self.executor.cleanup()

    def register_plugin(self, plugin_id: str) -> AgentCapability:
        """Register a plugin's agent capability"""
        capability = AgentCapability(plugin_id, self.registry, self.executor)
        self.capabilities[plugin_id] = capability
        logger.info(f"✅ Registered agent capability for plugin: {plugin_id}")
        return capability

    def get_capability(self, plugin_id: str) -> Optional[AgentCapability]:
        """Get plugin's agent capability"""
        return self.capabilities.get(plugin_id)

    def _register_core_services(self):
        """Register core Minder services"""
        # RAG Pipeline
        self.registry.register_service(
            service_id="rag-pipeline",
            name="RAG Pipeline",
            base_url="http://minder-rag-pipeline:8004",
            auth_type="none",
            endpoints=[
                {
                    "path": "/knowledge-base",
                    "method": "POST",
                    "description": "Create knowledge base",
                },
                {
                    "path": "/knowledge-base/{kb_id}/upload",
                    "method": "POST",
                    "description": "Upload document",
                },
                {
                    "path": "/pipeline/{pipeline_id}/query",
                    "method": "POST",
                    "description": "Query RAG pipeline",
                },
            ],
        )

        # Model Management
        self.registry.register_service(
            service_id="model-management",
            name="Model Management",
            base_url="http://minder-model-management:8005",
            auth_type="none",
            endpoints=[
                {"path": "/models", "method": "GET", "description": "List models"},
                {"path": "/models", "method": "POST", "description": "Register model"},
                {"path": "/models/fine-tune", "method": "POST", "description": "Fine-tune model"},
            ],
        )

        # TTS/STT Service
        self.registry.register_service(
            service_id="tts-stt",
            name="TTS/STT Service",
            base_url="http://minder-tts-stt-service:8006",
            auth_type="none",
            endpoints=[
                {"path": "/tts", "method": "POST", "description": "Text-to-speech"},
                {"path": "/stt", "method": "POST", "description": "Speech-to-text"},
            ],
        )


# Global agent manager
agent_manager = AgentManager()
