# tests/unit/api_gateway/test_gateway_aggregate.py

from uuid import uuid4

from src.api_gateway.domain.aggregates.gateway_aggregate import GatewayAggregate


def test_request_routing_creates_event():
    """Test routing creates RequestRouted event"""
    aggregate = GatewayAggregate(uuid4())

    aggregate.route_request(
        request_id=uuid4(),
        service_name="model-management",
        endpoint="/api/models",
        response_status=200,
        latency_ms=50,
    )

    events = aggregate.get_uncommitted_events()
    assert len(events) == 1
    assert events[0].event_type == "RequestRouted"
    assert events[0].data["service_name"] == "model-management"
    assert events[0].data["response_status"] == 200
    assert events[0].data["latency_ms"] == 50


def test_routing_rule_update():
    """Test routing rule update"""
    aggregate = GatewayAggregate(uuid4())

    rule_id = uuid4()
    aggregate.update_routing_rule(
        rule_id=rule_id,
        path_pattern="/api/models/*",
        target_service="model-management",
        priority=10,
    )

    events = aggregate.get_uncommitted_events()
    assert len(events) == 1
    assert events[0].event_type == "RoutingRuleUpdated"
    assert events[0].data["path_pattern"] == "/api/models/*"
    assert events[0].data["target_service"] == "model-management"
    assert events[0].data["priority"] == 10

    # Check aggregate state
    assert "/api/models/*" in aggregate.active_rules
    assert aggregate.active_rules["/api/models/*"]["target_service"] == "model-management"
    assert aggregate.active_rules["/api/models/*"]["priority"] == 10


def test_multiple_routing_rules():
    """Test multiple routing rules can be added"""
    aggregate = GatewayAggregate(uuid4())

    aggregate.update_routing_rule(
        rule_id=uuid4(),
        path_pattern="/api/models/*",
        target_service="model-management",
        priority=10,
    )

    aggregate.update_routing_rule(
        rule_id=uuid4(),
        path_pattern="/api/plugins/*",
        target_service="plugin-manager",
        priority=20,
    )

    assert len(aggregate.active_rules) == 2
    assert "/api/models/*" in aggregate.active_rules
    assert "/api/plugins/*" in aggregate.active_rules


def test_routing_rule_update_overwrites():
    """Test updating a rule overwrites existing rule"""
    aggregate = GatewayAggregate(uuid4())

    rule_id = uuid4()
    aggregate.update_routing_rule(
        rule_id=rule_id,
        path_pattern="/api/models/*",
        target_service="model-management",
        priority=10,
    )

    # Update same rule with different priority
    aggregate.update_routing_rule(
        rule_id=rule_id,
        path_pattern="/api/models/*",
        target_service="model-management-v2",
        priority=5,
    )

    assert aggregate.active_rules["/api/models/*"]["target_service"] == "model-management-v2"
    assert aggregate.active_rules["/api/models/*"]["priority"] == 5


def test_aggregate_version_increments():
    """Test aggregate version increments with each event"""
    aggregate = GatewayAggregate(uuid4())

    initial_version = aggregate.version

    aggregate.route_request(
        request_id=uuid4(),
        service_name="model-management",
        endpoint="/api/models",
        response_status=200,
        latency_ms=50,
    )

    assert aggregate.version == initial_version + 1

    aggregate.update_routing_rule(
        rule_id=uuid4(),
        path_pattern="/api/models/*",
        target_service="model-management",
        priority=10,
    )

    assert aggregate.version == initial_version + 2


def test_mark_events_as_committed():
    """Test events can be marked as committed"""
    aggregate = GatewayAggregate(uuid4())

    aggregate.route_request(
        request_id=uuid4(),
        service_name="model-management",
        endpoint="/api/models",
        response_status=200,
        latency_ms=50,
    )

    assert len(aggregate.get_uncommitted_events()) == 1

    aggregate.mark_events_as_committed()

    assert len(aggregate.get_uncommitted_events()) == 0
