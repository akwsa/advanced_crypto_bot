# AutoTrade Strategy 2 — Phase 1 Foundation + Phase 2 Shadow Runtime

Strategy 2 is an isolated, patient net-profit swing experiment. Phase 1 only
provides typed contracts, lifecycle validation, and a virtual SQLite ledger. It
does not subscribe to the signal queue, call an exchange, place an order, or
change Strategy 1.

## Configuration

All settings are namespaced and default off:

```dotenv
AUTOTRADE_STRATEGY2_ENABLED=false
AUTOTRADE_STRATEGY2_MODE=off
AUTOTRADE_STRATEGY2_VERSION=patient-swing-v1
AUTOTRADE_STRATEGY2_INITIAL_CASH_IDR=10000000
```

Only `off` and `shadow` are allowlisted. Invalid modes fail closed to `off`;
`ENABLED=true` is effective only with `MODE=shadow`.

As of Phase 2, the worker has one additive shadow hook immediately after
`TradeIntent.validate()` and before the Strategy 1 runtime call. That hook is
best-effort only: when disabled it is a no-op; when enabled it may write only to
`strategy2_*`; and any Strategy 2 exception degrades to warning + continue so
queue settlement and Strategy 1 stay unchanged.

## Lifecycle

```text
CANDIDATE → ARMED → PENDING → OPEN_RISK → BREAK_EVEN
                                      ↘         ↓
                              PROFIT_PROTECTED → CLOSED
```

`INVALIDATED`, `CANCELLED`, and `DATA_STALE` are terminal outcomes. Hard
invalidation and protective stops may close risk-bearing states and always take
precedence over a policy that waits for profit. A terminal state cannot reopen.
Illegal transitions raise a typed transition error before persistence changes.

## Decisions and reasons

Decision status and reason codes are enums, not classifications inferred from log
text. The taxonomy distinguishes data/integrity, entry evidence, execution cost,
risk/protection, and lifecycle outcomes. Human-readable `reason` and structured
evidence supplement the stable code but never replace it.

Shadow runtime adds explicit additive reasons for `ENTER_CANDIDATE`,
`SHADOW_SKIPPED`, `REPLAY`, and `NO_ENTRY`.

Identities include `strategy_version`, `experiment_id`, and an operation key.
Given the same immutable snapshot, configuration/version, and portfolio state,
the pure contracts and reducer produce the same identity and result without a
clock, network request, database read, or mutable global configuration.

## Virtual ledger invariants

Only `strategy2_*` tables are used:

- `strategy2_decisions` stores immutable decision attribution.
- `strategy2_state_events` is the lifecycle/accounting journal.
- `strategy2_portfolios` stores isolated virtual cash.
- `strategy2_positions` is the namespaced position projection.

Entry debits `price × quantity + fee` in the same transaction that records the
event and opens the projection. Close credits `price × quantity - fee` in the
same transaction. Replay of the same namespaced event is a no-op. NaN/Inf,
non-positive price/quantity, negative fee, fee above proceeds, insufficient cash,
illegal ownership/state, and oversell fail before commit.

The repository never reads or writes `users.balance`, `trades`, `pending_orders`,
or Strategy 1 `autotrade_*` tables. Strategy versions and experiment IDs do not
share cash or positions.

## Rollback and promotion boundary

Rollback is to leave `AUTOTRADE_STRATEGY2_ENABLED=false`/`MODE=off` and retain the
additive `strategy2_*` tables for audit. Schema creation is rerunnable; no legacy
table is migrated or deleted.

VM shadow activation, fill simulation, new capital or risk defaults, private API
access, active dry-run, deployment, and live trading still require explicit
approval beyond this additive seam. The current hook does not veto, modify, or
enrich Strategy 1 decisions. Promotion requires deterministic
replay, invariant/property tests, anti-lookahead checks, walk-forward evidence,
cost/fill stress, and separate shadow observation. Phase 1 makes no profitability
claim.
