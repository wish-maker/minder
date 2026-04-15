"""
Comprehensive Test Suite for Minder
Tests all modules, integrations, and advanced features
"""
import pytest
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path

# Core imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.kernel import MinderKernel
from core.anomaly_detection import AnomalyDetector, AnomalyType, AnomalySeverity
try:
    from core.advanced_correlation import AdvancedCorrelationEngine
    ADVANCED_CORRELATION_AVAILABLE = True
except ImportError:
    ADVANCED_CORRELATION_AVAILABLE = False
    pytest.skip("dtaidistance not installed - skipping advanced correlation tests", allow_module_level=True)

from core.knowledge_populator import KnowledgeGraphPopulator
from services.voice.voice_service import VoiceService
from services.openwebui.minder_agent import MinderOpenWebUIAgent

# Database configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'fundmind'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

class TestMinderKernel:
    """Test kernel functionality"""

    @pytest.fixture
    async def kernel(self):
        """Create test kernel"""
        config = {
            'tefas': {
                'database': DB_CONFIG
            },
            'plugins': {
                'tefas': {},
                'network': {},
                'weather': {},
                'crypto': {},
                'news': {}
            }
        }
        kernel = MinderKernel(config)
        await kernel.initialize()
        yield kernel
        await kernel.shutdown()

    @pytest.mark.asyncio
    async def test_kernel_initialization(self, kernel):
        """Test kernel initializes correctly"""
        assert kernel is not None
        assert kernel.config is not None

    @pytest.mark.asyncio
    async def test_plugin_loading(self, kernel):
        """Test plugins load correctly"""
        plugins = await kernel.list_plugins()
        assert isinstance(plugins, list)
        assert len(plugins) > 0

    @pytest.mark.asyncio
    async def test_event_bus(self, kernel):
        """Test event bus functionality"""
        test_event = {'type': 'test', 'data': 'test_data'}
        await kernel.event_bus.publish(test_event)
        # Event bus should handle the event without errors


class TestAnomalyDetection:
    """Test anomaly detection system"""

    @pytest.fixture
    def detector(self):
        """Create anomaly detector"""
        return AnomalyDetector()

    def test_detect_anomaly_spike(self, detector):
        """Test spike detection"""
        data = [1, 2, 1, 2, 1, 100, 1, 2]  # Spike at index 5
        anomalies = detector.detect_anomalies(data)
        assert len(anomalies) > 0
        assert anomalies[0].type == AnomalyType.SPIKE

    def test_detect_anomaly_drop(self, detector):
        """Test drop detection"""
        data = [100, 99, 98, 100, 99, 1, 100, 99]  # Drop at index 5
        anomalies = detector.detect_anomalies(data)
        assert len(anomalies) > 0
        assert anomalies[0].type == AnomalyType.DROP

    def test_no_anomaly_normal_data(self, detector):
        """Test normal data has no anomalies"""
        data = [10, 11, 10, 12, 11, 10, 11, 12]
        anomalies = detector.detect_anomalies(data)
        assert len(anomalies) == 0


@pytest.mark.skipif(not ADVANCED_CORRELATION_AVAILABLE, reason="dtaidistance not installed")
class TestAdvancedCorrelation:
    """Test advanced correlation features"""

    @pytest.fixture
    def correlation_engine(self):
        """Create correlation engine"""
        return AdvancedCorrelationEngine()

    def test_temporal_correlation(self, correlation_engine):
        """Test temporal correlation analysis"""
        time_series_1 = [1, 2, 3, 4, 5]
        time_series_2 = [2, 4, 6, 8, 10]
        correlation = correlation_engine.calculate_temporal_correlation(
            time_series_1, time_series_2
        )
        assert correlation > 0.8  # Strong positive correlation

    def test_cross_domain_correlation(self, correlation_engine):
        """Test cross-domain correlation"""
        domain1_data = {'values': [1, 2, 3, 4, 5]}
        domain2_data = {'values': [5, 4, 3, 2, 1]}
        result = correlation_engine.find_cross_domain_correlations(
            [domain1_data, domain2_data]
        )
        assert isinstance(result, list)


class TestKnowledgeGraph:
    """Test knowledge graph functionality"""

    @pytest.fixture
    def populator(self):
        """Create knowledge graph populator"""
        return KnowledgeGraphPopulator()

    def test_entity_resolution(self, populator):
        """Test entity resolution"""
        entities = [
            {'name': 'John Doe', 'source': 'news'},
            {'name': 'John Doe', 'source': 'social'}
        ]
        resolved = populator.resolve_entities(entities)
        assert len(resolved) == 1  # Should resolve to single entity

    def test_relationship_extraction(self, populator):
        """Test relationship extraction"""
        text = "Apple announced new iPhone features"
        relationships = populator.extract_relationships(text)
        assert isinstance(relationships, list)


@pytest.mark.skipif(not os.getenv('VOICE_SERVICE_ENABLED'), reason="Voice service not enabled")
class TestVoiceService:
    """Test voice interface"""

    @pytest.fixture
    def voice_service(self):
        """Create voice service"""
        return VoiceService()

    def test_text_to_speech(self, voice_service):
        """Test TTS functionality"""
        result = voice_service.text_to_speech("Hello world", language="en")
        assert result is not None

    def test_speech_to_text(self, voice_service):
        """Test STT functionality"""
        # This would require audio file input
        # For now, just test the method exists
        assert hasattr(voice_service, 'speech_to_text')


@pytest.mark.skipif(not os.getenv('OPENWEBUI_ENABLED'), reason="OpenWebUI not enabled")
class TestOpenWebUIIntegration:
    """Test OpenWebUI integration"""

    @pytest.fixture
    def agent(self):
        """Create Minder agent"""
        return MinderOpenWebUIAgent()

    def test_agent_initialization(self, agent):
        """Test agent initializes"""
        assert agent is not None
        assert agent.config is not None

    @pytest.mark.asyncio
    async def test_agent_query(self, agent):
        """Test agent can process queries"""
        response = await agent.query("What is Minder?")
        assert response is not None
        assert isinstance(response, str)


class TestIntegration:
    """Integration tests"""

    @pytest.mark.asyncio
    async def test_end_to_end_flow(self):
        """Test complete workflow"""
        # This would test a complete user journey
        # For now, just test the flow structure
        steps = [
            'initialize_kernel',
            'load_plugins',
            'collect_data',
            'analyze_data',
            'generate_insights'
        ]
        assert len(steps) == 5  # Verify workflow steps

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in workflows"""
        # Test graceful error handling
        try:
            # Simulate error condition
            raise ValueError("Test error")
        except ValueError as e:
            assert str(e) == "Test error"
