# 🔧 Minder Platform - Issues Tracker

**Last Updated:** 2026-04-23 22:30
**Status:** Active Tracking
**Overall Production Ready:** 72%

---

## 🚨 Critical Issues (P0 - Blocking Release)

### OPENWEBUI-001: OpenWebUI AI Tool Integration Not Working
- **Status:** 🔴 In Progress
- **Priority:** P0
- **Discovered:** 2026-04-23
- **Owner:** AI Integration Team
- **Estimated:** 2 hours

**Description:**
OpenWebUI is running but LLM cannot call Minder Platform tools from chat interface. Users cannot ask natural language queries like "What's the Bitcoin price?" and get API responses.

**Root Cause:**
- Tool calling mechanism defined but not fully integrated
- Missing connection between OpenWebUI and Minder API Gateway's /v1/ai endpoints
- functions.json created but needs end-to-end testing

**Impact:**
- Users must use REST API directly instead of natural language
- Chat interface is just a basic LLM without platform tools
- Primary value proposition (AI + Platform tools) not functional

**Fix Progress:**
- ✅ Created `infrastructure/docker/openwebui/functions.json` with 8 tool definitions
- ✅ Created `src/shared/ai/minder_tools.py` with tool execution logic
- ✅ Updated `docker-compose.yml` to mount functions.json
- ✅ Added environment variables for AI integration
- ⚠️ **Remaining:** End-to-end testing required

**Next Steps:**
1. Restart OpenWebUI container with new configuration
2. Test: User types "BTC fiyatı ne?" → LLM calls get_crypto_price → Returns price
3. Test: User types "Haberleri getir" → LLM calls get_latest_news → Returns articles
4. Verify all 8 tools work from chat interface

**Verification:**
```bash
# Test AI integration endpoint
curl http://localhost:8000/v1/ai/status

# Test function definitions
curl http://localhost:8000/v1/ai/functions/definitions

# Test tool execution
curl -X POST http://localhost:8000/v1/ai/functions/get_crypto_price \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC"}'
```

---

### DASH-001: No User-Friendly Dashboards
- **Status:** 🔴 Not Started
- **Priority:** P0
- **Discovered:** 2026-04-23
- **Owner:** Frontend Team
- **Estimated:** 3 hours

**Description:**
Grafana is installed but has no pre-configured dashboards. Users cannot visualize crypto prices, news sentiment, or plugin health in a user-friendly way.

**Impact:**
- No visual interface for end users
- Must use raw API or logs to see data
- Platform feels incomplete despite having all the data

**Required Dashboards:**
1. **Crypto Market Dashboard**
   - Real-time prices (BTC, ETH, SOL, ADA, DOT)
   - 24h change percentage
   - Market cap charts
   - Price alerts

2. **News Sentiment Dashboard**
   - Latest headlines
   - Sentiment analysis scores
   - Source distribution
   - Article count trends

3. **Plugin Health Dashboard**
   - All 5 plugins status
   - Last collection time
   - Error rates
   - Data quality metrics

4. **System Overview Dashboard**
   - Container health (20/20)
   - Resource usage
   - API request rates
   - Response times

**Next Steps:**
1. Create dashboard JSON files in `infrastructure/docker/grafana/dashboards/`
2. Configure auto-provisioning in docker-compose.yml
3. Test dashboard visibility and data accuracy
4. Add dashboard screenshots to documentation

---

## 🟡 High Priority Issues (P1 - Important)

### SDK-001: No Python SDK for Developers
- **Status:** 🔴 Not Started
- **Priority:** P1
- **Discovered:** 2026-04-23
- **Owner:** Developer Experience Team
- **Estimated:** 3 hours

**Description:**
Developers must make raw HTTP requests to integrate with Minder Platform. No official Python SDK exists for easy API access.

**Impact:**
- High barrier to entry for developers
- Error-prone manual HTTP request construction
- No type hints or autocomplete support
- Harder to build integrations

**Required SDK Features:**
```python
# Desired API
from minder_sdk import MinderClient

client = MinderClient(
    base_url="http://localhost:8000",
    api_key="your-jwt-token"
)

# Get crypto price
btc_price = client.crypto.get_price("BTC")

# Collect news
client.news.collect(source="BBC")

# Get plugin status
plugins = client.plugins.list()

# Enable plugin
client.plugins.enable("crypto")
```

**Implementation Plan:**
1. Create `minder-sdk/` package directory
2. Implement client classes for each plugin
3. Add type hints and docstrings
4. Write usage examples
5. Publish to PyPI or install via git

---

### API-001: No Postman Collection
- **Status:** 🔴 Not Started
- **Priority:** P1
- **Discovered:** 2026-04-23
- **Owner:** Developer Experience Team
- **Estimated:** 1 hour

**Description:**
No Postman collection available for testing all API endpoints. Developers must manually construct requests.

**Required Collections:**
- Authentication endpoints (login, refresh)
- All plugin endpoints (crypto, news, network, weather, tefas)
- AI integration endpoints
- Admin endpoints (enable/disable plugins)

**Deliverables:**
- Postman collection JSON file
- Environment variables for dev/staging/prod
- Pre-configured authentication
- Example request bodies

---

### ALERT-001: No Alert System
- **Status:** 🔴 Not Started
- **Priority:** P1
- **Discovered:** 2026-04-23
- **Owner:** Monitoring Team
- **Estimated:** 4 hours

**Description:**
No alert system for price changes, sentiment shifts, or plugin errors. Users must actively check for updates.

**Required Alerts:**
1. **Price Alerts**
   - BTC price changes >5% in 1 hour
   - ETH price crosses $3000
   - Custom price thresholds

2. **News Sentiment Alerts**
   - Sudden negative sentiment spike
   - Breaking news from specific sources
   - Keyword-triggered alerts (e.g., "regulation")

3. **Plugin Health Alerts**
   - Plugin collection fails 3x in a row
   - Database connection errors
   - API rate limit exceeded

4. **System Alerts**
   - Container goes unhealthy
   - Disk space <10%
   - API response time >5s

**Implementation:**
- Use Alertmanager (already installed)
- Configure alert rules in `infrastructure/docker/alertmanager/alerts.yml`
- Add notification channels (Email, Slack, Webhook)
- Test alert delivery

---

## 🟢 Medium Priority Issues (P2 - Nice to Have)

### DOC-001: Integration Examples Incomplete
- **Status:** 🔴 Not Started
- **Priority:** P2
- **Estimated:** 2 hours

**Description:**
Documentation has API reference but lacks practical integration examples for common use cases.

**Required Examples:**
1. Build a crypto price bot in Python
2. Create a news sentiment analyzer
3. Integrate with external trading platform
4. Build custom dashboard
5. Webhook integrations

---

### RPT-001: No Reporting System
- **Status:** 🔴 Not Started
- **Priority:** P2
- **Estimated:** 4 hours

**Description:**
Cannot generate PDF/Excel reports for historical data, performance metrics, or compliance audits.

**Required Features:**
- Daily crypto price report (PDF)
- Monthly news sentiment summary (Excel)
- Custom date range reports
- Scheduled email reports
- Report templates

---

### WEBHOOK-001: No Webhook System
- **Status:** 🔴 Not Started
- **Priority:** P2
- **Estimated:** 3 hours

**Description:**
Cannot push real-time updates to external systems. No event-driven architecture for integrations.

**Required Events:**
- Crypto price updated
- News article collected
- Plugin enabled/disabled
- System health changed

**Implementation:**
- Webhook configuration API
- Event publishing system
- Retry mechanism for failed webhooks
- Signature verification for security

---

## ✅ Resolved Issues

### P1-001: Default Credentials (Security)
- **Status:** ✅ Resolved
- **Fixed:** 2026-04-23
- **Solution:** Created `setup-security.sh` to generate secure credentials, removed all defaults from docker-compose.yml

### P1-002: Bare Except Clauses
- **Status:** ✅ Resolved
- **Fixed:** 2026-04-23
- **Solution:** Replaced with specific exception types in `configuration_store.py` and `correlation_engine.py`

### P1-003: Missing Health Checks
- **Status:** ✅ Resolved
- **Fixed:** 2026-04-23
- **Solution:** Added health checks to 4 services (telegraf, prometheus, postgres-exporter, redis-exporter)

### P1-004: No API Authentication
- **Status:** ✅ Resolved
- **Fixed:** 2026-04-23
- **Solution:** Implemented JWT authentication with rate limiting in `src/shared/auth/jwt_middleware.py`

### CLEANUP-001: Empty/Duplicate Files
- **Status:** ✅ Resolved
- **Fixed:** 2026-04-23
- **Solution:** Removed empty `/plugins` directory, duplicate `.env` files, cleaned `__pycache__`

### CODE-001: Database Pool Duplication
- **Status:** ✅ Resolved
- **Fixed:** 2026-04-23
- **Solution:** Created shared pool manager in `src/shared/database/asyncpg_pool.py`, removed 135 duplicate lines

---

## 📊 Issue Statistics

**Total Issues:** 13
- ✅ Resolved: 6 (46%)
- 🔴 In Progress: 1 (8%)
- 🔴 Not Started: 6 (46%)

**By Priority:**
- P0 (Critical): 2 (1 in progress)
- P1 (High): 3
- P2 (Medium): 3

**Estimated Time to Complete All Issues:** 20 hours

---

## 🎯 Next Actions (This Week)

1. **[TODAY]** Complete OpenWebUI AI tool integration testing (2h)
2. **[TODAY]** Create first Grafana dashboard - Crypto Market (2h)
3. **[TOMORROW]** Build Python SDK (3h)
4. **[WEDNESDAY]** Create Postman collection (1h)
5. **[THURSDAY]** Implement alert system (4h)
6. **[FRIDAY]** Create remaining dashboards (3h)

**Target:** Reach 90% production ready by end of week

---

## 📝 Issue Resolution Checklist

When resolving an issue:

1. **Fix the root cause** - Don't patch symptoms
2. **Add unit tests** - Ensure fix doesn't regress
3. **Update documentation** - Document the change
4. **Test end-to-end** - Verify it works in real scenarios
5. **Update this file** - Mark as resolved with notes
6. **Celebrate** - Tell the team when you ship something!

---

## 📞 How to Report Issues

Found a bug? Have a feature request?

1. Check if issue already exists in this file
2. If not, add it with:
   - Descriptive title (e.g., "AUTH-001: JWT tokens expire too quickly")
   - Status: "🔴 Not Started"
   - Priority: P0/P1/P2
   - Description: What's wrong?
   - Impact: Why does it matter?
   - Steps to reproduce (if bug)
  . Expected vs actual behavior
3. Assign owner and estimated time
4. Track progress until resolved

---

**Remember:** A tracked issue is half solved! 🎯
