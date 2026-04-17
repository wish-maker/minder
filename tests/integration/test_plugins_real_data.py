#!/usr/bin/env python3
"""
Test plugins with REAL API calls - no mocks!
"""
import asyncio
import sys
import os

# Add minder to path
sys.path.insert(0, "/root/minder")

from plugins.crypto.crypto_module import CryptoModule
from plugins.weather.weather_module import WeatherModule
from plugins.news.news_module import NewsModule

# Minimal config
config = {
    "database": {
        "host": "localhost",
        "port": 5432,
        "database": "fundmind",
        "user": "postgres",
        "password": "postgres",
    }
}


async def test_crypto_real():
    """Test crypto plugin with REAL API"""
    print("\n" + "=" * 60)
    print("🪙 Testing CRYPTO Plugin (REAL Binance API)")
    print("=" * 60)

    try:
        module = CryptoModule(config)
        await module.register()

        # Get REAL price from Binance
        result = await module._binance_get_price("BTCUSDT")

        print(f"✅ SUCCESS - Real BTC Price:")
        print(f"   Price: ${result['price']:,.2f}")
        print(f"   Source: {result['source']}")
        print(f"   Timestamp: {result['timestamp']}")

        # Verify it's real data
        assert result["price"] > 0, "Price must be positive"
        assert 20000 < result["price"] < 200000, "BTC price should be realistic"
        assert result["source"] == "binance", "Should come from Binance"

        await module.close()
        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_weather_real():
    """Test weather plugin with REAL API"""
    print("\n" + "=" * 60)
    print("🌤️  Testing WEATHER Plugin (REAL Open-Meteo API)")
    print("=" * 60)

    try:
        module = WeatherModule(config)
        await module.register()

        # Get REAL weather data
        result = await module._fetch_weather_data("Istanbul")

        print(f"✅ SUCCESS - Real Istanbul Weather:")
        print(f"   Temperature: {result['temperature_c']}°C")
        print(f"   Humidity: {result['humidity_pct']}%")
        print(f"   Wind: {result['wind_speed_kmh']} km/h")
        print(f"   Description: {result['weather_description']}")

        # Verify it's real data
        assert -50 < result["temperature_c"] < 50, "Temp should be realistic"
        assert 0 <= result["humidity_pct"] <= 100, "Humidity 0-100%"
        assert result["location"] == "Istanbul", "Should be Istanbul"

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_news_real():
    """Test news plugin with REAL RSS feeds"""
    print("\n" + "=" * 60)
    print("📰 Testing NEWS Plugin (REAL RSS Feeds)")
    print("=" * 60)

    try:
        module = NewsModule(config)
        await module.register()

        # Get REAL articles from RSS
        feed_config = {
            "name": "BBC World",
            "url": "https://feeds.bbci.co.uk/news/rss.xml",
            "source": "BBC",
        }

        articles = await module._fetch_rss_articles(feed_config)

        print(f"✅ SUCCESS - Real BBC Articles:")
        print(f"   Total articles fetched: {len(articles)}")

        if articles:
            first = articles[0]
            print(f"\n   Latest article:")
            print(f"   Title: {first['title'][:80]}...")
            print(f"   Source: {first['source']}")
            print(f"   URL: {first['url'][:60]}...")

            # Verify real data
            assert len(articles) > 0, "Should fetch articles"
            assert first["title"], "Should have title"
            assert first["url"], "Should have URL"
            assert "bbc" in first["url"].lower(), "Should be from BBC"

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all real data tests"""
    print("\n🔍 MINDER PLUGIN REAL DATA TEST")
    print("Testing all plugins with ACTUAL API calls - NO MOCKS!")

    results = {
        "crypto": await test_crypto_real(),
        "weather": await test_weather_real(),
        "news": await test_news_real(),
    }

    print("\n" + "=" * 60)
    print("📊 FINAL RESULTS")
    print("=" * 60)

    for plugin, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {plugin.upper()} Plugin")

    all_passed = all(results.values())

    if all_passed:
        print("\n🎉 SUCCESS! All plugins returning REAL data!")
        return 0
    else:
        print("\n⚠️  Some plugins failed real data test")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
