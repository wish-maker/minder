"""AI-tool aggregation and the generic plugin-analysis endpoint.

Built via a factory with shared state (plugins_db, plugin_instances) injected by
``main`` — see routes/services.py for the rationale. ``validate_ai_tools`` and
``settings`` are imported directly (they carry no request state).
"""

import json
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from config import settings
from shared.ai.tool_validator import validate_ai_tools


def build_ai_tools_router(*, plugins_db, plugin_instances, logger) -> APIRouter:
    router = APIRouter(tags=["AI Tools"])

    async def _load_plugin_manifest(plugin_name: str):
        """Load a plugin manifest (yml preferred, json fallback) from disk."""
        try:
            plugins_path = Path(settings.PLUGINS_PATH)
            manifest_file = plugins_path / plugin_name / "manifest.yml"
            if not manifest_file.exists():
                manifest_file = plugins_path / plugin_name / "manifest.json"
            if not manifest_file.exists():
                return None
            with open(manifest_file, "r") as f:
                if manifest_file.suffix in (".yaml", ".yml"):
                    return yaml.safe_load(f)
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load manifest for {plugin_name}: {e}")
            return None

    @router.get("/v1/plugins/ai/tools")
    async def get_all_ai_tools():
        """Aggregate OpenAI-compatible tool definitions from all active plugins."""
        all_tools = []
        for plugin_name in plugins_db:
            try:
                if not plugin_instances.get(plugin_name):
                    logger.debug(f"Plugin instance not available: {plugin_name}")
                    continue
                manifest = await _load_plugin_manifest(plugin_name)
                if not manifest:
                    logger.debug(f"No manifest found for plugin: {plugin_name}")
                    continue
                for tool in validate_ai_tools(manifest):
                    properties = {}
                    required = []
                    for param_name, param_def in tool.parameters.items():
                        properties[param_name] = {
                            "type": param_def.type.value,
                            "description": param_def.description,
                        }
                        if param_def.enum:
                            properties[param_name]["enum"] = param_def.enum
                        if param_def.default is not None:
                            properties[param_name]["default"] = param_def.default
                        if param_def.required:
                            required.append(param_name)
                    all_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": {
                                    "type": "object",
                                    "properties": properties,
                                    "required": required,
                                },
                            },
                            "metadata": {
                                "plugin": plugin_name,
                                "endpoint": f"/v1/plugins/{plugin_name}{tool.endpoint}",
                                "method": tool.method,
                            },
                        }
                    )
            except Exception as e:
                logger.error(f"Failed to load AI tools from plugin {plugin_name}: {e}")
                continue
        return {"tools": all_tools}

    @router.get("/v1/plugins/{plugin_name}/analysis")
    async def get_plugin_analysis(
        plugin_name: str,
        symbol: str = None,
        limit: int = 10,
        location: str = "Istanbul",
        fund_type: str = "YATIRIM",
    ):
        """Generic analysis endpoint: call a plugin's analyze() and shape the result."""
        if plugin_name not in plugins_db:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")
        if not plugins_db[plugin_name].enabled:
            raise HTTPException(
                status_code=403, detail=f"Plugin '{plugin_name}' is not enabled"
            )
        if plugin_name not in plugin_instances:
            raise HTTPException(
                status_code=503, detail=f"Plugin '{plugin_name}' is not running"
            )
        try:
            analysis_result = await plugin_instances[plugin_name].analyze()

            if plugin_name == "crypto" and symbol:
                if "metrics" in analysis_result and symbol in analysis_result["metrics"]:
                    return {
                        "symbol": symbol,
                        **analysis_result["metrics"][symbol],
                        "timestamp": datetime.now().isoformat(),
                    }
                raise HTTPException(
                    status_code=404, detail=f"No data found for symbol {symbol}"
                )
            elif plugin_name == "news":
                if "insights" in analysis_result:
                    articles = analysis_result.get("metrics", {}).get(
                        "latest_articles", []
                    )
                    return {
                        "articles": articles[:limit],
                        "total": min(limit, len(articles)),
                        "limit": limit,
                    }
            elif plugin_name == "weather" and location:
                if "metrics" in analysis_result:
                    weather_data = analysis_result["metrics"].get(
                        location,
                        {
                            "temperature": analysis_result["metrics"].get("avg_temp_c", 0),
                            "humidity": analysis_result["metrics"].get(
                                "avg_humidity_pct", 0
                            ),
                            "conditions": "unknown",
                        },
                    )
                    return {
                        "location": location,
                        "temperature": weather_data.get("temperature", 0),
                        "humidity": weather_data.get("humidity", 0),
                        "conditions": weather_data.get("conditions", "unknown"),
                        "timestamp": datetime.now().isoformat(),
                    }
            elif plugin_name == "network":
                if "metrics" in analysis_result:
                    m = analysis_result["metrics"]
                    return {
                        "metrics": [
                            {
                                "timestamp": datetime.now().isoformat(),
                                "cpu_usage": m.get("avg_cpu_usage_pct", 0),
                                "memory_usage": m.get("avg_memory_usage_pct", 0),
                                "load_avg": m.get("avg_load_avg", 0),
                            }
                        ],
                        "average_latency": m.get("avg_load_avg", 0),
                        "limit": limit,
                    }
            elif plugin_name == "tefas":
                if (
                    "metrics" in analysis_result
                    and "top_funds" in analysis_result["metrics"]
                ):
                    funds = analysis_result["metrics"]["top_funds"][:limit]
                    return {
                        "funds": funds,
                        "total": len(funds),
                        "fund_type": fund_type,
                        "limit": limit,
                    }
            return analysis_result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Analysis error for plugin {plugin_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    return router
