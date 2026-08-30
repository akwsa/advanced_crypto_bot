"""Contract tests for Story 2.3: Deterministic Simulator Lifecycle."""

from datetime import UTC, datetime, timedelta
import os
import subprocess
import sys
import pytest

from autotrade_next.domain.market import (
    InstrumentRules,
    MarketQuality,
    MarketSnapshot,
    OrderBookLevel,
    OrderBookSide,
    UniverseMembership,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.simulator import (
    CostRules, FeeType, LifecycleAction, LifecycleActionType, LifecycleScenario,
    OrderSimulator, OrderStatus, ScenarioOutcome, SimulatorError, SimulatorEvent,
    reduce_lifecycle,
)
from autotrade_next.ports.venue import VenuePort


EVENT_TIME = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


def _lifecycle_snapshot(*, asks=None) -> MarketSnapshot:
    asks = asks or (
        OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(3, 0)),
        OrderBookLevel(ScaledInteger(10100, 2), ScaledInteger(2, 0)))
    return MarketSnapshot.create(
        instrument_id="BTC-IDR", event_at_utc=EVENT_TIME, received_at_utc=EVENT_TIME,
        venue_cursor="1002", ingest_cursor="2002",
        bids=(OrderBookLevel(ScaledInteger(9900, 2), ScaledInteger(5, 0)),),
        asks=asks,
        execution_side=OrderBookSide.ASK, requested_size=ScaledInteger(5, 0),
        rules=InstrumentRules("rules:v1", ScaledInteger(1, 0), 2, 2,
                              ScaledInteger(1, 2), ScaledInteger(1, 2), True),
        membership=UniverseMembership("universe:v1", EVENT_TIME, True, "proof:v1"),
        quality=MarketQuality(0, 3_000_000, 10, 50, True, "public-market", "l2:1002"),
    )


def _scenario(outcome=ScenarioOutcome.EXECUTE, actions=()):
    return LifecycleScenario("scenario:v1", "fixed-seed", 2_000, 0,
                             outcome, FeeType.TAKER, tuple(actions))


def _costs():
    return CostRules("cost:v1", 10, 20, 5, 4)


def test_order_simulator_filled():
    event_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    receive_time = datetime(2026, 8, 29, 12, 0, 1, tzinfo=UTC)
    
    asks = (
        OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(10, 0)),
    )
    bids = (
        OrderBookLevel(ScaledInteger(9900, 2), ScaledInteger(10, 0)),
    )

    snapshot = MarketSnapshot.create(
        instrument_id="BTC-IDR",
        event_at_utc=event_time,
        received_at_utc=receive_time,
        venue_cursor="1001",
        ingest_cursor="2001",
        bids=bids,
        asks=asks,
        execution_side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0),
        rules=InstrumentRules(
            version="rules:btc-idr:7",
            min_order_size=ScaledInteger(1, 0),
            price_scale=2,
            quantity_scale=0,
            price_tick=ScaledInteger(1, 2),
            quantity_step=ScaledInteger(1, 0),
            metadata_qualified=True,
        ),
        membership=UniverseMembership(
            universe_version="universe:2026-08-29",
            effective_at_utc=event_time,
            is_member=True,
            proof_id="membership:btc-idr:2026-08-29",
        ),
        quality=MarketQuality(
            freshness_micros=1_000_000,
            max_freshness_micros=3_000_000,
            current_spread_ratio_bps=10,
            max_spread_ratio_bps=50,
            source_integrity_qualified=True,
            authority_scope_id="indodax-public-market",
            evidence_id="l2:btc-idr:1001",
        ),
    )

    simulator = OrderSimulator(seed=42)
    evt = simulator.simulate_execution(
        order_id="ord-123",
        side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0),
        snapshot=snapshot,
        evaluated_at_utc=event_time,
    )

    assert evt.order_id == "ord-123"
    assert evt.status is OrderStatus.FILLED
    assert evt.filled_quantity == ScaledInteger(5, 0)
    assert evt.remaining_quantity == ScaledInteger(0, 0)
    assert len(evt.fills) == 1
    assert evt.fills[0].price == ScaledInteger(10000, 2)
    assert evt.fills[0].fee_type is FeeType.TAKER
    assert snapshot.calculate_executable_price(OrderBookSide.ASK) == (
        ScaledInteger(10, 0),
        ScaledInteger(10000, 2),
    )


def test_order_simulator_fills_economically_equal_mixed_scale_quantity():
    event_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    snapshot = MarketSnapshot.create(
        instrument_id="BTC-IDR",
        event_at_utc=event_time,
        received_at_utc=event_time,
        venue_cursor="1002",
        ingest_cursor="2002",
        bids=(OrderBookLevel(ScaledInteger(9900, 2), ScaledInteger(5, 0)),),
        asks=(OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(5, 0)),),
        execution_side=OrderBookSide.ASK,
        requested_size=ScaledInteger(500, 2),
        rules=InstrumentRules(
            version="rules:btc-idr:8",
            min_order_size=ScaledInteger(1, 0),
            price_scale=2,
            quantity_scale=2,
            price_tick=ScaledInteger(1, 2),
            quantity_step=ScaledInteger(1, 2),
            metadata_qualified=True,
        ),
        membership=UniverseMembership(
            universe_version="universe:2026-08-29",
            effective_at_utc=event_time,
            is_member=True,
            proof_id="membership:btc-idr:2026-08-29",
        ),
        quality=MarketQuality(
            freshness_micros=0,
            max_freshness_micros=3_000_000,
            current_spread_ratio_bps=10,
            max_spread_ratio_bps=50,
            source_integrity_qualified=True,
            authority_scope_id="indodax-public-market",
            evidence_id="l2:btc-idr:1002",
        ),
    )

    event = OrderSimulator(seed=42).simulate_execution(
        order_id="ord-mixed-scale",
        side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0),
        snapshot=snapshot,
        evaluated_at_utc=event_time,
    )

    assert event.status is OrderStatus.FILLED
    assert event.filled_quantity == ScaledInteger(500, 2)
    assert event.remaining_quantity == ScaledInteger(0, 2)
    assert event.fills[0].quantity == ScaledInteger(500, 2)
    assert event.fills[0].fee == ScaledInteger(10000, 4)


def test_order_simulator_dry_run_no_live_imports():
    # Verify that live submission modules cannot be imported or accessed
    with pytest.raises(ModuleNotFoundError):
        import autotrade_next.adapters.indodax.live_submit  # type: ignore


def test_full_lifecycle_is_ordered_content_bound_and_exact_per_level():
    result = OrderSimulator(seed=42).simulate_lifecycle(
        order_id="ord-lifecycle", side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0), snapshot=_lifecycle_snapshot(),
        evaluated_at_utc=EVENT_TIME, scenario=_scenario(), cost_rules=_costs(),
    )
    assert tuple(event.status for event in result.events) == (
        OrderStatus.ACCEPTED, OrderStatus.OPEN, OrderStatus.PARTIAL, OrderStatus.FILLED)
    assert tuple(event.sequence for event in result.events) == (1, 2, 3, 4)
    assert all(event.event_ref.verify(event.binding_value()) for event in result.events)
    fills = result.terminal_event.fills
    assert tuple(fill.quantity for fill in fills) == (
        ScaledInteger(300, 2), ScaledInteger(200, 2))
    assert tuple(fill.notional for fill in fills) == (
        ScaledInteger(3_000_000, 4), ScaledInteger(2_020_000, 4))
    assert tuple(fill.fee for fill in fills) == (
        ScaledInteger(6_000, 4), ScaledInteger(4_040, 4))
    assert tuple(fill.tax for fill in fills) == (
        ScaledInteger(1_500, 4), ScaledInteger(1_010, 4))
    assert result.events[1].event_at_utc == EVENT_TIME + timedelta(microseconds=2_000)


def test_maker_bid_adverse_selection_and_single_rounding_cost_boundary():
    snapshot = MarketSnapshot.create(
        instrument_id="SMALL-IDR", event_at_utc=EVENT_TIME,
        received_at_utc=EVENT_TIME, venue_cursor="small:1", ingest_cursor="small:1",
        bids=(OrderBookLevel(ScaledInteger(99, 2), ScaledInteger(1, 0)),),
        asks=(OrderBookLevel(ScaledInteger(101, 2), ScaledInteger(1, 0)),),
        execution_side=OrderBookSide.BID, requested_size=ScaledInteger(1, 0),
        rules=InstrumentRules(
            "rules:small", ScaledInteger(1, 0), 2, 0,
            ScaledInteger(1, 2), ScaledInteger(1, 0), True),
        membership=UniverseMembership("universe:small", EVENT_TIME, True, "proof:small"),
        quality=MarketQuality(0, 1, 1, 2, True, "small", "small:1"))
    scenario = LifecycleScenario(
        "scenario:maker-bid", "seed", 0, 100,
        ScenarioOutcome.EXECUTE, FeeType.MAKER)
    result = OrderSimulator(seed=1).simulate_lifecycle(
        order_id="ord-maker-bid", side=OrderBookSide.BID,
        requested_size=ScaledInteger(1, 0), snapshot=snapshot,
        evaluated_at_utc=EVENT_TIME, scenario=scenario,
        cost_rules=CostRules("cost:coarse", 6_000, 0, 0, 0))
    fill = result.terminal_event.fills[0]
    assert fill.fee_type is FeeType.MAKER
    assert fill.price == ScaledInteger(98, 2)
    assert fill.notional == ScaledInteger(1, 0)
    assert fill.fee == ScaledInteger(1, 0)
    assert fill.tax == ScaledInteger(0, 0)


@pytest.mark.parametrize(
    ("outcome", "statuses"),
    [
        (ScenarioOutcome.REJECT, (OrderStatus.REJECTED,)),
        (ScenarioOutcome.EXPIRE, (OrderStatus.ACCEPTED, OrderStatus.OPEN, OrderStatus.EXPIRED)),
        (ScenarioOutcome.NON_FILL, (OrderStatus.ACCEPTED, OrderStatus.OPEN, OrderStatus.CANCELLED)),
        (ScenarioOutcome.AMBIGUOUS, (OrderStatus.ACCEPTED, OrderStatus.OPEN, OrderStatus.UNKNOWN)),
    ],
)
def test_explicit_terminal_scenarios(outcome, statuses):
    result = OrderSimulator(seed=7).simulate_lifecycle(
        order_id=f"ord-{outcome.value}", side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0), snapshot=_lifecycle_snapshot(),
        evaluated_at_utc=EVENT_TIME, scenario=_scenario(outcome), cost_rules=_costs())
    assert tuple(event.status for event in result.events) == statuses
    assert result.entry_frozen is (outcome is ScenarioOutcome.AMBIGUOUS)


def test_recorded_cancel_fill_race_uses_order_or_freezes_on_ambiguity():
    opened = EVENT_TIME + timedelta(microseconds=2_000)
    cancel_first = (
        LifecycleAction(1, LifecycleActionType.CANCEL, opened),
        LifecycleAction(2, LifecycleActionType.FILL, opened + timedelta(microseconds=1)))
    fill_first = (
        LifecycleAction(2, LifecycleActionType.CANCEL, opened + timedelta(microseconds=3)),
        LifecycleAction(1, LifecycleActionType.FILL, opened))
    ambiguous = (
        LifecycleAction(1, LifecycleActionType.CANCEL, opened),
        LifecycleAction(1, LifecycleActionType.FILL, opened))
    statuses = []
    for actions in (cancel_first, fill_first, ambiguous):
        result = OrderSimulator(seed=7).simulate_lifecycle(
            order_id="ord-race", side=OrderBookSide.ASK,
            requested_size=ScaledInteger(5, 0), snapshot=_lifecycle_snapshot(),
            evaluated_at_utc=EVENT_TIME, scenario=_scenario(actions=actions), cost_rules=_costs())
        statuses.append(result.terminal_event.status)
    assert statuses == [OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.UNKNOWN]


def test_partial_fill_then_cancel_preserves_cumulative_fill_and_remainder():
    opened = EVENT_TIME + timedelta(microseconds=2_000)
    snapshot = _lifecycle_snapshot(asks=(
        OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(2, 0)),))
    actions = (
        LifecycleAction(1, LifecycleActionType.FILL, opened),
        LifecycleAction(2, LifecycleActionType.CANCEL, opened + timedelta(microseconds=10)),
    )
    result = OrderSimulator(seed=7).simulate_lifecycle(
        order_id="ord-partial-cancel", side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0), snapshot=snapshot,
        evaluated_at_utc=EVENT_TIME, scenario=_scenario(actions=actions),
        cost_rules=_costs())
    assert tuple(event.status for event in result.events) == (
        OrderStatus.ACCEPTED, OrderStatus.OPEN,
        OrderStatus.PARTIAL, OrderStatus.CANCELLED)
    assert result.terminal_event.filled_quantity == ScaledInteger(200, 2)
    assert result.terminal_event.remaining_quantity == ScaledInteger(300, 2)
    assert len(result.terminal_event.fills) == 1


def test_partial_without_terminal_evidence_is_explicitly_nonterminal():
    snapshot = _lifecycle_snapshot(asks=(
        OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(2, 0)),))
    result = OrderSimulator(seed=7).simulate_lifecycle(
        order_id="ord-still-open", side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0), snapshot=snapshot,
        evaluated_at_utc=EVENT_TIME, scenario=_scenario(), cost_rules=_costs())
    assert result.latest_event.status is OrderStatus.PARTIAL
    assert not result.is_terminal
    assert not result.entry_frozen


def test_public_boundary_rejects_snapshot_mismatch_and_time_regression():
    simulator = OrderSimulator(seed=7)
    arguments = dict(
        order_id="ord-boundary", side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0), snapshot=_lifecycle_snapshot(),
        evaluated_at_utc=EVENT_TIME, scenario=_scenario(), cost_rules=_costs())
    with pytest.raises(SimulatorError, match="EXECUTION_SIDE_MISMATCH"):
        simulator.simulate_lifecycle(**{**arguments, "side": OrderBookSide.BID})
    with pytest.raises(SimulatorError, match="REQUESTED_SIZE_MISMATCH"):
        simulator.simulate_lifecycle(**{
            **arguments, "requested_size": ScaledInteger(4, 0)})
    before_open = (LifecycleAction(
        1, LifecycleActionType.CANCEL, EVENT_TIME),)
    ambiguous = simulator.simulate_lifecycle(**{
        **arguments, "scenario": _scenario(actions=before_open)})
    assert ambiguous.terminal_event.status is OrderStatus.UNKNOWN
    assert ambiguous.entry_frozen and ambiguous.is_terminal


def test_reducer_is_idempotent_and_rejects_conflicts_and_regressions():
    events = OrderSimulator(seed=7).simulate_lifecycle(
        order_id="ord-reduce", side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0), snapshot=_lifecycle_snapshot(),
        evaluated_at_utc=EVENT_TIME, scenario=_scenario(), cost_rules=_costs()).events
    assert reduce_lifecycle(events + (events[-1],)).terminal_event == events[-1]
    terminal = events[-1]
    conflicting = SimulatorEvent.create(
        event_id=terminal.event_id, order_id=terminal.order_id,
        status=terminal.status, filled_quantity=terminal.filled_quantity,
        remaining_quantity=terminal.remaining_quantity,
        average_price=terminal.average_price, fills=terminal.fills,
        event_at_utc=terminal.event_at_utc, sequence=terminal.sequence,
        schema_version="simulator-event:v2")
    with pytest.raises(SimulatorError, match="CONFLICTING_DUPLICATE_EVENT"):
        reduce_lifecycle(events + (conflicting,))
    with pytest.raises(SimulatorError, match="OUT_OF_ORDER_EVENT"):
        reduce_lifecycle((events[1], events[0]))
    illegal = SimulatorEvent.create(
        event_id="illegal-filled-after-accepted", order_id=terminal.order_id,
        status=terminal.status, filled_quantity=terminal.filled_quantity,
        remaining_quantity=terminal.remaining_quantity,
        average_price=terminal.average_price, fills=terminal.fills,
        event_at_utc=terminal.event_at_utc, sequence=2)
    with pytest.raises(SimulatorError, match="ILLEGAL_TRANSITION"):
        reduce_lifecycle((events[0], illegal))
    inconsistent_open = SimulatorEvent.create(
        event_id="inconsistent-open", order_id=events[0].order_id,
        status=OrderStatus.OPEN, filled_quantity=ScaledInteger(0, 2),
        remaining_quantity=ScaledInteger(501, 2),
        average_price=ScaledInteger(0, 2), fills=(),
        event_at_utc=events[1].event_at_utc, sequence=2)
    with pytest.raises(SimulatorError, match="QUANTITY_CONSERVATION_BREACH"):
        reduce_lifecycle((events[0], inconsistent_open))


def test_replay_identity_does_not_depend_on_python_hash():
    first = OrderSimulator(seed=42).simulate_lifecycle(
        order_id="ord-stable", side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0), snapshot=_lifecycle_snapshot(),
        evaluated_at_utc=EVENT_TIME, scenario=_scenario(), cost_rules=_costs())
    second = OrderSimulator(seed=42).simulate_lifecycle(
        order_id="ord-stable", side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0), snapshot=_lifecycle_snapshot(),
        evaluated_at_utc=EVENT_TIME, scenario=_scenario(), cost_rules=_costs())
    assert tuple((e.event_id, e.event_ref) for e in first.events) == tuple(
        (e.event_id, e.event_ref) for e in second.events)
    command = [sys.executable, "-c", (
        "import json,runpy; "
        "n=runpy.run_path('tests/autotrade_next/contract/test_simulator_lifecycle.py'); "
        "r=n['OrderSimulator'](seed=42).simulate_lifecycle("
        "order_id='ord-stable',side=n['OrderBookSide'].ASK,"
        "requested_size=n['ScaledInteger'](5,0),snapshot=n['_lifecycle_snapshot'](),"
        "evaluated_at_utc=n['EVENT_TIME'],scenario=n['_scenario'](),cost_rules=n['_costs']()); "
        "print(json.dumps([(e.event_id,e.event_ref.key,e.status.value,e.sequence) for e in r.events]))"
    )]
    outputs = []
    for hash_seed in ("1", "999"):
        environment = {**os.environ, "PYTHONHASHSEED": hash_seed,
                       "PYTHONDONTWRITEBYTECODE": "1"}
        outputs.append(subprocess.check_output(command, text=True, env=environment))
    assert outputs[0] == outputs[1]


def test_venue_port_uses_exact_shared_schema_types():
    annotations = VenuePort.publish_event.__annotations__
    assert annotations["event"] is SimulatorEvent
    assert annotations["return"] is None
    event = OrderSimulator(seed=42).simulate_lifecycle(
        order_id="ord-schema", side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0), snapshot=_lifecycle_snapshot(),
        evaluated_at_utc=EVENT_TIME, scenario=_scenario(), cost_rules=_costs(),
    ).events[0]
    assert event.schema_version == "simulator-event:v1"
    assert tuple(event.binding_value()) == (
        "schema_version", "event_id", "sequence", "order_id", "status",
        "filled_quantity", "remaining_quantity", "average_price", "fills",
        "event_at_utc",
    )

    class Recorder:
        def __init__(self):
            self.event = None

        def publish_event(self, published: SimulatorEvent) -> None:
            self.event = published

    recorder: VenuePort = Recorder()
    recorder.publish_event(event)
    assert recorder.event is event
    assert recorder.event.event_ref.verify(recorder.event.binding_value())
