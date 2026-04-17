# Manual Tests

This directory contains tests that require external API access, manual intervention, or specific runtime conditions and should NOT be run in CI/CD pipelines.

## Why Manual Tests?

These tests are excluded from CI/CD because they:

1. **Make real HTTP requests to external APIs** (TEFAS, KAP, etc.)
2. **Subject to rate limiting and robot detection**
3. **May fail due to network issues or API changes**
4. **Require stable internet connection and specific timing**
5. **May have flaky behavior in automated CI environments**

## Available Tests

### test_tefas_crawler.py
Tests the tefas-crawler package by making real API calls to TEFAS.

### test_tefas_real.py
Tests TEFAS plugin with real TEFAS API calls.

### test_tefas_v2.py
Tests TEFAS v2 module integration.

### test_tefas_v3_integration.py
Tests TEFAS v3 module with full integration scenarios.

### test_unified_api.py
Tests the unified data API across multiple modules.

### test_plugins_real_data.py
Tests plugins with real data sources.

### test_kap_site.py
Tests KAP (Kamuyu Aydınlatma Platformu) site scraping.

### validate_complete_integration.py
Validates complete integration across all modules.

### validate_phase1.py
Validates Phase 1 implementation milestones.

## How to Run

### Run all manual tests
```bash
# From project root
pytest tests/manual/ -v

# Or run individual tests
python tests/manual/test_tefas_crawler.py
```

### Run specific test
```bash
pytest tests/manual/test_tefas_real.py -v
pytest tests/manual/test_kap_site.py -v
```

## Expected Behavior

**These tests MAY fail if:**
- External APIs are down or blocking requests
- Rate limiting is triggered (multiple retries with backoff)
- Robot detection blocks requests
- Network issues or timeouts
- API responses changed unexpectedly

**This is NORMAL and EXPECTED behavior** for manual integration tests.

## Best Practices

1. **Run during development/testing**, not in CI
2. **Run infrequently** to avoid rate limiting
3. **Use appropriate delays** between requests
4. **Monitor external API status** if tests fail consistently
5. **Update tests** when API responses change
6. **Document API changes** in test files

## CI/CD Integration

These tests are explicitly **EXCLUDED** from CI/CD pipelines:
- Not run in GitHub Actions
- Not run in pre-commit hooks
- Not required for PR approval

They are provided for:
- Local development validation
- Manual testing before releases
- Integration debugging
- API availability monitoring
