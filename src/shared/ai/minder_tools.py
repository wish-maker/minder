"""
Minder AI Agent - Tool Calling Interface for LLMs
Enables LLMs (Llama 3.2 via Ollama) to call Minder Platform APIs
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
import json
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Minder Platform function definitions for LLM tool calling
MINDER_FUNCTIONS = [
    {
        "name": "collect_crypto_data",
        "description": "Collect latest cryptocurrency market data from Binance, CoinGecko, and Kraken. Returns number of records collected.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Cryptocurrency symbols to collect (BTC, ETH, SOL, ADA, DOT)",
                    "default": ["BTC", "ETH", "SOL", "ADA", "DOT"]
                }
            },
            "required": []
        }
    },
    {
        "name": "get_crypto_price",
        "description": "Get current price and market data for a specific cryptocurrency from the database.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Cryptocurrency symbol (e.g., BTC, ETH, SOL)"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "collect_news",
        "description": "Collect latest news articles from BBC, Guardian, and NPR RSS feeds. Returns number of articles collected.",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Specific news source to collect from",
                    "enum": ["BBC", "Guardian", "NPR", "ALL"]
                }
            },
            "required": []
        }
    },
    {
        "name": "get_latest_news",
        "description": "Get latest news articles from the database with sentiment analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of articles to return",
                    "default": 10
                },
                "source": {
                    "type": "string",
                    "description": "Filter by news source"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_plugin_status",
        "description": "Get health status and information for all Minder plugins. Returns list of plugins with their health status.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "type": "object"
        }
    },
    {
        "name": "enable_plugin",
        "description": "Enable a Minder plugin (crypto, news, network, weather, tefas). Requires admin privileges.",
        "parameters": {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "Plugin name to enable",
                    "enum": ["crypto", "news", "network", "weather", "tefas"]
                }
            },
            "required": ["plugin_name"]
        }
    },
    {
        "name": "get_network_metrics",
        "description": "Get latest network performance metrics including latency, throughput, and connection statistics.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of recent metrics to return",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "get_weather_data",
        "description": "Get latest weather data including temperature, humidity, and conditions for configured locations.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location to get weather for",
                    "default": "Istanbul"
                }
            },
            "required": []
        }
    }
]


class MinderToolExecutor:
    """Execute Minder Platform tools/functions"""

    def __init__(self):
        self.plugin_registry_url = "http://minder-plugin-registry:8001"
        self.api_gateway_url = "http://minder-api-gateway:8000"

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a Minder Platform tool

        Args:
            tool_name: Name of the tool to execute
            parameters: Parameters for the tool

        Returns:
            Tool execution result
        """
        tool_mappings = {
            "collect_crypto_data": self._collect_crypto_data,
            "get_crypto_price": self._get_crypto_price,
            "collect_news": self._collect_news,
            "get_latest_news": self._get_latest_news,
            "get_plugin_status": self._get_plugin_status,
            "enable_plugin": self._enable_plugin,
            "get_network_metrics": self._get_network_metrics,
            "get_weather_data": self._get_weather_data,
        }

        if tool_name not in tool_mappings:
            raise ValueError(f"Unknown tool: {tool_name}")

        executor = tool_mappings[tool_name]
        return await executor(parameters)

    async def _collect_crypto_data(self, params: Dict) -> Dict:
        """Trigger crypto data collection"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.plugin_registry_url}/v1/plugins/crypto/collect"
            )
            response.raise_for_status()
            return response.json()

    async def _get_crypto_price(self, params: Dict) -> Dict:
        """Get crypto price from database"""
        symbol = params.get("symbol", "BTC")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.plugin_registry_url}/v1/plugins/crypto/analysis?symbol={symbol}"
            )
            response.raise_for_status()
            return response.json()

    async def _collect_news(self, params: Dict) -> Dict:
        """Trigger news collection"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.plugin_registry_url}/v1/plugins/news/collect"
            )
            response.raise_for_status()
            return response.json()

    async def _get_latest_news(self, params: Dict) -> Dict:
        """Get latest news from database"""
        limit = params.get("limit", 10)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.plugin_registry_url}/v1/plugins/news/analysis?limit={limit}"
            )
            response.raise_for_status()
            return response.json()

    async def _get_plugin_status(self, params: Dict) -> Dict:
        """Get all plugin status"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.plugin_registry_url}/v1/plugins"
            )
            response.raise_for_status()
            return response.json()

    async def _enable_plugin(self, params: Dict) -> Dict:
        """Enable a plugin"""
        plugin_name = params.get("plugin_name")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.plugin_registry_url}/v1/plugins/{plugin_name}/enable"
            )
            response.raise_for_status()
            return response.json()

    async def _get_network_metrics(self, params: Dict) -> Dict:
        """Get network metrics"""
        limit = params.get("limit", 10)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.plugin_registry_url}/v1/plugins/network/analysis?limit={limit}"
            )
            response.raise_for_status()
            return response.json()

    async def _get_weather_data(self, params: Dict) -> Dict:
        """Get weather data"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.plugin_registry_url}/v1/plugins/weather/analysis"
            )
            response.raise_for_status()
            return response.json()


# Global executor
tool_executor = MinderToolExecutor()


# FastAPI endpoints for AI integration
from fastapi import APIRouter

router = APIRouter(prefix="/v1/ai", tags=["AI Integration"])

@router.post("/chat")
async def chat_with_tools(request: Request):
    """
    Chat endpoint with tool calling support
    Compatible with OpenWebUI and other AI interfaces
    """
    body = await request.json()

    messages = body.get("messages", [])
    tools = body.get("tools", None)

    if not messages:
        raise HTTPException(status_code=400, detail="Messages required")

    # If tools are provided, use them
    if tools:
        # For now, execute first tool
        # In production, LLM should decide which tool to use
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "I'll help you with that. Let me call the appropriate tool.",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": tools[0]["name"],
                            "arguments": json.dumps(tools[0].get("parameters", {}))
                        }
                    }]
                }
            }]
        }

    # If no tools, route to Ollama directly
    ollama_url = "http://ollama:11434/api/chat"

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            ollama_url,
            json=body
        )
        return response.json()


@router.post("/functions/definitions")
async def get_function_definitions():
    """Get available Minder Platform function definitions"""
    return {
        "functions": MINDER_FUNCTIONS
    }


@router.post("/functions/{function_name}")
async def execute_function(function_name: str, request: Request):
    """
    Execute a Minder Platform function/tool
    Called by AI interfaces when tool use is requested
    """
    params = await request.json()

    try:
        result = await tool_executor.execute_tool(function_name, params)

        return {
            "result": result,
            "status": "success",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error executing function {function_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error executing function: {str(e)}"
        )


@router.get("/status")
async def get_ai_status():
    """Get AI integration status"""
    # Check Ollama status
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://ollama:11434/api/tags",
                timeout=5.0
            )
            ollama_status = "healthy" if response.status_code == 200 else "unhealthy"
            models = response.json().get("models", [])
    except:
        ollama_status = "unreachable"
        models = []

    return {
        "ollama_status": ollama_status,
        "available_models": [m["name"] for m in models],
        "tools_available": len(MINDER_FUNCTIONS),
        "tool_names": [f["name"] for f in MINDER_FUNCTIONS],
        "timestamp": datetime.utcnow().isoformat()
    }


# Example usage with LLM
async def chat_with_minder(user_message: str) -> str:
    """
    Example: Chat with Minder Platform using LLM + Tools

    This demonstrates how an LLM can use Minder Platform as tools
    """
    import ollama

    # 1. Get available tools
    tools_response = await get_function_definitions()
    tools = tools_response["functions"]

    # 2. Prepare message with tools
    messages = [
        {"role": "system", "content": "You are a helpful assistant for Minder Platform. You can use tools to collect and analyze data."},
        {"role": "user", "content": user_message}
    ]

    # 3. Call Ollama with tools
    response = ollama.chat(
        'llama3.2',
        messages=messages,
        tools=tools
    )

    # 4. Check if LLM wants to use tools
    if 'message' in response and 'tool_calls' in response['message']:
        tool_calls = response['message']['tool_calls']

        # Execute each tool call
        tool_results = []
        for tool_call in tool_calls:
            function_name = tool_call['function']['name']
            arguments = json.loads(tool_call['function']['arguments'])

            result = await tool_executor.execute_tool(function_name, arguments)
            tool_results.append({
                "tool_call_id": tool_call['id'],
                "role": "tool",
                "name": function_name,
                "content": json.dumps(result)
            })

        # 5. Get final response from LLM with tool results
        messages.extend(tool_results)
        final_response = ollama.chat(
            'llama3.2',
            messages=messages
        )

        return final_response['message']['content']

    return response['message']['content']


# Example conversations
EXAMPLE_CONVERSATIONS = [
    {
        "user": "What's the current price of Bitcoin?",
        "expected_tool": "get_crypto_price",
        "expected_params": {"symbol": "BTC"}
    },
    {
        "user": "Collect the latest crypto data for me",
        "expected_tool": "collect_crypto_data",
        "expected_params": {"symbols": ["BTC", "ETH", "SOL"]}
    },
    {
        "user": "What are the latest news headlines?",
        "expected_tool": "get_latest_news",
        "expected_params": {"limit": 5}
    },
    {
        "user": "Check the status of all plugins",
        "expected_tool": "get_plugin_status",
        "expected_params": {}
    },
    {
        "user": "Get the latest network metrics",
        "expected_tool": "get_network_metrics",
        "expected_params": {"limit": 10}
    }
]
