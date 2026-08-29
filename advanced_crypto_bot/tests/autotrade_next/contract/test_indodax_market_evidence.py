from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from autotrade_next.adapters.indodax.capability_registry import INDODAX_CAPABILITY_REGISTRY
from autotrade_next.adapters.indodax.market_evidence import qualify_recorded_input
from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.errors import MarketEvidenceError, RecoveryEvaluationError
from autotrade_next.domain.market import (
    AffectedScope,
    ContinuityResult,
    EvidenceDisposition,
    EvidencePolicy,
    ProductFamily,
    ReconciliationCheckpoint,
    RecoveryDisposition,
    RecoveryProof,
    ScopeKind,
    evaluate_recovery_gate,
)


NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)
POLICY = EvidencePolicy("market-evidence-policy:v1")
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "indodax"
LOGIC_TEST_REGISTRY = INDODAX_CAPABILITY_REGISTRY


def _scope(channel: str = "market:order-book-btcidr") -> AffectedScope:
    return AffectedScope(
        ScopeKind.INSTRUMENT_CHANNEL,
        "authority:indodax",
        "BTC-IDR",
        channel.replace("{pair}", "btcidr"),
    )


def _order_book_payload(offset: int = 42, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "result": {
            "channel": "market:order-book-btcidr",
            "data": {
                "data": {"pair": "btcidr", "ask": [], "bid": []},
                "offset": offset,
            },
        },
    }
    payload.update(extra)
    return payload


def _qualify(**overrides: object):
    values = {
        "registry": LOGIC_TEST_REGISTRY,
        "product": ProductFamily.MARKET_DATA_WEBSOCKET,
        "resource": "market:order-book-{pair}",
        "effective_at": NOW,
        "instrument_id": "BTC-IDR",
        "scope": _scope(),
        "payload": _order_book_payload(),
        "event_at_utc": NOW,
        "received_at_utc": NOW,
        "evaluated_at_utc": NOW,
        "venue_cursor": 42,
        "ingest_cursor": "ingest:42",
        "policy": POLICY,
    }
    values.update(overrides)
    return qualify_recorded_input(**values)


def test_catalog_has_five_isolated_products_and_unique_artifacts() -> None:
    products = {entry.product for entry in INDODAX_CAPABILITY_REGISTRY.entries}
    assert products == set(ProductFamily)
    artifact_refs = [entry.artifact.contract_ref.key for entry in INDODAX_CAPABILITY_REGISTRY.entries]
    assert len(artifact_refs) == len(set(artifact_refs))
    assert all(entry.documentation_commit not in ("master", "main") for entry in INDODAX_CAPABILITY_REGISTRY.entries)
    qualified = {
        entry.capability_id
        for entry in INDODAX_CAPABILITY_REGISTRY.entries
        if entry.qualification_status.value == "QUALIFIED"
    }
    assert qualified == {
        "public-rest.depth.v1",
        "public-rest.ticker.v1",
        "private-rest.get-info.v1",
        "trade-api-v2.my-trades.v1",
        "trade-api-v2.order-histories.v1",
        "market-ws.order-book.v1",
        "market-ws.trade-activity.v1",
        "private-ws.order-update.v1",
    }
    public = INDODAX_CAPABILITY_REGISTRY.lookup(
        ProductFamily.PUBLIC_REST, "/api/depth/{pair}", NOW
    ).entry
    assert public is not None
    assert public.cursor_capability.value == "NO_AUTHORITATIVE_SEQUENCE"


@pytest.mark.parametrize(
    ("product", "resource", "fixture_path", "venue_cursor"),
    [
        (ProductFamily.PUBLIC_REST, "/api/depth/{pair}", "public_rest/public-rest.depth.v1.json", None),
        (ProductFamily.PUBLIC_REST, "/api/ticker/{pair}", "public_rest/public-rest.ticker.v1.json", None),
        (ProductFamily.PRIVATE_REST, "getInfo", "private_rest/private-rest.get-info.v1.json", None),
        (ProductFamily.TRADE_API_V2, "/api/v2/myTrades", "trade_api_v2/trade-api-v2.my-trades.v1.json", None),
        (
            ProductFamily.TRADE_API_V2,
            "/api/v2/order/histories",
            "trade_api_v2/trade-api-v2.order-histories.v1.json",
            None,
        ),
        (
            ProductFamily.MARKET_DATA_WEBSOCKET,
            "market:order-book-{pair}",
            "market_data_websocket/market-ws.order-book.v1.json",
            0,
        ),
        (
            ProductFamily.MARKET_DATA_WEBSOCKET,
            "market:trade-activity-{pair}",
            "market_data_websocket/market-ws.trade-activity.v1.json",
            0,
        ),
        (
            ProductFamily.PRIVATE_WEBSOCKET,
            "private:order-update",
            "private_websocket/private-ws.order-update.v1.json",
            None,
        ),
    ],
)
def test_every_qualified_catalog_entry_admits_its_own_offline_fixture(
    product: ProductFamily,
    resource: str,
    fixture_path: str,
    venue_cursor: int | None,
) -> None:
    payload = json.loads((FIXTURE_ROOT / fixture_path).read_text(encoding="utf-8"))
    scope = _scope(resource)
    result = _qualify(
        product=product,
        resource=resource,
        scope=scope,
        payload=payload,
        venue_cursor=venue_cursor,
    )
    entry = LOGIC_TEST_REGISTRY.lookup(product, resource, NOW).entry

    assert entry is not None
    assert result.disposition is EvidenceDisposition.QUALIFIED
    assert result.evidence is not None
    assert result.evidence.capability_ref == entry.capability_ref
    assert result.evidence.capability_version == entry.version
    assert result.evidence.event_at_utc == NOW
    assert result.evidence.received_at_utc == NOW
    assert result.canonical_fields == tuple(sorted(entry.authoritative_fields))
    assert tuple(field.field for field in result.evidence.authoritative_fields) == result.canonical_fields
    assert result.freeze_request is None
    assert result.recovery_request is None
    assert result.reconciliation_request is None


def test_qualified_ws_evidence_separates_venue_and_local_cursor_and_freezes_payload() -> None:
    payload = _order_book_payload()
    result = _qualify(payload=payload)
    assert result.disposition is EvidenceDisposition.QUALIFIED
    assert result.evidence is not None
    assert result.evidence.venue_cursor == "42"
    assert result.evidence.ingest_cursor == "ingest:42"
    assert result.evidence.continuity is ContinuityResult.QUALIFIED
    assert result.canonical_fields == (
        "result.channel",
        "result.data.data.ask",
        "result.data.data.bid",
        "result.data.data.pair",
        "result.data.offset",
    )
    before = result.evidence.canonical_bytes()
    payload["result"]["data"]["offset"] = 99  # type: ignore[index]
    assert result.evidence.canonical_bytes() == before
    assert all(b"ingest:42" not in ref.key.encode() for ref in result.evidence.recovery_evidence_refs)


def test_public_rest_has_no_venue_sequence_and_unknown_resource_is_typed_no_match() -> None:
    public = _qualify(
        product=ProductFamily.PUBLIC_REST,
        resource="/api/depth/{pair}",
        scope=_scope("/api/depth/{pair}"),
        payload={"buy": [], "sell": []},
        venue_cursor=None,
    )
    assert public.evidence is not None
    assert public.evidence.venue_cursor is None
    assert public.evidence.continuity is ContinuityResult.NO_AUTHORITATIVE_SEQUENCE

    missing = _qualify(resource="market:unknown-{pair}")
    assert missing.disposition is EvidenceDisposition.UNQUALIFIED
    assert missing.reason == "NO_MATCH"
    assert missing.evidence is None


def test_field_authority_is_product_local_and_ignores_self_attested_quality() -> None:
    payload = {
        "ticker": {
            "buy": "100",
            "high": "110",
            "last": "105",
            "low": "90",
            "sell": "106",
            "server_time": 1787832000,
        },
        "ask": [],
        "quality": "QUALIFIED",
        "cursor_capability": "VENUE_OFFSET",
    }
    result = _qualify(
        product=ProductFamily.PUBLIC_REST,
        resource="/api/ticker/{pair}",
        scope=_scope("/api/ticker/{pair}"),
        payload=payload,
        venue_cursor=None,
    )

    assert result.disposition is EvidenceDisposition.QUALIFIED
    assert result.canonical_fields == (
        "ticker.buy",
        "ticker.high",
        "ticker.last",
        "ticker.low",
        "ticker.sell",
        "ticker.server_time",
    )
    assert "ask" not in result.canonical_fields
    assert "quality" not in result.canonical_fields
    assert "cursor_capability" not in result.canonical_fields

    with pytest.raises(MarketEvidenceError) as foreign_fields_only:
        _qualify(
            product=ProductFamily.PUBLIC_REST,
            resource="/api/ticker/{pair}",
            scope=_scope("/api/ticker/{pair}"),
            payload={"ticker": {"buy": [], "sell": [], "server_time": 1787832000}},
            venue_cursor=None,
        )
    assert foreign_fields_only.value.code == "MISSING_AUTHORITATIVE_FIELD"
    assert foreign_fields_only.value.partial_result is None


def test_documented_remote_timestamp_must_match_the_explicit_event_time() -> None:
    ticker = {"ticker": {
        "buy": "100", "high": "110", "last": "105", "low": "90",
        "sell": "106", "server_time": 1787831999,
    }}
    with pytest.raises(MarketEvidenceError) as mismatch:
        _qualify(
            product=ProductFamily.PUBLIC_REST,
            resource="/api/ticker/{pair}",
            scope=_scope("/api/ticker/{pair}"),
            payload=ticker,
            venue_cursor=None,
        )
    assert mismatch.value.code == "REMOTE_TIMESTAMP_MISMATCH"
    assert mismatch.value.partial_result is None

    with pytest.raises(MarketEvidenceError) as missing:
        _qualify(
            product=ProductFamily.PRIVATE_WEBSOCKET,
            resource="private:order-update",
            scope=_scope("private:order-update"),
            payload={"push": {"channel": "pws:sanitized", "pub": {"data": [{
                "eventType": "order_update",
                "order": {
                    "orderId": "sanitized-order", "symbol": "btcidr", "side": "BUY",
                    "origQty": "1", "unfilledQty": "0", "executedQty": "1",
                    "price": "100", "description": "BTC/IDR", "status": "FILLED",
                    "clientOrderId": "sanitized-client",
                },
            }]}}},
            venue_cursor=None,
        )
    assert missing.value.code == "MISSING_REMOTE_TIMESTAMP"
    assert missing.value.partial_result is None


def test_official_response_envelopes_and_remote_identity_are_fail_closed() -> None:
    with pytest.raises(MarketEvidenceError) as flattened:
        _qualify(payload={"pair": "btcidr", "ask": [], "bid": [], "offset": 42})
    assert flattened.value.code == "MISSING_AUTHORITATIVE_FIELD"

    foreign_channel = _order_book_payload()
    foreign_channel["result"]["channel"] = "market:order-book-ethidr"  # type: ignore[index]
    with pytest.raises(MarketEvidenceError) as channel_mismatch:
        _qualify(payload=foreign_channel)
    assert channel_mismatch.value.code == "EVIDENCE_SCOPE_MISMATCH"

    foreign_instrument = _order_book_payload()
    foreign_instrument["result"]["data"]["data"]["pair"] = "ethidr"  # type: ignore[index]
    with pytest.raises(MarketEvidenceError) as instrument_mismatch:
        _qualify(payload=foreign_instrument)
    assert instrument_mismatch.value.code == "EVIDENCE_INSTRUMENT_MISMATCH"

    trades = json.loads(
        (FIXTURE_ROOT / "trade_api_v2/trade-api-v2.my-trades.v1.json")
        .read_text(encoding="utf-8")
    )
    trades["data"].append(dict(trades["data"][0]))
    with pytest.raises(MarketEvidenceError) as ambiguous_time:
        _qualify(
            product=ProductFamily.TRADE_API_V2,
            resource="/api/v2/myTrades",
            scope=_scope("/api/v2/myTrades"),
            payload=trades,
            venue_cursor=None,
        )
    assert ambiguous_time.value.code == "AMBIGUOUS_REMOTE_TIMESTAMP"


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"evaluated_at_utc": NOW + timedelta(seconds=3)}, EvidenceDisposition.QUALIFIED),
        ({"evaluated_at_utc": NOW + timedelta(seconds=3, microseconds=1)}, EvidenceDisposition.UNQUALIFIED),
        ({"event_at_utc": NOW - timedelta(seconds=1)}, EvidenceDisposition.QUALIFIED),
        ({"event_at_utc": NOW - timedelta(seconds=1, microseconds=1)}, EvidenceDisposition.UNQUALIFIED),
        ({"event_at_utc": NOW + timedelta(seconds=1, microseconds=1)}, EvidenceDisposition.UNQUALIFIED),
    ],
)
def test_freshness_and_remote_skew_boundaries(changes: dict[str, object], expected: EvidenceDisposition) -> None:
    result = _qualify(**changes)
    assert result.disposition is expected
    if expected is EvidenceDisposition.QUALIFIED:
        assert result.freeze_request is None
        assert result.recovery_request is None
        assert result.reconciliation_request is None
    else:
        assert result.freeze_request is not None
        assert result.recovery_request is not None
        assert result.reconciliation_request is not None


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"venue_cursor": None}, "MISSING_VENUE_CURSOR"),
        ({"venue_cursor": True}, "MISSING_VENUE_CURSOR"),
        ({"venue_cursor": "not-a-number"}, "INVALID_VENUE_CURSOR"),
        ({"venue_cursor": 41}, "VENUE_CURSOR_MISMATCH"),
    ],
)
def test_websocket_cursor_contract_rejects_missing_invalid_and_payload_mismatch(
    changes: dict[str, object], code: str
) -> None:
    with pytest.raises(MarketEvidenceError) as caught:
        _qualify(**changes)
    assert caught.value.code == code
    assert caught.value.partial_result is None


def test_snapshot_product_rejects_a_caller_claimed_venue_cursor() -> None:
    with pytest.raises(MarketEvidenceError) as caught:
        _qualify(
            product=ProductFamily.PUBLIC_REST,
            resource="/api/depth/{pair}",
            scope=_scope("/api/depth/{pair}"),
            payload={"buy": [], "sell": []},
            venue_cursor=42,
        )
    assert caught.value.code == "UNSUPPORTED_VENUE_CURSOR"
    assert caught.value.partial_result is None


def test_gap_regression_conflict_disconnect_and_exact_duplicate_are_local() -> None:
    previous = _qualify().evidence
    assert previous is not None
    duplicate = _qualify(previous_evidence=previous)
    assert duplicate.evidence is not None
    assert duplicate.evidence.continuity is ContinuityResult.EXACT_DUPLICATE
    assert duplicate.freeze_request is None

    conflict = _qualify(previous_evidence=previous, payload=_order_book_payload(x=1))
    assert conflict.evidence is not None
    assert conflict.evidence.continuity is ContinuityResult.CONFLICT
    assert conflict.freeze_request is not None
    assert conflict.freeze_request.scope.kind is ScopeKind.INSTRUMENT_CHANNEL

    gap = _qualify(previous_evidence=previous, venue_cursor=44, payload=_order_book_payload(44))
    assert gap.evidence is not None and gap.evidence.continuity is ContinuityResult.GAP
    regression = _qualify(previous_evidence=previous, venue_cursor=41, payload=_order_book_payload(41))
    assert regression.evidence is not None and regression.evidence.continuity is ContinuityResult.REGRESSION
    disconnected = _qualify(connected=False)
    assert disconnected.evidence is not None and disconnected.evidence.continuity is ContinuityResult.DISCONNECTED

    reconnect_only = _qualify(previous_evidence=disconnected.evidence, connected=True)
    assert reconnect_only.disposition is EvidenceDisposition.UNQUALIFIED
    assert reconnect_only.freeze_request is not None


def test_out_of_order_conflict_is_frozen_and_determinism_holds_for_100_runs() -> None:
    previous = _qualify().evidence
    assert previous is not None
    out_of_order = _qualify(
        previous_evidence=previous,
        venue_cursor=43,
        event_at_utc=NOW - timedelta(seconds=1),
        payload=_order_book_payload(43),
    )
    assert out_of_order.evidence is not None
    assert out_of_order.evidence.continuity is ContinuityResult.OUT_OF_ORDER
    assert out_of_order.freeze_request is not None
    results = [_qualify().evidence.canonical_bytes() for _ in range(100)]
    assert len(set(results)) == 1


def test_deprecated_private_rest_is_unqualified_and_private_ws_requires_rest_recovery() -> None:
    legacy = _qualify(
        product=ProductFamily.PRIVATE_REST,
        resource="tradeHistory",
        scope=_scope("tradeHistory"),
        payload={"success": 1, "return": {"trades": []}},
        venue_cursor=None,
    )
    assert legacy.disposition is EvidenceDisposition.UNQUALIFIED
    assert legacy.reason == "ENTRY_UNQUALIFIED"

    private_ws = _qualify(
        product=ProductFamily.PRIVATE_WEBSOCKET,
        resource="private:order-update",
        scope=_scope("private:order-update"),
        payload=json.loads(
            (FIXTURE_ROOT / "private_websocket/private-ws.order-update.v1.json")
            .read_text(encoding="utf-8")
        ),
        venue_cursor=None,
        connected=False,
    )
    assert private_ws.recovery_request is not None
    assert private_ws.recovery_request.recovery_route == "/api/v2/order/histories"


def test_local_clock_anomaly_is_authority_scoped_safe_latched() -> None:
    result = _qualify(local_clock_anomaly=True)
    assert result.disposition is EvidenceDisposition.SAFE_LATCHED
    assert result.freeze_request is not None
    assert result.freeze_request.scope == AffectedScope(ScopeKind.AUTHORITY, "authority:indodax")
    assert result.reason == "CLOCK_ANOMALY"


def test_verified_local_clock_rollback_is_never_treated_as_pair_local() -> None:
    result = _qualify(evaluated_at_utc=NOW - timedelta(microseconds=1))
    authority_scope = AffectedScope(ScopeKind.AUTHORITY, "authority:indodax")

    assert result.disposition is EvidenceDisposition.SAFE_LATCHED
    assert result.reason == "CLOCK_ANOMALY"
    assert result.evidence is not None
    assert result.evidence.freshness_micros == 0
    assert result.evidence.scope == authority_scope
    assert result.freeze_request is not None
    assert result.freeze_request.scope == authority_scope
    assert result.recovery_request is not None
    assert result.recovery_request.scope == authority_scope


def test_remote_scope_must_match_instrument_and_authority_scope_needs_systemic_proof() -> None:
    with pytest.raises(MarketEvidenceError) as foreign_instrument:
        _qualify(
            scope=AffectedScope(
                ScopeKind.INSTRUMENT_CHANNEL,
                "authority:indodax",
                "ETH-IDR",
                "market:order-book-ethidr",
            )
        )
    assert foreign_instrument.value.code == "EVIDENCE_SCOPE_MISMATCH"

    with pytest.raises(MarketEvidenceError) as foreign_channel:
        _qualify(scope=_scope("market:trade-activity-btcidr"))
    assert foreign_channel.value.code == "EVIDENCE_SCOPE_MISMATCH"
    assert foreign_channel.value.path == ("scope", "channel")

    authority_scope = AffectedScope(ScopeKind.AUTHORITY, "authority:indodax")
    with pytest.raises(MarketEvidenceError) as unproven:
        _qualify(scope=authority_scope, connected=False)
    assert unproven.value.code == "UNPROVEN_AUTHORITY_SCOPE"

    systemic = _qualify(
        scope=authority_scope,
        connected=False,
        systemic_integrity_proven=True,
    )
    assert systemic.freeze_request is not None
    assert systemic.freeze_request.scope == authority_scope


def test_recovery_gate_is_pure_and_requires_matching_recovery_and_reconciliation() -> None:
    failed = _qualify(connected=False)
    request = failed.recovery_request
    assert request is not None
    proof = RecoveryProof.create(
        capability_ref=request.capability_ref,
        capability_version=request.capability_version,
        scope=request.scope,
        recovery_route=request.recovery_route,
        qualified=True,
    )
    checkpoint = ReconciliationCheckpoint.create(
        capability_ref=request.capability_ref,
        capability_version=request.capability_version,
        scope=request.scope,
        requirement_set_ref=request.requirement_set_ref,
        current=True,
    )
    assert evaluate_recovery_gate(request, proof, None).disposition is RecoveryDisposition.FROZEN
    assert evaluate_recovery_gate(request, None, checkpoint).disposition is RecoveryDisposition.FROZEN
    cleared = evaluate_recovery_gate(request, proof, checkpoint)
    assert cleared.disposition is RecoveryDisposition.CLEAR_REQUESTED
    assert cleared.clear_request is not None
    assert cleared.clear_request.scope == request.scope

    foreign = RecoveryProof.create(
        capability_ref=request.capability_ref,
        capability_version=request.capability_version,
        scope=AffectedScope(
            ScopeKind.INSTRUMENT_CHANNEL,
            "authority:indodax",
            "ETH-IDR",
            request.scope.channel,
        ),
        recovery_route=request.recovery_route,
        qualified=True,
    )
    assert evaluate_recovery_gate(request, foreign, checkpoint).disposition is RecoveryDisposition.FROZEN

    foreign_version = RecoveryProof.create(
        capability_ref=request.capability_ref,
        capability_version="foreign-version",
        scope=request.scope,
        recovery_route=request.recovery_route,
        qualified=True,
    )
    assert (
        evaluate_recovery_gate(request, foreign_version, checkpoint).disposition
        is RecoveryDisposition.FROZEN
    )

    mismatched_inputs = (
        (
            RecoveryProof.create(
                capability_ref=request.capability_ref,
                capability_version=request.capability_version,
                scope=request.scope,
                recovery_route=request.recovery_route,
                qualified=False,
            ),
            checkpoint,
        ),
        (
            RecoveryProof.create(
                capability_ref=request.capability_ref,
                capability_version=request.capability_version,
                scope=request.scope,
                recovery_route="/foreign-recovery",
                qualified=True,
            ),
            checkpoint,
        ),
        (
            proof,
            ReconciliationCheckpoint.create(
                capability_ref=request.capability_ref,
                capability_version=request.capability_version,
                scope=request.scope,
                requirement_set_ref=request.requirement_set_ref,
                current=False,
            ),
        ),
        (
            proof,
            ReconciliationCheckpoint.create(
                capability_ref=request.capability_ref,
                capability_version=request.capability_version,
                scope=request.scope,
                requirement_set_ref=ContentRef.v2(
                    "market.recovery-requirements",
                    "recovery-requirement-set",
                    {"foreign": True},
                ),
                current=True,
            ),
        ),
    )
    for mismatched_proof, mismatched_checkpoint in mismatched_inputs:
        result = evaluate_recovery_gate(request, mismatched_proof, mismatched_checkpoint)
        assert result.disposition is RecoveryDisposition.FROZEN
        assert result.clear_request is None
        assert result.reason == "PROOF_MISMATCH"

    with pytest.raises(RecoveryEvaluationError) as forged:
        replace(proof, qualified=False)
    assert forged.value.code == "RECOVERY_PROOF_MISMATCH"


def test_market_evidence_rejects_compatibility_recipe_even_with_matching_digest() -> None:
    evidence = _qualify().evidence
    assert evidence is not None
    compatibility_ref = ContentRef.v1("market-evidence", evidence.binding_value())
    with pytest.raises(MarketEvidenceError) as mismatch:
        replace(evidence, evidence_ref=compatibility_ref)
    assert mismatch.value.code == "EVIDENCE_CONTENT_MISMATCH"


def test_market_evidence_rejects_self_attested_qualified_failure() -> None:
    evidence = _qualify().evidence
    assert evidence is not None
    binding = evidence.binding_value()
    binding["continuity"] = ContinuityResult.GAP.value
    forged_ref = ContentRef.v2("market.evidence", "market-evidence", binding)
    with pytest.raises(MarketEvidenceError) as mismatch:
        replace(
            evidence,
            continuity=ContinuityResult.GAP,
            evidence_ref=forged_ref,
        )
    assert mismatch.value.code == "INVALID_EVIDENCE_DISPOSITION"


def test_structural_invalid_input_is_rejected_atomically_and_secrets_are_forbidden() -> None:
    with pytest.raises(MarketEvidenceError) as naive:
        _qualify(event_at_utc=datetime(2026, 8, 27, 12))
    assert naive.value.partial_result is None
    with pytest.raises(MarketEvidenceError) as non_utc:
        _qualify(event_at_utc=NOW.astimezone(timezone(timedelta(hours=7))))
    assert non_utc.value.code == "INVALID_EVIDENCE_TIME"
    with pytest.raises(MarketEvidenceError) as secret:
        _qualify(payload=_order_book_payload(api_key="not-allowed"))
    assert secret.value.code == "SECRET_BEARING_EVIDENCE"
