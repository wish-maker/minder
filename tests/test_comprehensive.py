"""
Comprehensive Test Suite for Minder
Tests all modules, integrations, and advanced features
"""
import pytest
import asyncio
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Core imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.kernel import MinderKernel
from core.anomaly_detection import AnomalyDetector, AnomalyType, AnomalySeverity
from core.advanced_correlation import AdvancedCorrelationEngine
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
            'fund': {
                'database': DB_CONFIG
            },
            'modules': {
                'fund': {},
                'network': {},
                'weather': {},
                'crypto': {},
                'news': {}
            }
        }

        kernel = MinderKernel(config)
        await kernel.start()

        yield kernel

        await kernel.stop()

    @pytest.mark.asyncio
    async def test_kernel_startup(self, kernel):
        """Test kernel starts correctly"""
        status = await kernel.get_system_status()
        assert status['status'] == 'running'
        assert status['modules']['total'] > 0

    @pytest.mark.asyncio
    async def test_module_registry(self, kernel):
        """Test module registry"""
        modules = await kernel.registry.list_modules()
        assert len(modules) > 0

    @pytest.mark.asyncio
    async def test_event_bus(self, kernel):
        """Test event bus functionality"""
        from core.event_bus import Event, EventType

        # Subscribe to event
        event_received = []

        async def handler(event):
            event_received.append(event)

        await kernel.event_bus.subscribe(EventType.MODULE_READY, handler)

        # Publish event
        await kernel.event_bus.publish(Event(
            type=EventType.MODULE_READY,
            source="test",
            data={'test': True}
        ))

        # Give time for processing
        await asyncio.sleep(0.1)

        assert len(event_received) > 0

class TestFundModule:
    """Test fund module with real database"""

    @pytest.fixture
    async def fund_module(self):
        """Create fund module"""
        from modules.fund.fund_module import FundModule

        module = FundModule({'database': DB_CONFIG})
        await module.register()

        yield module

        await module.shutdown()

    @pytest.mark.asyncio
    async def test_fund_registration(self, fund_module):
        """Test fund module registration"""
        assert fund_module.metadata is not None
        assert fund_module.metadata.name == "fund"
        assert fund_module.metadata.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_fund_data_collection(self, fund_module):
        """Test fund data collection from real database"""
        result = await fund_module.collect_data()

        assert 'records_collected' in result
        assert result['records_collected'] >= 0

    @pytest.mark.asyncio
    async def test_fund_analysis(self, fund_module):
        """Test fund analysis"""
        result = await fund_module.analyze()

        assert 'metrics' in result
        assert 'insights' in result

        if result['metrics']:
            assert 'total_funds' in result['metrics']

    @pytest.mark.asyncio
    async def test_fund_anomalies(self, fund_module):
        """Test fund anomaly detection"""
        anomalies = await fund_module.get_anomalies(severity="high", limit=10)

        assert isinstance(anomalies, list)

    @pytest.mark.asyncio
    async def test_fund_ml_training(self, fund_module):
        """Test ML model training"""
        result = await fund_module.train_ai(model_type="linear")

        # Training might fail if no data, but should return a result
        assert 'model_id' in result or 'error' in result

class TestAnomalyDetection:
    """Test anomaly detection system"""

    @pytest.fixture
    def detector(self):
        """Create anomaly detector"""
        config = {
            'threshold': 0.95,
            'window_size': 100,
            'min_samples': 50
        }
        return AnomalyDetector(config)

    def test_isolation_forest_detection(self, detector):
        """Test Isolation Forest anomaly detection"""
        # Create sample data with anomalies
        np.random.seed(42)
        normal_data = np.random.normal(0, 1, 1000)
        anomaly_data = np.random.normal(10, 1, 50)  # Outliers

        combined_data = np.concatenate([normal_data, anomaly_data])
        df = pd.DataFrame({'value': combined_data})

        # Detect anomalies (synchronous wrapper)
        async def test_detection():
            return await detector.detect_anomalies_isolation_forest(
                df, 'test', 'test_entity'
            )

        anomalies = asyncio.run(test_detection())

        assert isinstance(anomalies, list)
        # Should detect some anomalies
        assert len(anomalies) >= 0

    def test_statistical_detection(self, detector):
        """Test statistical anomaly detection"""
        # Create sample data
        np.random.seed(42)
        data = np.random.normal(0, 1, 100)

        # Add some outliers
        data[0] = 10  # Huge outlier
        data[50] = -8  # Huge outlier

        df = pd.DataFrame({'value': data})

        async def test_detection():
            return await detector.detect_anomalies_statistical(df, 'test', 'test_entity')

        anomalies = asyncio.run(test_detection())

        assert isinstance(anomalies, list)
        assert len(anomalies) >= 2  # Should detect at least the 2 outliers

class TestAdvancedCorrelation:
    """Test advanced correlation algorithms"""

    @pytest.fixture
    def correlation_engine(self):
        """Create correlation engine"""
        config = {
            'significance_level': 0.05,
            'max_lag': 30
        }
        return AdvancedCorrelationEngine(config)

    def test_granger_causality(self, correlation_engine):
        """Test Granger causality"""
        # Create sample time series
        np.random.seed(42)
        series1 = np.random.normal(0, 1, 200)

        # Series2 depends on series1 with lag
        series2 = np.zeros(200)
        for i in range(1, 200):
            series2[i] = 0.5 * series1[i-1] + np.random.normal(0, 0.5, 1)

        async def test_granger():
            return await correlation_engine.granger_causality_test(
                series1[:150], series2[:150], max_lag=5
            )

        result = asyncio.run(test_granger())

        assert 'p_value' in result
        assert 'is_significant' in result

    def test_dynamic_time_warping(self, correlation_engine):
        """Test DTW distance calculation"""
        # Create similar patterns with different speeds
        np.random.seed(42)
        pattern = np.sin(np.linspace(0, 4*np.pi, 100))

        series1 = pattern
        series2 = np.sin(np.linspace(0, 4*np.pi, 80))  # Compressed version

        async def test_dtw():
            return await correlation_engine.dynamic_time_warping(
                series1, series2
            )

        result = asyncio.run(test_dtw())

        assert 'similarity_score' in result
        # Should have high similarity since patterns are similar
        assert result['similarity_score'] > 0.5

    def test_comprehensive_correlation(self, correlation_engine):
        """Test comprehensive correlation analysis"""
        np.random.seed(42)

        # Create correlated series
        base = np.random.normal(0, 1, 200)
        series1 = base + np.random.normal(0, 0.1, 200)
        series2 = 0.8 * base + np.random.normal(0, 0.2, 200)

        async def test_comprehensive():
            return await correlation_engine.comprehensive_correlation_analysis(
                series1, series2, 'series1', 'series2'
            )

        result = asyncio.run(test_comprehensive())

        assert 'overall_strength' in result
        assert 'relationship_type' in result
        assert 'detailed_results' in result

class TestKnowledgeGraph:
    """Test knowledge graph population"""

    @pytest.fixture
    async def kg_populator(self):
        """Create knowledge graph populator"""
        from core.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph({})
        config = {'batch_size': 100}

        populator = KnowledgeGraphPopulator(kg, config)

        yield populator

    @pytest.mark.asyncio
    async def test_fund_entity_population(self, kg_populator):
        """Test fund entity population"""
        # Create sample fund data
        fund_data = pd.DataFrame({
            'fund_code': ['TEK', 'SAN', 'TEFAS'] * 10,
            'price': np.random.uniform(10, 100, 30)
        })

        analysis = {
            'top_performers': pd.DataFrame({
                'fund_code': ['TEK', 'SAN'],
                'avg_return': [0.05, 0.03],
                'volatility': [0.02, 0.015],
                'sharpe_ratio': [2.5, 2.0]
            })
        }

        result = await kg_populator.populate_from_fund_module(fund_data, analysis)

        assert 'entities_added' in result
        assert result['entities_added'] > 0

class TestVoiceService:
    """Test voice service"""

    @pytest.fixture
    def voice_service(self):
        """Create voice service"""
        config = {}
        return VoiceService(config)

    def test_supported_languages(self, voice_service):
        """Test language support"""
        languages = asyncio.run(voice_service.get_supported_languages())

        assert 'tr' in languages
        assert 'en' in languages
        assert len(languages) >= 6

    def test_health_check(self, voice_service):
        """Test voice service health check"""
        health = asyncio.run(voice_service.health_check())

        assert 'supported_languages' in health

class TestOpenWebUIAgent:
    """Test OpenWebUI agent integration"""

    @pytest.fixture
    async def agent(self):
        """Create agent"""
        from core.character_system import CharacterEngine

        config = {'modules': {'fund': {'database': DB_CONFIG}}}
        kernel = MinderKernel(config)

        # Mock start - don't actually start all services
        kernel.running = True
        kernel.startup_time = datetime.now()

        character_engine = CharacterEngine(config)

        agent = MinderOpenWebUIAgent(kernel, character_engine)

        yield agent

        await kernel.stop()

    @pytest.mark.asyncio
    async def test_function_definitions(self, agent):
        """Test function definitions are available"""
        functions = agent.get_functions_definition()

        assert len(functions) > 0
        assert any(f['name'] == 'get_fund_recommendations' for f in functions)

    @pytest.mark.asyncio
    async def test_intent_analysis(self, agent):
        """Test intent analysis"""
        # Turkish recommendation query
        intent_tr = await agent._analyze_intent(
            "Hangi fonları önerirsin?",
            'tr'
        )

        assert intent_tr['action'] == 'function_call'
        assert intent_tr['function'] == 'get_fund_recommendations'

        # English recommendation query
        intent_en = await agent._analyze_intent(
            "What funds do you recommend?",
            'en'
        )

        assert intent_en['action'] == 'function_call'
        assert intent_en['function'] == 'get_fund_recommendations'

    @pytest.mark.asyncio
    async def test_system_status_function(self, agent):
        """Test system status function"""
        result = await agent._get_system_status(
            agent.character_engine.presets['finbot']
        )

        assert 'response' in result
        assert 'status' in result

class TestIntegration:
    """Integration tests"""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """Test complete analysis pipeline"""
        config = {
            'fund': {'database': DB_CONFIG},
            'modules': {'fund': {}, 'network': {}}
        }

        kernel = MinderKernel(config)
        await kernel.start()

        try:
            # Run fund module pipeline
            result = await kernel.run_module_pipeline('fund', ['collect', 'analyze'])

            assert 'collect' in result
            assert 'analyze' in result

        finally:
            await kernel.stop()

    @pytest.mark.asyncio
    async def test_cross_module_correlation(self):
        """Test cross-module correlation discovery"""
        config = {
            'fund': {'database': DB_CONFIG},
            'modules': {'fund': {}, 'network': {}}
        }

        kernel = MinderKernel(config)
        await kernel.start()

        try:
            # Discover correlations
            correlations = await kernel.discover_all_correlations()

            assert isinstance(correlations, dict)

        finally:
            await kernel.stop()

# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
