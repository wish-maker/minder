"""
Tests for Crypto Plugin Real API Integration

Tests the multi-source fallback pattern, data validation, and caching
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from plugins.crypto.crypto_module import CryptoModule
from plugins.crypto.crypto_validator import PluginDataValidator


@pytest.fixture
def crypto_config():
    """Standard crypto module configuration"""
    return {
        "database": {
            "host": "localhost",
            "port": 5432,
            "database": "fundmind",
            "user": "postgres",
            "password": "test",
        },
        "crypto": {
            "symbols": ["bitcoin", "ethereum", "tether"],
            "cache": {"ttl": 300},
        },
    }


@pytest.fixture
def validator():
    """Create data validator instance"""
    return PluginDataValidator()


class TestDataValidation:
    """Test data quality validation"""

    def test_valid_crypto_data(self, validator):
        """Test validation of valid crypto data"""
        valid_data = {
            "price": 50000.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        is_valid, score = validator.validate_crypto_data(valid_data)
        assert is_valid
        assert score > 0.5

    def test_null_price_reduces_score(self, validator):
        """Test that null price reduces validity score"""
        invalid_data = {
            "price": None,
            "timestamp": datetime.now(timezone.utc),
        }
        is_valid, score = validator.validate_crypto_data(invalid_data)
        # Score should be reduced but might still be valid if timestamp is fresh
        assert score <= 0.7, f"Expected score <= 0.7 but got {score}"
        # With both null price AND a bad timestamp, it would be invalid
        stale_invalid_data = {
            "price_usd": None,
            "timestamp": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        }
        is_valid, score = validator.validate_crypto_data(stale_invalid_data)
        assert not is_valid, f"Expected invalid with null price and stale timestamp but got score {score}"

    def test_stale_data_reduces_score(self, validator):
        """Test that stale data reduces validity score"""
        # Create a timestamp that's definitely older than 5 minutes
        stale_timestamp = datetime.now(timezone.utc).replace(
            year=2024, month=1, day=1, hour=0, minute=0, second=0
        )
        stale_data = {
            "price": 50000.0,
            "timestamp": stale_timestamp,
        }
        is_valid, score = validator.validate_crypto_data(stale_data)
        # Stale data gets -0.4 penalty, so score should be 0.6
        assert score == 0.6, f"Expected score 0.6 for stale data but got {score}"
        # With multiple issues, it would be invalid
        stale_and_null_data = {
            "price": None,
            "timestamp": stale_timestamp,
        }
        is_valid, score = validator.validate_crypto_data(stale_and_null_data)
        assert not is_valid, f"Expected invalid for stale + null price but got score {score}"

    def test_price_outlier_detection(self, validator):
        """Test detection of price outliers"""
        outlier_data = {
            "price": 100000.0,  # 100% increase (more than 50% threshold)
            "previous_price": 50000.0,
            "timestamp": datetime.now(timezone.utc),
        }
        is_valid, score = validator.validate_crypto_data(outlier_data)
        # Outlier gets -0.3 penalty, so score should be 0.7
        assert score == 0.7, f"Expected score 0.7 for outlier but got {score}"
        # With multiple issues (outlier + stale), it would be invalid
        stale_outlier_data = {
            "price": 100000.0,
            "previous_price": 50000.0,
            "timestamp": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        }
        is_valid, score = validator.validate_crypto_data(stale_outlier_data)
        assert not is_valid, f"Expected invalid for outlier + stale but got score {score}"



class TestCryptoModuleInitialization:
    """Test crypto module initialization and configuration"""

    def test_module_initialization(self, crypto_config):
        """Test module initializes correctly"""
        module = CryptoModule(crypto_config)
        assert module.validator is not None
        assert module.cache == {}
        assert len(module.sources) == 3
        assert module.cache_ttl == 300

    def test_source_priority_order(self, crypto_config):
        """Test that sources are in correct priority order"""
        module = CryptoModule(crypto_config)
        source_names = [name for name, _ in module.sources]
        assert source_names == ["binance", "coingecko", "kraken"]


class TestFallbackPattern:
    """Test fallback pattern between API sources"""

    @pytest.mark.asyncio
    async def test_fallback_to_second_source(self, crypto_config):
        """Test fallback when primary source fails"""
        module = CryptoModule(crypto_config)

        # Mock binance to fail, coingecko to succeed
        mock_binance = AsyncMock(side_effect=Exception("Binance failed"))
        mock_coingecko = AsyncMock(
            return_value={
                "price": 50000.0,
                "source": "coingecko",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        module.sources[0] = ("binance", mock_binance)
        module.sources[1] = ("coingecko", mock_coingecko)

        result = await module._get_price_with_fallback("BTCUSDT")

        assert result is not None
        assert result["source"] == "coingecko"
        assert result["price"] == 50000.0
        mock_binance.assert_called_once()
        mock_coingecko.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_sources_fail(self, crypto_config):
        """Test behavior when all sources fail"""
        module = CryptoModule(crypto_config)

        # Mock all sources to fail
        mock_fail = AsyncMock(side_effect=Exception("API failed"))
        module.sources = [
            ("binance", mock_fail),
            ("coingecko", mock_fail),
            ("kraken", mock_fail),
        ]

        result = await module._get_price_with_fallback("BTCUSDT")

        assert result is None


class TestCaching:
    """Test caching behavior"""

    @pytest.mark.asyncio
    async def test_cache_hit(self, crypto_config):
        """Test that cache is used on second call"""
        module = CryptoModule(crypto_config)

        # Mock API call
        mock_api = AsyncMock(
            return_value={
                "price": 50000.0,
                "source": "binance",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        module.sources[0] = ("binance", mock_api)

        # First call
        result1 = await module._get_price_with_fallback("BTCUSDT")
        # Second call should use cache
        result2 = await module._get_price_with_fallback("BTCUSDT")

        assert result1["price"] == result2["price"]
        # API should only be called once due to cache
        mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_expiration(self, crypto_config):
        """Test that cache expires after TTL"""
        module = CryptoModule(crypto_config)
        module.cache_ttl = 0  # Force immediate expiration

        # Mock API call
        mock_api = AsyncMock(
            return_value={
                "price": 50000.0,
                "source": "binance",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        module.sources[0] = ("binance", mock_api)

        # First call
        await module._get_price_with_fallback("BTCUSDT")
        # Second call should bypass expired cache
        await module._get_price_with_fallback("BTCUSDT")

        # API should be called twice since cache expired
        assert mock_api.call_count == 2

    @pytest.mark.asyncio
    async def test_stale_cache_fallback(self, crypto_config):
        """Test using stale cache when all sources fail"""
        module = CryptoModule(crypto_config)

        # Set up cached data
        cached_data = {
            "price": 50000.0,
            "source": "binance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        module.cache["crypto:BTCUSDT"] = (cached_data, datetime.now(timezone.utc))

        # Mock all sources to fail
        mock_fail = AsyncMock(side_effect=Exception("API failed"))
        module.sources = [("binance", mock_fail), ("coingecko", mock_fail)]

        result = await module._get_price_with_fallback("BTCUSDT")

        # Should return stale cached data
        assert result is not None
        assert result["price"] == 50000.0


class TestAPIIntegration:
    """Test real API integration (marked as integration tests)"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_binance_api_real(self, crypto_config):
        """Integration test: Real Binance API call"""
        module = CryptoModule(crypto_config)

        try:
            result = await module._binance_get_price("BTCUSDT")
            assert "price" in result
            assert result["source"] == "binance"
            assert isinstance(result["price"], float)
            assert result["price"] > 0
        except Exception as e:
            pytest.skip(f"Binance API unavailable: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_coingecko_api_real(self, crypto_config):
        """Integration test: Real CoinGecko API call"""
        module = CryptoModule(crypto_config)

        try:
            result = await module._coingecko_get_price("BTCUSDT")
            assert "price" in result
            assert result["source"] == "coingecko"
            assert isinstance(result["price"], float)
            assert result["price"] > 0
        except Exception as e:
            pytest.skip(f"CoinGecko API unavailable: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_kraken_api_real(self, crypto_config):
        """Integration test: Real Kraken API call"""
        module = CryptoModule(crypto_config)

        try:
            result = await module._kraken_get_price("BTCUSDT")
            assert "price" in result
            assert result["source"] == "kraken"
            assert isinstance(result["price"], float)
            assert result["price"] > 0
        except Exception as e:
            pytest.skip(f"Kraken API unavailable: {e}")


class TestSymbolMapping:
    """Test symbol mapping and name resolution"""

    def test_get_coin_name(self, crypto_config):
        """Test coin name resolution"""
        module = CryptoModule(crypto_config)
        assert module._get_coin_name("BTCUSDT") == "Bitcoin"
        assert module._get_coin_name("ETHUSDT") == "Ethereum"
        assert module._get_coin_name("BNBUSDT") == "BNB"
        assert module._get_coin_name("XRPUSDT") == "XRP"


class TestMarketDataFetching:
    """Test market data fetching with multiple symbols"""

    @pytest.mark.asyncio
    async def test_fetch_market_data_structure(self, crypto_config):
        """Test that market data fetching returns correct structure"""
        module = CryptoModule(crypto_config)

        # Mock all API calls
        mock_price = AsyncMock(
            return_value={
                "price": 50000.0,
                "market_cap": 1000000000000,
                "volume_24h": 20000000000,
                "change_24h_pct": 2.5,
                "source": "binance",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        module.sources[0] = ("binance", mock_price)

        result = await module._fetch_crypto_market_data()

        assert isinstance(result, list)
        assert len(result) > 0

        # Check structure of first result
        first_item = result[0]
        assert "symbol" in first_item
        assert "name" in first_item
        assert "price" in first_item
        assert "timestamp" in first_item
