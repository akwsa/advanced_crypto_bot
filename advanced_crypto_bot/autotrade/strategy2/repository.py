"""Atomic, namespaced SQLite repository for Strategy 2 Phase 1.

This module deliberately has no exchange/runtime integration and only accesses
``strategy2_*`` tables created by :class:`core.database.Database`.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
import math
from typing import Any, Mapping

from .contracts import stable_idempotency_key
from .state_machine import InvalidTransitionError, validate_transition
from .taxonomy import DecisionStatus, PositionState, ReasonCode, TERMINAL_POSITION_STATES


def _json(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    if value is not None and not isinstance(value, (Mapping, list, tuple)):
        raise TypeError("journal payload must be a mapping or sequence")
    def normalize(item):
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise TypeError("journal payload mapping keys must be strings")
            return {key: normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if item is None or isinstance(item, (str, bool, int)):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("journal payload contains non-finite numeric data")
            return item
        raise TypeError(f"unsupported journal payload value: {type(item).__name__}")
    return json.dumps(normalize({} if value is None else value), allow_nan=False, sort_keys=True, separators=(",", ":"))


def _nonempty(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must be non-empty")
    return text


def _finite(name: str, value: Any, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if positive and number <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and number < 0:
        raise ValueError(f"{name} must be non-negative")
    if number == 0:
        return 0.0
    return number


def _user_id(value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("user_id must be a positive integer")
    return value


def _pair(value: Any) -> str:
    pair = _nonempty("pair", value).upper().replace("/", "").replace("_", "").replace("-", "")
    if not pair:
        raise ValueError("pair must be non-empty")
    return pair


def _same(row, expected: Mapping[str, Any], kind: str):
    conflicts = [key for key, value in expected.items() if row[key] != value]
    if conflicts:
        raise ValueError(f"{kind} idempotency conflict: {', '.join(conflicts)}")
    return row


def _close_payload(price: float, quantity: float, fee: float, target: PositionState) -> Mapping[str, Any]:
    return {
        "operation": "close",
        "price": price,
        "quantity": quantity,
        "fee": fee,
        "target_state": target.value,
    }


class Strategy2Repository:
    """Persist one isolated Strategy 2 experiment using atomic projections."""

    def __init__(self, database, *, strategy_version: str, experiment_id: str,
                 initial_cash: float):
        self.database = database
        self.strategy_version = _nonempty("strategy_version", strategy_version)
        self.experiment_id = _nonempty("experiment_id", experiment_id)
        self.initial_cash = _finite("initial_cash", initial_cash, positive=True)

    @property
    def namespace(self):
        return self.strategy_version, self.experiment_id

    def _ensure_portfolio(self, conn, user_id: int):
        user_id = _user_id(user_id)
        conn.execute('''
            INSERT OR IGNORE INTO strategy2_portfolios
            (strategy_version,experiment_id,user_id,cash,initial_cash)
            VALUES(?,?,?,?,?)
        ''', (*self.namespace, int(user_id), self.initial_cash, self.initial_cash))
        row = conn.execute('''
            SELECT * FROM strategy2_portfolios
            WHERE strategy_version=? AND experiment_id=? AND user_id=?
        ''', (*self.namespace, int(user_id))).fetchone()
        if float(row["initial_cash"]) != self.initial_cash:
            raise ValueError("Strategy 2 initial_cash conflicts with existing portfolio")
        return row

    def get_portfolio(self, user_id: int):
        with self.database.get_connection() as conn:
            return self._ensure_portfolio(conn, user_id)

    def get_position(self, user_id: int, pair: str):
        with self.database.get_connection() as conn:
            return conn.execute('''
                SELECT * FROM strategy2_positions
                WHERE strategy_version=? AND experiment_id=? AND user_id=? AND pair=?
            ''', (*self.namespace, _user_id(user_id), _pair(pair))).fetchone()

    def record_decision(self, *, operation_identity: str, idempotency_key: str, correlation_id: str,
                        snapshot_id: str, pair: str, status: Any,
                        reason_code: Any, reason: str = "",
                        evidence: Mapping[str, Any] | None = None):
        """Insert an immutable decision once and return its canonical row."""
        status_value = DecisionStatus(status).value
        reason_value = ReasonCode(reason_code).value
        operation_identity = _nonempty("operation_identity", operation_identity)
        expected_key = stable_idempotency_key(*self.namespace, operation_identity)
        if idempotency_key != expected_key:
            raise ValueError("idempotency_key does not match Strategy 2 namespace")
        pair = _pair(pair)
        evidence_json = _json(evidence)
        values = (
            *self.namespace,
            _nonempty("idempotency_key", idempotency_key),
            _nonempty("correlation_id", correlation_id),
            _nonempty("snapshot_id", snapshot_id),
            pair,
            _nonempty("status", status_value),
            _nonempty("reason_code", reason_value),
            str(reason or ""),
            evidence_json,
        )
        with self.database.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute('''
                INSERT OR IGNORE INTO strategy2_decisions
                (strategy_version,experiment_id,idempotency_key,correlation_id,
                 snapshot_id,pair,status,reason_code,reason,evidence_json)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            ''', values)
            row = conn.execute('''
                SELECT * FROM strategy2_decisions
                WHERE strategy_version=? AND experiment_id=? AND idempotency_key=?
            ''', (*self.namespace, values[2])).fetchone()
            return _same(row, {
                "correlation_id": values[3], "snapshot_id": values[4], "pair": pair,
                "status": status_value, "reason_code": reason_value,
                "reason": str(reason or ""), "evidence_json": evidence_json,
            }, "decision")

    def transition(self, *, user_id: int, pair: str, event_key: str,
                   correlation_id: str, snapshot_id: str, to_state: Any,
                   reason_code: Any, event: Mapping[str, Any] | None = None):
        """Apply one legal lifecycle transition, idempotently and atomically."""
        user_id, pair = _user_id(user_id), _pair(pair)
        event_key = _nonempty("event_key", event_key)
        target = PositionState(getattr(to_state, "value", to_state))
        reason = ReasonCode(reason_code).value
        with self.database.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior_event = self._event(conn, event_key)
            if prior_event:
                return self._verify_event(prior_event, user_id, pair, correlation_id,
                                          snapshot_id, target, reason, event)
            position = self._position(conn, user_id, pair)
            current = PositionState(position["state"]) if position else None
            if current is None:
                if target != PositionState.CANDIDATE:
                    raise InvalidTransitionError(None, target)
            else:
                if current == target:
                    raise ValueError("fresh same-state transition is not allowed")
                validate_transition(current, target)
            if position and float(position["quantity"]) > 0 and target in TERMINAL_POSITION_STATES:
                raise ValueError("terminal transition with quantity requires atomic settlement")
            conn.execute('''
                INSERT INTO strategy2_state_events
                (strategy_version,experiment_id,event_key,correlation_id,snapshot_id,
                 user_id,pair,from_state,to_state,reason_code,event_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ''', (*self.namespace, event_key, _nonempty("correlation_id", correlation_id),
                  _nonempty("snapshot_id", snapshot_id), user_id, pair,
                  current.value if current else None, target.value, reason, _json(event)))
            if position:
                conn.execute('''UPDATE strategy2_positions SET state=?,updated_at=CURRENT_TIMESTAMP
                    WHERE id=?''', (target.value, position["id"]))
            else:
                conn.execute('''INSERT INTO strategy2_positions
                    (strategy_version,experiment_id,user_id,pair,state,quantity,avg_price,cost_basis,fees)
                    VALUES(?,?,?,?,?,0,0,0,0)''', (*self.namespace, user_id, pair, target.value))
            return self._event(conn, event_key)

    def record_audit_event(self, *, user_id: int | None, pair: str, event_key: str,
                           correlation_id: str, snapshot_id: str, state: Any | None,
                           reason_code: Any, event: Mapping[str, Any] | None = None):
        """Persist an additive audit event without mutating Strategy 2 projections."""
        pair = _pair(pair)
        event_key = _nonempty("event_key", event_key)
        snapshot_id = _nonempty("snapshot_id", snapshot_id)
        correlation_id = _nonempty("correlation_id", correlation_id)
        state_value = None if state is None else PositionState(getattr(state, "value", state)).value
        if user_id is not None:
            normalized_user_id = _user_id(user_id)
        else:
            normalized_user_id = 0
        with self.database.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior_event = self._event(conn, event_key)
            if prior_event:
                return _same(prior_event, {
                    "user_id": normalized_user_id,
                    "pair": pair,
                    "correlation_id": correlation_id,
                    "snapshot_id": snapshot_id,
                    "from_state": state_value,
                    "to_state": state_value,
                    "reason_code": ReasonCode(reason_code).value,
                    "event_json": _json(event),
                }, "event")
            conn.execute('''INSERT INTO strategy2_state_events
                (strategy_version,experiment_id,event_key,correlation_id,snapshot_id,user_id,pair,
                 from_state,to_state,reason_code,event_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                (*self.namespace, event_key, correlation_id, snapshot_id, normalized_user_id,
                 pair, state_value, state_value, ReasonCode(reason_code).value, _json(event)))
            return self._event(conn, event_key)

    def open_position(self, *, user_id: int, pair: str, event_key: str,
                      correlation_id: str, snapshot_id: str, price: float,
                      quantity: float, fee: float, reason_code: Any):
        """Debit isolated cash and open a PENDING position exactly once."""
        price = _finite("price", price, positive=True)
        quantity = _finite("quantity", quantity, positive=True)
        fee = _finite("fee", fee, nonnegative=True)
        notional = price * quantity
        required = notional + fee
        if not math.isfinite(notional) or notional <= 0 or not math.isfinite(required):
            raise ValueError("entry total must be positive and finite")
        user_id, pair, event_key = _user_id(user_id), _pair(pair), _nonempty("event_key", event_key)
        payload = {"operation": "open", "price": price, "quantity": quantity, "fee": fee}
        with self.database.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior_event = self._event(conn, event_key)
            if prior_event:
                return self._verify_event(prior_event, user_id, pair, correlation_id, snapshot_id,
                    PositionState.OPEN_RISK, reason_code, payload)
            portfolio = self._ensure_portfolio(conn, user_id)
            position = self._position(conn, user_id, pair)
            if not position or PositionState(position["state"]) != PositionState.PENDING:
                raise ValueError("virtual entry requires an existing PENDING position")
            if float(position["quantity"]) > 0:
                raise ValueError("position is already open")
            validate_transition(PositionState.PENDING, PositionState.OPEN_RISK)
            updated = conn.execute('''UPDATE strategy2_portfolios SET cash=cash-?,updated_at=CURRENT_TIMESTAMP
                WHERE strategy_version=? AND experiment_id=? AND user_id=? AND cash>=?''',
                (required, *self.namespace, int(user_id), required)).rowcount
            if updated != 1:
                raise ValueError("insufficient Strategy 2 virtual cash")
            conn.execute('''UPDATE strategy2_positions SET state=?,quantity=?,avg_price=?,cost_basis=?,fees=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?''', (PositionState.OPEN_RISK.value, quantity, price, notional, fee, position["id"]))
            self._insert_event(conn, user_id, pair, event_key, correlation_id, snapshot_id,
                               PositionState.PENDING, PositionState.OPEN_RISK, reason_code, payload)
            return self._event(conn, event_key)

    def close_position(self, *, user_id: int, pair: str, event_key: str,
                       correlation_id: str, snapshot_id: str, price: float,
                       quantity: float, fee: float, reason_code: Any):
        """Credit proceeds and reduce/close an isolated position exactly once."""
        return self.settle_position(
            user_id=user_id,
            pair=pair,
            event_key=event_key,
            correlation_id=correlation_id,
            snapshot_id=snapshot_id,
            price=price,
            quantity=quantity,
            fee=fee,
            reason_code=reason_code,
            target_state=PositionState.CLOSED,
        )

    def settle_position(self, *, user_id: int, pair: str, event_key: str,
                        correlation_id: str, snapshot_id: str, price: float,
                        quantity: float, fee: float, reason_code: Any,
                        target_state: Any):
        """Atomically credit proceeds and settle to a terminal or retained risk state."""
        price = _finite("price", price, positive=True)
        quantity = _finite("quantity", quantity, positive=True)
        fee = _finite("fee", fee, nonnegative=True)
        proceeds = price * quantity
        if not math.isfinite(proceeds) or proceeds <= 0 or fee > proceeds:
            raise ValueError("fee cannot exceed finite proceeds")
        user_id, pair, event_key = _user_id(user_id), _pair(pair), _nonempty("event_key", event_key)
        requested_target = PositionState(getattr(target_state, "value", target_state))
        with self.database.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior_event = self._event(conn, event_key)
            if prior_event:
                expected_target = PositionState(prior_event["to_state"])
                return self._verify_event(prior_event, user_id, pair, correlation_id, snapshot_id,
                    expected_target, reason_code, _close_payload(price, quantity, fee, expected_target))
            position = self._position(conn, user_id, pair)
            if not position or float(position["quantity"]) <= 0:
                raise ValueError("no open Strategy 2 position")
            old_qty = float(position["quantity"])
            if quantity > old_qty:
                raise ValueError("sell exceeds Strategy 2 position")
            portfolio = self._ensure_portfolio(conn, user_id)
            remaining = max(0.0, old_qty - quantity)
            if remaining <= 1e-12:
                remaining = 0.0
            current = PositionState(position["state"])
            if current not in {PositionState.OPEN_RISK, PositionState.BREAK_EVEN, PositionState.PROFIT_PROTECTED}:
                raise InvalidTransitionError(current, PositionState.CLOSED)
            if remaining > 0 and requested_target == PositionState.CLOSED:
                requested_target = current
            elif remaining > 0 and requested_target != current:
                raise InvalidTransitionError(current, requested_target)
            target = requested_target if remaining == 0 else current
            if target == PositionState.CLOSED:
                validate_transition(current, target)
            elif remaining == 0:
                validate_transition(current, target)
            ratio = remaining / old_qty if remaining else 0.0
            new_cash = float(portfolio["cash"]) + proceeds - fee
            if not math.isfinite(new_cash):
                raise ValueError("portfolio cash must remain finite")
            conn.execute('''UPDATE strategy2_portfolios SET cash=?,updated_at=CURRENT_TIMESTAMP
                WHERE strategy_version=? AND experiment_id=? AND user_id=?''',
                (new_cash, *self.namespace, int(user_id)))
            conn.execute('''UPDATE strategy2_positions SET state=?,quantity=?,avg_price=?,cost_basis=?,fees=fees+?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?''', (target.value, remaining,
                    float(position["avg_price"]) if remaining else 0.0,
                    float(position["cost_basis"]) * ratio, fee, position["id"]))
            self._insert_event(conn, user_id, pair, event_key, correlation_id, snapshot_id,
                               current, target, reason_code, _close_payload(price, quantity, fee, target))
            return self._event(conn, event_key)

    def _position(self, conn, user_id, pair):
        return conn.execute('''SELECT * FROM strategy2_positions
            WHERE strategy_version=? AND experiment_id=? AND user_id=? AND pair=?''',
            (*self.namespace, int(user_id), pair)).fetchone()

    def _event(self, conn, event_key):
        return conn.execute('''SELECT * FROM strategy2_state_events
            WHERE strategy_version=? AND experiment_id=? AND event_key=?''',
            (*self.namespace, event_key)).fetchone()

    def _insert_event(self, conn, user_id, pair, event_key, correlation_id,
                      snapshot_id, current, target, reason_code, payload):
        conn.execute('''INSERT INTO strategy2_state_events
            (strategy_version,experiment_id,event_key,correlation_id,snapshot_id,user_id,pair,
             from_state,to_state,reason_code,event_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            (*self.namespace, event_key, _nonempty("correlation_id", correlation_id),
             _nonempty("snapshot_id", snapshot_id), int(user_id), pair,
             current.value if current else None, target.value,
             ReasonCode(reason_code).value, _json(payload)))

    def _verify_event(self, row, user_id, pair, correlation_id, snapshot_id,
                      target, reason_code, payload):
        return _same(row, {
            "user_id": _user_id(user_id), "pair": _pair(pair),
            "correlation_id": _nonempty("correlation_id", correlation_id),
            "snapshot_id": _nonempty("snapshot_id", snapshot_id),
            "to_state": PositionState(target).value,
            "reason_code": ReasonCode(reason_code).value,
            "event_json": _json(payload),
        }, "event")
