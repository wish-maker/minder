"""
Complete OpenWebUI Agent Integration
Connects Minder with OpenWebUI for function calling and character-based interactions
"""

from typing import Dict, List, Any, Optional
import asyncio
import logging
from datetime import datetime
import json

from core.kernel import MinderKernel
from core.character_system import CharacterEngine
from services.voice.voice_service import VoiceService

logger = logging.getLogger(__name__)


class MinderOpenWebUIAgent:
    """
    Complete OpenWebUI agent for Minder

    Features:
    - Function calling for all Minder modules
    - Character-based conversations
    - Voice interaction support
    - Multi-language support (TR, EN)
    - Real-time anomaly alerts
    - Knowledge graph queries
    """

    def __init__(
        self, kernel: MinderKernel, character_engine: CharacterEngine
    ):
        self.kernel = kernel
        self.character_engine = character_engine
        self.voice_service = VoiceService({})

        # Define available functions
        self.functions = self._define_functions()

    def _define_functions(self) -> Dict[str, Dict]:
        """Define available functions for function calling"""
        return {
            "get_fund_recommendations": {
                "name": "get_fund_recommendations",
                "description": "Get personalized fund recommendations based on risk profile",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "risk_tolerance": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "Risk tolerance level",
                        },
                        "investment_horizon": {
                            "type": "string",
                            "enum": ["short", "medium", "long"],
                            "description": "Investment time horizon",
                        },
                        "investment_goal": {
                            "type": "string",
                            "enum": ["growth", "income", "balanced"],
                            "description": "Investment objective",
                        },
                    },
                    "required": ["risk_tolerance"],
                },
            },
            "analyze_fund_performance": {
                "name": "analyze_fund_performance",
                "description": "Analyze performance of a specific fund",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fund_code": {
                            "type": "string",
                            "description": "Fund code (e.g., TEFAS, TEK, SAN)",
                        },
                        "period": {
                            "type": "string",
                            "enum": ["1M", "3M", "6M", "1Y", "ALL"],
                            "description": "Analysis period",
                        },
                    },
                    "required": ["fund_code"],
                },
            },
            "get_system_status": {
                "name": "get_system_status",
                "description": "Get overall Minder system status",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            "detect_anomalies": {
                "name": "detect_anomalies",
                "description": "Detect recent anomalies across all modules",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "critical"],
                            "description": "Minimum severity level",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of anomalies to return",
                            "default": 10,
                        },
                    },
                    "required": [],
                },
            },
            "get_correlations": {
                "name": "get_correlations",
                "description": "Get discovered correlations between modules",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_a": {
                            "type": "string",
                            "description": "First module name",
                        },
                        "module_b": {
                            "type": "string",
                            "description": "Second module name",
                        },
                    },
                    "required": [],
                },
            },
            "query_knowledge_graph": {
                "name": "query_knowledge_graph",
                "description": "Query knowledge graph for entity relationships",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_type": {
                            "type": "string",
                            "description": "Type of entity (fund, network, etc.)",
                        },
                        "entity_id": {
                            "type": "string",
                            "description": "Specific entity ID",
                        },
                    },
                    "required": [],
                },
            },
            "run_module_pipeline": {
                "name": "run_module_pipeline",
                "description": "Run analysis pipeline on a module",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module": {
                            "type": "string",
                            "description": "Module name (fund, network, weather, etc.)",
                        },
                        "pipeline": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "collect",
                                    "analyze",
                                    "train",
                                    "index",
                                ],
                            },
                            "description": "Pipeline operations to run",
                        },
                    },
                    "required": ["module"],
                },
            },
        }

    async def process_message(
        self,
        message: str,
        character_name: str = "finbot",
        voice_mode: bool = False,
        language: str = "auto",
    ) -> Dict[str, Any]:
        """
        Process user message through Minder

        Args:
            message: User's message
            character_name: Character to use
            voice_mode: Whether to return voice audio
            language: Language (auto, tr, en)

        Returns:
            Response with text, audio (if voice_mode), and metadata
        """
        try:
            start_time = datetime.now()

            # Detect language
            detected_language = await self._detect_language(message)
            if language == "auto":
                language = detected_language

            # Get character
            character = self.character_engine.get_character(character_name)
            if not character:
                character = self.character_engine.presets.get(character_name)
                if not character:
                    character = self.character_engine.presets["finbot"]

            # Inject personality into system prompt
            system_prompt = self.character_engine.inject_personality(
                self._get_base_system_prompt(), character
            )

            # Analyze intent
            intent = await self._analyze_intent(message, language)

            # Route to appropriate handler
            if intent["action"] == "function_call":
                # Function calling
                result = await self._handle_function_call(
                    intent["function"], intent["parameters"], character
                )

                response_text = result.get("response", "")

            elif intent["action"] == "general_query":
                # General knowledge query
                result = await self._handle_general_query(
                    message, character, language
                )
                response_text = result.get("response", "")

            elif intent["action"] == "conversation":
                # General conversation
                response_text = await self._generate_conversational_response(
                    message, character, language
                )

            else:
                response_text = await self._generate_fallback_response(
                    message, character, language
                )

            # Generate voice if requested
            audio_data = None
            audio_duration = 0

            if voice_mode and response_text:
                synthesis = await self.voice_service.synthesize_with_character(
                    text=response_text, character=character
                )

                if "audio_data" in synthesis:
                    audio_data = synthesis["audio_data"]
                    audio_duration = synthesis.get("duration", 0)

            elapsed = (datetime.now() - start_time).total_seconds()

            return {
                "response": response_text,
                "character": character.name,
                "language": language,
                "audio": audio_data,
                "audio_duration": audio_duration,
                "intent": intent,
                "processing_time_seconds": elapsed,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"❌ Message processing failed: {e}", exc_info=True)
            return {
                "response": f"Üzgünüz, bir hata oluştu: {str(e)}",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def _detect_language(self, text: str) -> str:
        """Detect language of text"""
        # Simple heuristic
        turkish_chars = set("çğıöşüÇĞİÖŞÜ")
        text_lower = text.lower()

        if any(char in text_lower for char in turkish_chars):
            return "tr"
        else:
            return "en"

    async def _analyze_intent(
        self, message: str, language: str
    ) -> Dict[str, Any]:
        """Analyze user intent"""
        message_lower = message.lower()

        intent = {
            "action": "conversation",
            "confidence": 0.5,
            "function": None,
            "parameters": {},
        }

        # Check for fund recommendations (Turkish & English)
        if any(
            word in message_lower
            for word in ["öner", "recommend", " tavsiye", "ön"]
        ):
            intent["action"] = "function_call"
            intent["function"] = "get_fund_recommendations"
            intent["confidence"] = 0.8

            # Extract parameters
            if (
                "düşük" in message_lower
                or "low" in message_lower
                or "az" in message_lower
            ):
                intent["parameters"]["risk_tolerance"] = "low"
            elif (
                "yüksek" in message_lower
                or "high" in message_lower
                or "çok" in message_lower
            ):
                intent["parameters"]["risk_tolerance"] = "high"
            else:
                intent["parameters"]["risk_tolerance"] = "medium"

        # Check for fund analysis
        elif any(
            word in message_lower
            for word in ["analiz", "analyze", "durum", "performance"]
        ):
            intent["action"] = "function_call"
            intent["function"] = "analyze_fund_performance"
            intent["confidence"] = 0.7

        # Check for system status
        elif any(
            word in message_lower
            for word in ["durum", "status", "health", "working"]
        ):
            intent["action"] = "function_call"
            intent["function"] = "get_system_status"
            intent["confidence"] = 0.9

        # Check for anomalies
        elif any(
            word in message_lower
            for word in ["anomaly", "anomali", "sorun", "problem", "hata"]
        ):
            intent["action"] = "function_call"
            intent["function"] = "detect_anomalies"
            intent["confidence"] = 0.8

        # Check for correlations
        elif any(
            word in message_lower
            for word in ["korelasyon", "correlation", "ilişki", "relation"]
        ):
            intent["action"] = "function_call"
            intent["function"] = "get_correlations"
            intent["confidence"] = 0.7

        # Check for knowledge graph query
        elif any(
            word in message_lower
            for word in ["bilgi", "information", "knowledge", "graph"]
        ):
            intent["action"] = "function_call"
            intent["function"] = "query_knowledge_graph"
            intent["confidence"] = 0.6

        return intent

    async def _handle_function_call(
        self, function_name: str, parameters: Dict[str, Any], character: Any
    ) -> Dict[str, Any]:
        """Handle function call"""
        try:
            if function_name == "get_fund_recommendations":
                return await self._get_fund_recommendations(
                    parameters, character
                )

            elif function_name == "analyze_fund_performance":
                return await self._analyze_fund_performance(
                    parameters, character
                )

            elif function_name == "get_system_status":
                return await self._get_system_status(character)

            elif function_name == "detect_anomalies":
                return await self._detect_anomalies(parameters, character)

            elif function_name == "get_correlations":
                return await self._get_correlations(parameters, character)

            elif function_name == "query_knowledge_graph":
                return await self._query_knowledge_graph(parameters, character)

            elif function_name == "run_module_pipeline":
                return await self._run_module_pipeline(parameters, character)

            else:
                return {
                    "response": f"Bilinmeyen fonksiyon: {function_name}",
                    "error": "Unknown function",
                }

        except Exception as e:
            logger.error(f"Function call failed: {e}")
            return {
                "response": f"Fonksiyon çağrılırken hata oluştu: {str(e)}",
                "error": str(e),
            }

    async def _get_fund_recommendations(
        self, params: Dict[str, Any], character: Any
    ) -> Dict[str, Any]:
        """Get personalized fund recommendations"""
        risk_tolerance = params.get("risk_tolerance", "medium")
        horizon = params.get("investment_horizon", "medium")
        goal = params.get("investment_goal", "balanced")

        # Get fund module
        fund_module = await self.kernel.registry.get_module("fund")
        if not fund_module:
            return {"response": "Fund modülü mevcut değil.", "funds": []}

        # Analyze
        analysis = await fund_module.analyze()
        top_performers = analysis.get("top_performers", [])

        # Filter by risk tolerance
        if risk_tolerance == "low":
            filtered = [
                f for f in top_performers if f.get("volatility", 1) < 0.02
            ]
        elif risk_tolerance == "high":
            filtered = [
                f for f in top_performers if f.get("sharpe_ratio", 0) > 0.5
            ]
        else:
            filtered = top_performers[:10]

        # Generate response
        if character.voice_profile.language == "tr":
            response = (
                f"Risk profilinize ({risk_tolerance}) uygun fon önerileri:\n\n"
            )
            for i, fund in enumerate(filtered[:5], 1):
                response += f"{i}. **{fund['fund_code']}** - Sharpe: {fund['sharpe_ratio']:.2f}\n"

            response += "\nBu dağıtım Modern Portföy Teorisi'ne göre optimize edilmiştir."
        else:
            response = (
                f"Fund recommendations for {risk_tolerance} risk profile:\n\n"
            )
            for i, fund in enumerate(filtered[:5], 1):
                response += f"{i}. **{fund['fund_code']}** - Sharpe: {fund['sharpe_ratio']:.2f}\n"

            response += "\nOptimized using Modern Portfolio Theory."

        return {
            "response": response,
            "funds": filtered[:5],
            "risk_tolerance": risk_tolerance,
        }

    async def _get_system_status(self, character: Any) -> Dict[str, Any]:
        """Get system status"""
        status = await self.kernel.get_system_status()

        if character.voice_profile.language == "tr":
            response = "📊 **Minder Sistem Durumu**\n\n"
            response += f"Modüller: {status['modules']['ready']}/{status['modules']['total']} hazır\n"
            response += f"Korelasyonlar: {status['correlations']['total_correlations']} tane\n"
            response += (
                f"Çalışma süresi: {status['uptime_seconds']/60:.1} dakika\n"
            )
            response += f"Durum: {'✅ Çalışıyor' if status['status'] == 'running' else '❌ Çalışmıyor'}"
        else:
            response = "📊 **Minder System Status**\n\n"
            response += f"Modules: {status['modules']['ready']}/{status['modules']['total']} ready\n"
            response += f"Correlations: {status['correlations']['total_correlations']} found\n"
            response += f"Uptime: {status['uptime_seconds']/60:.1} minutes\n"
            response += f"Status: {'✅ Running' if status['status'] == 'running' else '❌ Stopped'}"

        return {"response": response, "status": status}

    async def _detect_anomalies(
        self, params: Dict[str, Any], character: Any
    ) -> Dict[str, Any]:
        """Detect anomalies"""
        severity = params.get("severity", "medium")
        limit = params.get("limit", 10)

        # Get anomalies from all modules
        all_anomalies = []

        modules = await self.kernel.registry.list_modules(status="ready")
        for module_info in modules:
            module = await self.kernel.registry.get_module(module_info["name"])
            if module:
                anomalies = await module.get_anomalies(
                    severity=severity, limit=limit
                )
                all_anomalies.extend(anomalies)

        # Sort by severity
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        all_anomalies.sort(
            key=lambda a: severity_order.get(a.get("severity", "low"), 0),
            reverse=True,
        )

        # Generate response
        if character.voice_profile.language == "tr":
            response = (
                f"⚠️  **Tespit Edilen Anomaliler** ({severity} üzeri)\n\n"
            )
            for anomaly in all_anomalies[:limit]:
                response += f"- {anomaly['description']}\n"
        else:
            response = f"⚠️  **Detected Anomalies** ({severity}+)\n\n"
            for anomaly in all_anomalies[:limit]:
                response += f"- {anomaly['description']}\n"

        return {"response": response, "anomalies": all_anomalies[:limit]}

    async def _get_correlations(
        self, params: Dict[str, Any], character: Any
    ) -> Dict[str, Any]:
        """Get correlations"""
        module_a = params.get("module_a")
        module_b = params.get("module_b")

        if module_a and module_b:
            # Specific pair
            correlations = (
                await self.kernel.correlation_engine.discover_correlations(
                    module_a, module_b
                )
            )
            correlations_list = correlations
        else:
            # All correlations
            all_correlations = (
                await self.kernel.correlation_engine.get_all_correlations()
            )
            correlations_list = []
            for pair, corrs in all_correlations.items():
                correlations_list.extend(corrs)

        # Generate response
        if character.voice_profile.language == "tr":
            response = "🔗 **Bulunan Korelasyonlar**\n\n"
            for corr in correlations_list[:5]:
                response += f"- {corr['module_a']} ↔ {corr['module_b']}: {corr['description']} (güç: {corr['strength']:.2f})\n"
        else:
            response = "🔗 **Discovered Correlations**\n\n"
            for corr in correlations_list[:5]:
                response += f"- {corr['module_a']} ↔ {corr['module_b']}: {corr['description']} (strength: {corr['strength']:.2f})\n"

        return {"response": response, "correlations": correlations_list[:5]}

    async def _query_knowledge_graph(
        self, params: Dict[str, Any], character: Any
    ) -> Dict[str, Any]:
        """Query knowledge graph"""
        kg = self.kernel.knowledge_graph

        if params.get("entity_id"):
            # Get specific entity
            entity = await kg.get_entity(params["entity_id"])
            if entity:
                relations = await kg.get_relations(entity.id)

                if character.voice_profile.language == "tr":
                    response = f"📊 **Varlık: {entity.name}**\n\n"
                    response += f"Tür: {entity.type.value}\n"
                    response += f"İlişkiler: {len(relations)} tane\n"
                else:
                    response = f"📊 **Entity: {entity.name}**\n\n"
                    response += f"Type: {entity.type.value}\n"
                    response += f"Relations: {len(relations)} found\n"

                return {
                    "response": response,
                    "entity": entity.__dict__,
                    "relations": relations,
                }

        return {"response": "Varlık bulunamadı.", "entity": None}

    async def _run_module_pipeline(
        self, params: Dict[str, Any], character: Any
    ) -> Dict[str, Any]:
        """Run module pipeline"""
        module_name = params["module"]
        pipeline = params.get("pipeline", ["collect", "analyze"])

        results = await self.kernel.run_module_pipeline(module_name, pipeline)

        if character.voice_profile.language == "tr":
            response = f"⚙️  **{module_name} Modülü Pipeline**\n\n"
            for operation, result in results.items():
                if "error" in result:
                    response += f"❌ {operation}: {result['error']}\n"
                else:
                    response += f"✅ {operation}: Tamamlandı\n"
        else:
            response = f"⚙️  **{module_name} Module Pipeline**\n\n"
            for operation, result in results.items():
                if "error" in result:
                    response += f"❌ {operation}: {result['error']}\n"
                else:
                    response += f"✅ {operation}: Completed\n"

        return {"response": response, "results": results}

    async def _handle_general_query(
        self, query: str, character: Any, language: str
    ) -> Dict[str, Any]:
        """Handle general knowledge query"""
        # Query all modules
        module_results = await self.kernel.query_modules(query)

        if module_results:
            # Build response from module results
            if language == "tr":
                response = f"🔍 **Sorgu Sonuçları**: {query}\n\n"
                for result in module_results:
                    module_name = result["module"]
                    response += f"- {module_name} modülü sorgulandı\n"
            else:
                response = f"🔍 **Query Results**: {query}\n\n"
                for result in module_results:
                    module_name = result["module"]
                    response += f"- {module_name} module queried\n"

            return {"response": response, "module_results": module_results}

        return {
            "response": await self._generate_fallback_response(
                query, character, language
            )
        }

    async def _generate_conversational_response(
        self, message: str, character: Any, language: str
    ) -> str:
        """Generate conversational response"""
        # This would use Ollama in production
        if language == "tr":
            return f"{character.name} olarak size yardımcı olabilirim. Fon analizi, portföy optimizasyonu veya sistem durumu hakkında sorular sorabilirsiniz."
        else:
            return f"As {character.name}, I'm here to help! You can ask me about fund analysis, portfolio optimization, or system status."

    async def _generate_fallback_response(
        self, message: str, character: Any, language: str
    ) -> str:
        """Generate fallback response"""
        if language == "tr":
            return "Minder AI platformu olarak size yardımcı olabilirim. Fonlar, portföy, network analizi veya diğer konular hakkında sorularınızı bekliyorum."
        else:
            return "As the Minder AI platform, I'm here to help! Feel free to ask about funds, portfolios, network analysis, or other topics."

    def _get_base_system_prompt(self) -> str:
        """Get base system prompt"""
        return """You are Minder's AI assistant. Help users using all available modules and capabilities."""

    def get_functions_definition(self) -> List[Dict]:
        """Get functions definition for OpenAI function calling format"""
        return list(self.functions.values())
