# Reality-Check Review — Architecture Spine

## Verdict

**CHANGES REQUIRED.** The spine is directionally sound as a target architecture,
and its WSL stack versions are reproducible in the project virtual environment.
However, several rules are written as committed system invariants even though the
current champion runtime contradicts them. The document needs an explicit
current-state/target-state boundary and migration gates; otherwise the roadmap can
mistake desired properties for foundations that already exist.

## Findings

### 1. Critical — AD-1 and the “event-sourced” paradigm are not implemented for the champion

`autotrade/contracts.py::TradeIntent` carries `version`, `correlation_id`, and
`idempotency_key`, but has no first-class `snapshot_id`, `strategy_version`,
`configuration_hash`, `experiment_id`, or ingestion time. Its fallback
`created_at` reads the wall clock, and `_canonical(..., default=str)` does not make
arbitrary signal payloads a rigorously replayable market snapshot. The Strategy 1
tables in `core/database.py` likewise do not persist those fields; only the
isolated Strategy 2 tables have some of them. There is no canonical immutable
market-snapshot journal visible in the current tree.

Consequently, identical policy replay and champion/challenger evaluation against
the same snapshot/configuration cannot currently be demonstrated. Calling the
platform “event-sourced” overstates reality: fills are append-only-ish accounting
events, but decisions and market inputs do not yet form a complete replay source.

**Required correction:** label this explicitly as the target paradigm. Make
snapshot persistence plus a v2 intent identity migration the first enabling
milestone, and define a replay acceptance test before claiming AD-1 is enforced.
Also specify whether configuration and strategy artifacts are stored by value or
by immutable content-addressed reference.

### 2. Critical — AD-2/AD-8 conflict with active legacy-driven portfolio and runtime paths

The normalized fill journal and virtual-cash updates do exist, and
`record_dryrun_fill`/sell paths use transactions. But the present application is
not governed exclusively by them. `autotrade/portfolio.py` calculates portfolio
state from `db.get_open_trades()` and legacy trade fields. The champion execution
code also contains many legacy trade and pending-order paths, while the schema
comment itself describes `trades` as a compatibility projection rather than
preventing reads. Prior audit documentation records real divergence between
legacy pending orders and normalized orders, confirming this is not theoretical.

In addition, money and quantities in the canonical-looking SQLite tables are
declared as `REAL`, while the spine mandates decimal/quantized IDR and no
binary-float equality. Current code eagerly converts amounts to `float`. Thus the
stated money convention is also target-state, not a verified invariant.

**Required correction:** add a consumer-by-consumer cutover inventory and a hard
gate that no risk, equity, sizing, exit, dashboard, or reconciliation query reads
legacy state before declaring AD-2 complete. Decide and document the persistence
representation for money (for example integer IDR plus integer base-asset units,
or decimal text), including migration and invariant tests. Do not call the current
normalized journal the “sole accounting authority” until that cutover passes.

### 3. High — AD-3 and AD-6 describe abstractions that do not yet exist

The champion policy is not presently a pure strategy boundary. The large
`autotrade/runtime.py` orchestration performs network ticker calls, reads mutable
`Config`, consults database-backed bot state, applies policy gates, and executes
fills in the same runtime surface. Strategy 2's current `shadow_runtime.py` is an
observation adapter: a BUY is labelled `ENTER_CANDIDATE` based on the champion
recommendation, not an independent patient-swing policy evaluated from a canonical
snapshot.

Execution realism is also partial and fragmented. Current dry-run paths generally
use a fixed configured slippage percentage, a configured fee rate, and current
bid/ask or last price. The code has pending expiry and partial exit lifecycle
features, but no single versioned simulator demonstrably applying size-aware
depth, latency, partial entry fills, precision rules, and identical assumptions to
every strategy. The blanket “Indodax fees” wording is unsupported without a
versioned fee schedule/source and maker/taker/order-type semantics.

**Required correction:** treat extraction of a pure champion adapter and a shared
`ExecutionModel` contract as migrations, not directory moves. Define the minimum
snapshot schema, simulator inputs, deterministic clock/randomness, depth fallback,
fee schedule provenance/effective date, and golden parity tests. Until Strategy 2
emits independent intents and owns the full lifecycle, describe it as scaffolding,
not an operational challenger.

### 4. High — AD-9's VM single-writer guarantee is operational intent, not enforced architecture

The current worker lock uses `fcntl.flock` on a local `/tmp` file. It prevents a
second worker on one host only; it cannot fence WSL and the Google VM from sharing
Redis, SQLite copies, Telegram credentials, or experiment namespaces. The checked
in `crypto-bot.service` contains no distributed lease, unique runtime role,
credential isolation, or experiment namespace configuration. The previously
observed Telegram `getUpdates` conflict is direct evidence that cross-host
single-writer ownership was not guaranteed.

**Required correction:** choose one enforceable mechanism: deployment-level
credential separation and WSL-safe defaults, or a renewable distributed lease
with fencing tokens around all writes. Add startup refusal when role/namespace is
ambiguous and an acceptance test that a second host/process cannot poll Telegram
or mutate the canonical experiment. A local flock can remain defense in depth but
does not satisfy AD-9.

### 5. Medium — Stack versions are verified locally but dependency reproducibility is unsupported

The exact table values are correct when checked with `venv/bin/python` in WSL on
2026-08-24: Python 3.12.3, SQLite 3.45.1, pandas 3.0.2, redis-py 7.4.0,
python-telegram-bot 22.7, and scikit-learn 1.8.0. They are not guaranteed by
`requirements.txt`, which uses broad lower bounds (`pandas>=2.0.0`,
`redis>=5.0.0`, etc.). The system interpreter already resolves a different pandas
and Telegram version and lacks some dependencies, illustrating why invocation
context matters. No evidence in the spine verifies the corresponding Google VM
versions. “Redis client” should be named `redis-py`; Redis server compatibility is
not specified.

**Required correction:** rename the column to “observed in WSL project venv on
2026-08-24,” record the command/evidence, and do not imply VM parity. Add a lock or
constraints artifact and CI/VM verification before versions become architecture
commitments. Pin only versions actually required by tested behavior; otherwise
state supported ranges and include SQLite runtime capability checks.

## Positive reality checks

- Normalized Strategy 1 intent/order/fill/position tables and atomic virtual-cash
  fill paths are present, so AD-2 has a real migration substrate.
- Strategy 2 has a genuinely separate namespace, repository, portfolio and state
  tables, supporting the isolation direction in AD-10 even though the independent
  policy/lifecycle is incomplete.
- The circuit-breaker principle in AD-8 matches the documented accounting repair
  objective: canonical cash plus mark-to-market positions, with protection exits
  separated from new-risk blocking. It still needs consumer cutover verification.
- SQLite remains a technically reasonable choice for one local writer at this
  scale, provided the single-writer constraint becomes enforceable and contention
  is measured as the spine proposes.

## Review scope

Evidence was checked against `autotrade/contracts.py`, `autotrade/runtime.py`,
`autotrade/portfolio.py`, `autotrade/strategy2/shadow_runtime.py`,
`autotrade/strategy2/repository.py`, `core/database.py`, `core/config.py`,
`bot.py`, `crypto-bot.service`, `requirements.txt`, and the cited audit/handoff
documents. Live Google VM state was not accessible as part of this review, so no
current VM package or service assertion is treated as verified.
