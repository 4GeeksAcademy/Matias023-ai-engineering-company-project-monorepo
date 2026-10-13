"""Isolated unit tests for business performance transformation tasks."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from data.pipelines import pipeline


WEEK = date(2025, 1, 6)


@pytest.fixture(autouse=True)
def configured_contract_paths(monkeypatch):
    monkeypatch.setenv("PIPELINE_TAG_PATH_WAREHOUSE", "warehouse")
    monkeypatch.setenv("PIPELINE_TAG_PATH_CLIENT_ID", "client_id")
    monkeypatch.setenv("PIPELINE_TAG_PATH_QUANTITY", "quantity")


@pytest.fixture
def contractual_events():
    return [
        {"event_type": "inbound_order_created", "tags": {
            "warehouse": "los_angeles", "client_id": "client-a", "quantity": 12}},
        {"event_type": "outbound_order_created", "tags": {
            "warehouse": "los_angeles", "client_id": "client-a"}},
        {"event_type": "outbound_order_created", "tags": {
            "warehouse": "los_angeles", "client_id": "client-a"}},
        {"event_type": "stock_threshold_triggered", "tags": {
            "warehouse": "los_angeles", "client_id": "client-a"}},
        {"event_type": "inventory_discrepancy_detected", "tags": {
            "warehouse": "los_angeles", "client_id": "client-a"}},
        {"event_type": "inbound_order_created", "tags": {
            "warehouse": "zaragoza", "client_id": "client-b", "quantity": 4}},
        {"event_type": "inventory_discrepancy_detected", "tags": {
            "warehouse": "zaragoza", "client_id": "client-b"}},
    ]


def validated(events):
    return pipeline.validate_contractual_weekly_events.fn(events)


def test_inbound_units_count_sums_only_validated_inbound_quantities(contractual_events):
    result = pipeline.calculate_inbound_units_count.fn(validated(contractual_events))
    assert result == {("los_angeles", "client-a"): 12,
                      ("zaragoza", "client-b"): 4}


def test_outbound_orders_count_is_grouped_by_warehouse_and_client(contractual_events):
    result = pipeline.calculate_outbound_orders_count.fn(validated(contractual_events))
    assert result == {("los_angeles", "client-a"): 2}


def test_stockout_events_count_is_numerically_exact(contractual_events):
    result = pipeline.calculate_stockout_events_count.fn(validated(contractual_events))
    assert result == {("los_angeles", "client-a"): 1}


def test_discrepancy_rate_uses_outbound_count_and_zero_denominator():
    events = validated([
        {"event_type": "inventory_discrepancy_detected", "tags": {
            "warehouse": "zaragoza", "client_id": "client-b"}},
        {"event_type": "outbound_order_created", "tags": {
            "warehouse": "los_angeles", "client_id": "client-a"}},
        {"event_type": "inventory_discrepancy_detected", "tags": {
            "warehouse": "los_angeles", "client_id": "client-a"}},
        {"event_type": "inventory_discrepancy_detected", "tags": {
            "warehouse": "los_angeles", "client_id": "client-a"}},
    ])
    outbound = pipeline.calculate_outbound_orders_count.fn(events)
    result = pipeline.calculate_discrepancy_events_and_rate.fn(events, outbound)
    assert result[("los_angeles", "client-a")] == (2, Decimal("2"))
    assert result[("zaragoza", "client-b")] == (1, Decimal("0"))


def test_validation_rejects_malformed_event_before_any_kpi_result():
    events = [
        {"event_type": "outbound_order_created", "tags": {
            "warehouse": "los_angeles", "client_id": "client-a"}},
        {"event_type": "inbound_order_created", "tags": {
            "warehouse": "LA", "client_id": "client-a", "quantity": "bad"}},
    ]
    with pytest.raises(pipeline.ContractViolation) as error:
        pipeline.validate_and_aggregate_performance.fn(WEEK, events)
    assert error.value.rejected == 1
    assert error.value.reasons == {
        "unknown_or_missing_warehouse": 1,
        "missing_or_invalid_quantity": 1,
    }


def test_composed_rows_keep_warehouse_client_week_grain(contractual_events):
    rows = pipeline.validate_and_aggregate_performance.fn(WEEK, contractual_events)
    assert [(row["warehouse"], row["client_id"], row["week_start"]) for row in rows] == [
        ("los_angeles", "client-a", WEEK), ("zaragoza", "client-b", WEEK)]
    assert rows[0]["discrepancy_rate"] == Decimal("0.5")
    assert rows[1]["discrepancy_rate"] == Decimal("0")
