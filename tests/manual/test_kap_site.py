#!/usr/bin/env python3
"""
Test KAP (Kamuyu Aydınlatma Platformu) site accessibility
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup


async def test_kap_site():
    """Test KAP site accessibility"""

    print("=" * 60)
    print("Testing KAP Site Access")
    print("=" * 60)

    urls = [
        ("KAP All Funds", "https://kap.org.tr/tr/YatirimFonlari/ALL"),
        ("KAP Home", "https://kap.org.tr"),
    ]

    async with aiohttp.ClientSession() as session:
        for name, url in urls:
            try:
                print(f"\nTesting: {name}")
                print(f"URL: {url}")

                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    print(f"✅ Status: {response.status}")

                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, "html.parser")

                        # Look for fund-related content
                        title = soup.find("title")
                        if title:
                            print(f"   Title: {title.get_text()[:100]}")

                        # Count tables
                        tables = soup.find_all("table")
                        print(f"   Tables found: {len(tables)}")

                        # Look for fund data
                        if "fon" in html.lower() or "fund" in html.lower():
                            print(f"   ✅ Contains fund-related content")

                        # Check for data format (JSON, XML, etc.)
                        if "application/json" in html or ".json" in html:
                            print(f"   ✅ Contains JSON data")

                    else:
                        print(f"   ⚠️  Unexpected status code")

            except Exception as e:
                print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_kap_site())
