"""Pinned offline Indodax capability catalog; no legacy or network fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.encoding import canonical_bytes
from autotrade_next.domain.market import (
    AuthScope,
    CapabilityArtifact,
    CapabilityEntry,
    CapabilityRegistry,
    CursorCapability,
    ProductFamily,
    QualificationStatus,
    RateLimitContract,
    RateLimitStatus,
    RecoveryContract,
    RecoveryMode,
    TimestampContract,
    TimestampUnit,
)


_COMMIT = "2e0c1fecb04cd30465ad81fd4be11ae66b5d0e19"
# The qualification cannot pre-date the exact documentation object used as
# evidence.  Commit 2e0c1fe was authored at 2026-03-03T15:12:12+07:00.
_EFFECTIVE_FROM = datetime(2026, 3, 3, 8, 12, 12, tzinfo=UTC)
_DOCUMENT_COORDINATES = {
    "Public-RestAPI.md": (
        "9694c93b309dc9ba0c2d427190c37655e7cd4008",
        "aa5b9d30d9d07d196fae2cbdce26a0e71887f4f6c62d5af3d491aae943e2972c",
    ),
    "Private-RestAPI.md": (
        "26a9ddea4c8da0df9004466c7d51ae0811236cf0",
        "051d5c1437c4f3d756c2dfe13f9ba3c649f304323be3e62a448d348a85574e23",
    ),
    "INDODAX-TradeAPI-2.md": (
        "205ecaead0aa22b85bfdbff086cf4cb9bab780eb",
        "b094830f2993a877253a8c5592b59f0429b2dc6e5fccfd2c9d911512ec47efa4",
    ),
    "Marketdata-websocket.md": (
        "fb28a8009f706c2d2863f6b1da569fe81061833f",
        "0bd22b40559d1adb26b5b9097b9d1201d3abf8f08910acdf071563afbeeda46f",
    ),
    "Private-websocket.md": (
        "ea9e31464c769d48939321809c6eebed5651c128",
        "aca2ffc60b73a26aeba141a9ff9091e99bd9cb1fddc828784cad7f2223f2568f",
    ),
}
_UNDOCUMENTED_RATE_LIMIT = RateLimitContract(RateLimitStatus.NOT_DOCUMENTED)
_PUBLIC_REST_RATE_LIMIT = RateLimitContract(
    RateLimitStatus.DOCUMENTED,
    180,
    60_000_000,
)
_SANITIZED_PAYLOADS: dict[str, object] = {
    "public-rest.depth.v1": {"buy": [], "sell": []},
    "public-rest.ticker.v1": {
        "ticker": {
            "buy": "100", "high": "110", "last": "105", "low": "90",
            "sell": "106", "server_time": 1787832000,
        },
    },
    "private-rest.get-info.v1": {
        "success": 1,
        "return": {"balance": {}, "balance_hold": {}, "server_time": 1787832000},
    },
    "private-rest.trade-history.deprecated": {
        "success": 1,
        "return": {"trades": []},
    },
    "trade-api-v2.my-trades.v1": {
        "data": [{
            "tradeId": "sanitized-trade", "orderId": "sanitized-order",
            "clientOrderId": "sanitized-client", "symbol": "btcidr",
            "price": "100", "qty": "1", "quoteQty": "100",
            "commission": "1", "commissionAsset": "idr",
            "isBuyer": True, "isMaker": False, "time": 1787832000000,
        }],
    },
    "trade-api-v2.order-histories.v1": {
        "data": [{
            "orderId": "sanitized-order", "clientOrderId": "sanitized-client",
            "symbol": "btcidr", "side": "BUY", "type": "LIMIT",
            "status": "FILLED", "price": "100", "oriQty": "1",
            "executedQty": "1", "submitTime": 1787831999000,
            "finishTime": 1787832000000,
        }],
    },
    "market-ws.order-book.v1": {
        "result": {
            "channel": "market:order-book-btcidr",
            "data": {"data": {"pair": "btcidr", "ask": [], "bid": []}, "offset": 0},
        },
    },
    "market-ws.trade-activity.v1": {
        "result": {
            "channel": "market:trade-activity-btcidr",
            "data": {"data": [["btcidr", 1787832000, 1, "buy", 100, "100", "1"]], "offset": 0},
        },
    },
    "private-ws.order-update.v1": {
        "push": {
            "channel": "pws:sanitized",
            "pub": {"data": [{
                "eventType": "order_update",
                "order": {
                    "orderId": "sanitized-order", "symbol": "btcidr", "side": "BUY",
                    "origQty": "1", "unfilledQty": "0", "executedQty": "1",
                    "price": "100", "description": "BTC/IDR", "status": "FILLED",
                    "transactionTime": 1787832000000,
                    "clientOrderId": "sanitized-client",
                },
            }]},
        },
    },
}


def _artifact(
    *, artifact_id: str, document_path: str, assertions: tuple[str, ...],
    fields: tuple[str, ...], payload: object,
) -> CapabilityArtifact:
    # Coordinates were independently derived from the exact vendored bytes and
    # the Git tree at _COMMIT. Contract tests recompute both algorithms offline.
    blob_digest, content_digest = _DOCUMENT_COORDINATES[document_path]
    payload_digest = sha256(canonical_bytes(payload)).hexdigest()
    value = {
        "artifact_id": artifact_id,
        "repository_commit": _COMMIT,
        "document_path": document_path,
        "git_blob_digest": blob_digest,
        "document_content_digest": content_digest,
        "extracted_assertions": assertions,
        "authoritative_fields": fields,
        "sanitized_payload_digest": payload_digest,
    }
    return CapabilityArtifact(
        artifact_id=artifact_id,
        repository_commit=_COMMIT,
        document_path=document_path,
        git_blob_digest=blob_digest,
        document_content_digest=content_digest,
        extracted_assertions=assertions,
        authoritative_fields=fields,
        sanitized_payload_digest=payload_digest,
        contract_ref=ContentRef.v2("indodax.contract-artifact", "capability-artifact", value),
    )


def _entry(
    *, capability_id: str, product: ProductFamily, base_url: str, resource: str,
    document_path: str, fields: tuple[str, ...], cursor: CursorCapability,
    auth: AuthScope, recovery: RecoveryContract, assertions: tuple[str, ...],
    timestamp: TimestampContract = TimestampContract(TimestampUnit.NONE, None),
    status: QualificationStatus = QualificationStatus.QUALIFIED,
    rate: RateLimitContract = _UNDOCUMENTED_RATE_LIMIT,
) -> CapabilityEntry:
    artifact = _artifact(
        artifact_id=f"indodax:{capability_id}:artifact:v1",
        document_path=document_path,
        assertions=assertions,
        fields=fields,
        payload=_SANITIZED_PAYLOADS[capability_id],
    )
    return CapabilityEntry(
        capability_id=capability_id,
        version="indodax-docs:2026-03-03",
        product=product,
        base_url=base_url,
        resource=resource,
        documentation_commit=_COMMIT,
        document_path=document_path,
        git_blob_digest=artifact.git_blob_digest,
        document_content_digest=artifact.document_content_digest,
        effective_from=_EFFECTIVE_FROM,
        effective_until=None,
        auth_scope=auth,
        authoritative_fields=fields,
        cursor_capability=cursor,
        snapshot_source=resource,
        timestamp_contract=timestamp,
        rate_limit_contract=rate,
        recovery_contract=recovery,
        qualification_status=status,
        artifact=artifact,
    )


def build_indodax_capability_registry() -> CapabilityRegistry:
    entries = (
        _entry(
            capability_id="public-rest.depth.v1", product=ProductFamily.PUBLIC_REST,
            base_url="https://indodax.com", resource="/api/depth/{pair}",
            document_path="Public-RestAPI.md", fields=("buy", "sell"),
            cursor=CursorCapability.NO_AUTHORITATIVE_SEQUENCE, auth=AuthScope.PUBLIC,
            recovery=RecoveryContract(RecoveryMode.SNAPSHOT, "/api/depth/{pair}"),
            assertions=("depth buy/sell are endpoint-local snapshot fields",),
            rate=_PUBLIC_REST_RATE_LIMIT,
        ),
        _entry(
            capability_id="public-rest.ticker.v1", product=ProductFamily.PUBLIC_REST,
            base_url="https://indodax.com", resource="/api/ticker/{pair}",
            document_path="Public-RestAPI.md", fields=(
                "ticker.buy", "ticker.high", "ticker.last", "ticker.low",
                "ticker.sell", "ticker.server_time",
            ),
            cursor=CursorCapability.NO_AUTHORITATIVE_SEQUENCE, auth=AuthScope.PUBLIC,
            recovery=RecoveryContract(RecoveryMode.SNAPSHOT, "/api/ticker/{pair}"),
            assertions=("ticker fields do not establish order-book continuity",),
            timestamp=TimestampContract(TimestampUnit.SECONDS, "ticker.server_time"),
            rate=_PUBLIC_REST_RATE_LIMIT,
        ),
        _entry(
            capability_id="private-rest.get-info.v1", product=ProductFamily.PRIVATE_REST,
            base_url="https://indodax.com/tapi", resource="getInfo",
            document_path="Private-RestAPI.md", fields=(
                "return.balance", "return.balance_hold", "return.server_time",
            ),
            cursor=CursorCapability.NO_AUTHORITATIVE_SEQUENCE, auth=AuthScope.PRIVATE_READ,
            recovery=RecoveryContract(RecoveryMode.REST_RECONCILIATION, "getInfo"),
            assertions=("getInfo uses Key and HMAC-SHA512; its response example uses seconds",),
            timestamp=TimestampContract(TimestampUnit.SECONDS, "return.server_time"),
        ),
        _entry(
            capability_id="private-rest.trade-history.deprecated", product=ProductFamily.PRIVATE_REST,
            base_url="https://indodax.com/tapi", resource="tradeHistory",
            document_path="Private-RestAPI.md", fields=("return.trades",),
            cursor=CursorCapability.NO_AUTHORITATIVE_SEQUENCE, auth=AuthScope.PRIVATE_READ,
            recovery=RecoveryContract(RecoveryMode.NONE, None),
            assertions=("legacy tradeHistory is not an authoritative recovery route",),
            status=QualificationStatus.UNQUALIFIED,
        ),
        _entry(
            capability_id="trade-api-v2.my-trades.v1", product=ProductFamily.TRADE_API_V2,
            base_url="https://tapi.indodax.com", resource="/api/v2/myTrades",
            document_path="INDODAX-TradeAPI-2.md", fields=(
                "data[].tradeId", "data[].orderId", "data[].clientOrderId",
                "data[].symbol", "data[].price", "data[].qty", "data[].quoteQty",
                "data[].commission", "data[].commissionAsset", "data[].isBuyer",
                "data[].isMaker", "data[].time",
            ),
            cursor=CursorCapability.NO_AUTHORITATIVE_SEQUENCE, auth=AuthScope.TRADE_API_V2_READ,
            recovery=RecoveryContract(RecoveryMode.REST_RECONCILIATION, "/api/v2/myTrades"),
            assertions=("Trade API 2.0 uses X-APIKEY and HMAC-SHA512",),
            timestamp=TimestampContract(TimestampUnit.MILLISECONDS, "data[].time"),
        ),
        _entry(
            capability_id="trade-api-v2.order-histories.v1", product=ProductFamily.TRADE_API_V2,
            base_url="https://tapi.indodax.com", resource="/api/v2/order/histories",
            document_path="INDODAX-TradeAPI-2.md", fields=(
                "data[].orderId", "data[].clientOrderId", "data[].symbol",
                "data[].side", "data[].type", "data[].status", "data[].price",
                "data[].oriQty", "data[].executedQty", "data[].submitTime",
                "data[].finishTime",
            ),
            cursor=CursorCapability.NO_AUTHORITATIVE_SEQUENCE, auth=AuthScope.TRADE_API_V2_READ,
            recovery=RecoveryContract(
                RecoveryMode.REST_RECONCILIATION,
                "/api/v2/order/histories",
                "trade-api-v2.order-histories.v1",
            ),
            assertions=("order histories is the pinned reconciliation route",),
            timestamp=TimestampContract(TimestampUnit.MILLISECONDS, "data[].finishTime"),
        ),
        _entry(
            capability_id="market-ws.order-book.v1", product=ProductFamily.MARKET_DATA_WEBSOCKET,
            base_url="wss://ws3.indodax.com/ws/", resource="market:order-book-{pair}",
            document_path="Marketdata-websocket.md", fields=(
                "result.channel", "result.data.data.ask", "result.data.data.bid",
                "result.data.data.pair", "result.data.offset",
            ),
            cursor=CursorCapability.VENUE_OFFSET, auth=AuthScope.PUBLIC,
            recovery=RecoveryContract(RecoveryMode.OFFSET_REPLAY, "market:order-book-{pair}"),
            assertions=("order-book offset and recovery are channel-local",),
        ),
        _entry(
            capability_id="market-ws.trade-activity.v1", product=ProductFamily.MARKET_DATA_WEBSOCKET,
            base_url="wss://ws3.indodax.com/ws/", resource="market:trade-activity-{pair}",
            document_path="Marketdata-websocket.md", fields=(
                "result.channel", "result.data.data[].0", "result.data.data[].1",
                "result.data.data[].2", "result.data.data[].3", "result.data.data[].4",
                "result.data.data[].5", "result.data.data[].6", "result.data.offset",
            ),
            cursor=CursorCapability.VENUE_OFFSET, auth=AuthScope.PUBLIC,
            recovery=RecoveryContract(RecoveryMode.OFFSET_REPLAY, "market:trade-activity-{pair}"),
            assertions=("trade activity offset is not inherited by other channels",),
            timestamp=TimestampContract(TimestampUnit.SECONDS, "result.data.data[].1"),
        ),
        _entry(
            capability_id="private-ws.order-update.v1", product=ProductFamily.PRIVATE_WEBSOCKET,
            base_url="wss://pws.indodax.com/ws/?cf_ws_frame_ping_pong=true", resource="private:order-update",
            document_path="Private-websocket.md", fields=(
                "push.channel", "push.pub.data[].eventType",
                "push.pub.data[].order.orderId", "push.pub.data[].order.symbol",
                "push.pub.data[].order.side", "push.pub.data[].order.origQty",
                "push.pub.data[].order.unfilledQty", "push.pub.data[].order.executedQty",
                "push.pub.data[].order.price", "push.pub.data[].order.description",
                "push.pub.data[].order.status", "push.pub.data[].order.transactionTime",
                "push.pub.data[].order.clientOrderId",
            ),
            cursor=CursorCapability.NO_AUTHORITATIVE_SEQUENCE, auth=AuthScope.PRIVATE_WEBSOCKET_READ,
            recovery=RecoveryContract(
                RecoveryMode.REST_RECONCILIATION,
                "/api/v2/order/histories",
                "trade-api-v2.order-histories.v1",
            ),
            assertions=("private WebSocket event requires REST reconciliation",),
            timestamp=TimestampContract(
                TimestampUnit.MILLISECONDS,
                "push.pub.data[].order.transactionTime",
            ),
        ),
    )
    return CapabilityRegistry(entries)


INDODAX_CAPABILITY_REGISTRY = build_indodax_capability_registry()


__all__ = ("INDODAX_CAPABILITY_REGISTRY", "build_indodax_capability_registry")
