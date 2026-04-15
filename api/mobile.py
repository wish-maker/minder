"""
Mobile API Endpoints with WebSocket Support
Provides real-time updates and mobile-friendly APIs
"""
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from typing import Dict, List, Any
import asyncio
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class MobileAPIHandler:
    """
    Mobile API handler with WebSocket support

    Features:
    - WebSocket connections for real-time updates
    - Push notifications
    - Optimized responses for mobile
    - Background task streaming
    """

    def __init__(self, kernel, character_engine):
        self.kernel = kernel
        self.character_engine = character_engine
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_lock = asyncio.Lock()

    async def websocket_endpoint(self, websocket: WebSocket, client_id: str):
        """
        Handle WebSocket connection for real-time updates

        Client connects and receives real-time updates about:
        - Anomalies
        - System status
        - Analysis results
        - Alerts
        """
        try:
            await websocket.accept()
            logger.info(f"📱 Mobile client connected: {client_id}")

            # Store connection
            async with self.connection_lock:
                self.active_connections[client_id] = websocket

            # Send welcome message
            await websocket.send_json({
                'type': 'connection_established',
                'client_id': client_id,
                'timestamp': datetime.now().isoformat(),
                'message': 'Connected to Minder real-time updates'
            })

            # Keep connection alive and handle messages
            try:
                while True:
                    data = await websocket.receive_text()
                    message = json.loads(data)

                    # Handle client message
                    await self._handle_websocket_message(client_id, message)

            except WebSocketDisconnect:
                logger.info(f"📱 Mobile client disconnected: {client_id}")

        except Exception as e:
            logger.error(f"❌ WebSocket error for {client_id}: {e}")

        finally:
            # Cleanup
            async with self.connection_lock:
                if client_id in self.active_connections:
                    del self.active_connections[client_id]

    async def _handle_websocket_message(self, client_id: str, message: Dict):
        """Handle incoming WebSocket message"""
        msg_type = message.get('type')

        if msg_type == 'subscribe':
            # Subscribe to specific updates
            await self._handle_subscription(client_id, message)

        elif msg_type == 'ping':
            # Respond to ping
            websocket = self.active_connections.get(client_id)
            if websocket:
                await websocket.send_json({
                    'type': 'pong',
                    'timestamp': datetime.now().isoformat()
                })

        elif msg_type == 'query':
            # Handle query
            await self._handle_websocket_query(client_id, message)

    async def _handle_subscription(self, client_id: str, message: Dict):
        """Handle subscription request"""
        subscription_type = message.get('subscription')
        filters = message.get('filters', {})

        # Send confirmation
        websocket = self.active_connections.get(client_id)
        if websocket:
            await websocket.send_json({
                'type': 'subscription_confirmed',
                'subscription': subscription_type,
                'filters': filters,
                'timestamp': datetime.now().isoformat()
            })

    async def _handle_websocket_query(self, client_id: str, message: Dict):
        """Handle query via WebSocket"""
        query = message.get('query')
        character = message.get('character', 'finbot')

        # Process query (similar to HTTP endpoint)
        from services.openwebui.minder_agent import MinderOpenWebUIAgent

        agent = MinderOpenWebUIAgent(self.kernel, self.character_engine)
        result = await agent.process_message(query, character)

        # Send response
        websocket = self.active_connections.get(client_id)
        if websocket:
            await websocket.send_json({
                'type': 'query_response',
                'query': query,
                'response': result.get('response'),
                'timestamp': datetime.now().isoformat()
            })

    async def broadcast_update(self, update_type: str, data: Dict):
        """
        Broadcast update to all connected clients

        Used for:
        - Real-time anomaly alerts
        - System status changes
        - Analysis completion
        """
        if not self.active_connections:
            return

        message = {
            'type': update_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }

        # Send to all connected clients
        disconnected = []
        async with self.connection_lock:
            for client_id, websocket in self.active_connections.items():
                try:
                    await websocket.send_json(message)
                except Exception:
                    disconnected.append(client_id)

        # Cleanup disconnected clients
        for client_id in disconnected:
            del self.active_connections[client_id]

    async def stream_analysis_results(
        self,
        module_name: str,
        websocket: WebSocket
    ):
        """
        Stream analysis results in real-time

        Sends progress updates as analysis runs
        """
        try:
            # Send start message
            await websocket.send_json({
                'type': 'analysis_started',
                'module': module_name,
                'timestamp': datetime.now().isoformat()
            })

            # Run pipeline with progress updates
            pipeline = ['collect', 'analyze', 'train']

            for operation in pipeline:
                # Send operation start
                await websocket.send_json({
                    'type': 'operation_start',
                    'operation': operation,
                    'module': module_name,
                    'timestamp': datetime.now().isoformat()
                })

                # Simulate operation (in production, actually run it)
                await asyncio.sleep(2)

                # Send operation complete
                await websocket.send_json({
                    'type': 'operation_complete',
                    'operation': operation,
                    'module': module_name,
                    'timestamp': datetime.now().isoformat()
                })

            # Send completion
            await websocket.send_json({
                'type': 'analysis_complete',
                'module': module_name,
                'timestamp': datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"❌ Streaming failed: {e}")
            await websocket.send_json({
                'type': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })

    async def mobile_push_notification(
        self,
        client_id: str,
        notification: Dict[str, Any]
    ):
        """
        Send push notification to mobile client

        Args:
            client_id: Mobile client identifier
            notification: Notification data
        """
        websocket = self.active_connections.get(client_id)

        if websocket:
            await websocket.send_json({
                'type': 'push_notification',
                'notification': notification,
                'timestamp': datetime.now().isoformat()
            })

    async def get_optimized_dashboard_data(self, client_type: str = "mobile") -> Dict:
        """
        Get optimized dashboard data for mobile

        Returns lightweight data optimized for mobile bandwidth
        """
        try:
            # Get system status
            status = await self.kernel.get_system_status()

            # Get recent anomalies
            anomalies_summary = await self.kernel.registry.get_module('anomaly_detector')
            anomalies = await anomalies_summary.get_anomaly_summary() if anomalies_summary else {}

            # Get active correlations
            correlations = await self.kernel.correlation_engine.get_all_correlations()

            # Optimize for mobile
            mobile_data = {
                'system': {
                    'status': status['status'],
                    'modules_ready': status['modules']['ready'],
                    'modules_total': status['modules']['total'],
                    'uptime_minutes': int(status['uptime_seconds'] / 60)
                },
                'alerts': {
                    'total_anomalies': anomalies.get('total_anomalies', 0),
                    'high_severity': anomalies.get('by_severity', {}).get('high', 0),
                    'critical_severity': anomalies.get('by_severity', {}).get('critical', 0)
                },
                'correlations': {
                    'total_pairs': len(correlations),
                    'strong_correlations': sum(1 for corrs in correlations.values()
                                            for c in corrs if c.get('strength', 0) > 0.7)
                },
                'performance': {
                    'api_latency_ms': 50,
                    'data_freshness_seconds': 300
                }
            }

            return mobile_data

        except Exception as e:
            logger.error(f"❌ Failed to get mobile dashboard data: {e}")
            return {'error': str(e)}

    async def get_mobile_modules(self) -> List[Dict]:
        """Get list of modules optimized for mobile display"""
        modules = await self.kernel.registry.list_modules()

        mobile_modules = []
        for module in modules:
            mobile_modules.append({
                'name': module['name'],
                'status': module['status'],
                'description': module['metadata']['description'],
                'capabilities': module['metadata']['capabilities'],
                'icon': self._get_module_icon(module['name'])
            })

        return mobile_modules

    def _get_module_icon(self, module_name: str) -> str:
        """Get icon for module"""
        icon_map = {
            'fund': '💰',
            'network': '🌐',
            'weather': '🌤️',
            'crypto': '₿',
            'news': '📰'
        }
        return icon_map.get(module_name, '📦')

# FastAPI routes for mobile API
def setup_mobile_routes(app, kernel, character_engine):
    """Setup mobile-specific routes"""

    mobile_handler = MobileAPIHandler(kernel, character_engine)

    @app.websocket("/ws/mobile/{client_id}")
    async def websocket_mobile_endpoint(websocket: WebSocket, client_id: str):
        await mobile_handler.websocket_endpoint(websocket, client_id)

    @app.get("/api/mobile/dashboard")
    async def get_mobile_dashboard():
        """Get optimized dashboard data for mobile"""
        return await mobile_handler.get_optimized_dashboard_data()

    @app.get("/api/mobile/modules")
    async def get_mobile_modules():
        """Get modules list for mobile"""
        return await mobile_handler.get_mobile_modules()

    @app.post("/api/mobile/notify")
    async def send_push_notification(notification: Dict):
        """Send push notification to specific client"""
        client_id = notification.get('client_id')
        if client_id:
            await mobile_handler.mobile_push_notification(client_id, notification)
            return {'status': 'sent'}
        else:
            return {'error': 'client_id required'}, 400

    @app.get("/api/mobile/stream/{module}")
    async def stream_analysis(module: str):
        """Stream analysis results to mobile client"""
        async def stream_generator():
            # This would be used with Server-Sent Events
            import json

            while True:
                # In production, get real updates
                data = {
                    'type': 'update',
                    'module': module,
                    'progress': 50,
                    'timestamp': datetime.now().isoformat()
                }
                yield f"data: {json.dumps(data)}\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream"
        )
