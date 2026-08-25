# Technology Currentness & Brownfield Reality Review

**Artifact reviewed:** `ARCHITECTURE-SPINE.md` (draft, 2026-08-25)  
**Review date:** 2026-08-26  
**Lens:** every committed decision is supported by current primary-source research or by observable brownfield reality; named versions and technologies exist and fit the intended deployment.  
**Verdict:** **CHANGES REQUIRED** — the architectural direction is broadly well researched and appropriate, but the committed `uv` pin is already behind security fixes, the “Indodax v2” boundary is not precise enough to map to the venue's actual product contracts, and the runtime pin set is not yet a constructible/qualified brownfield deployment contract.

## Executive assessment

Most durable choices are credible: Python is the least-disruptive language for this codebase; a hexagonal modular monolith is a sensible strangler target; SQLite is technically suitable for a single-host/single-writer DRY RUN when its WAL constraints are enforced; Redis is correctly non-authoritative; and outbox, backup/restore, replay, reconciliation, and read-only projection rules are supported by primary documentation and by defects visible in the existing system.

The research companion is materially stronger than the spine's terse source list. It cites official Python, SQLite, Redis, Indodax, Telegram, AWS, Microsoft, OpenTelemetry, GitHub, NIST, and Google SRE sources. The code scan also correctly observes current drift: Docker uses Python 3.11, the local environment reports Python 3.12.3 with SQLite 3.45.1, dependencies are open lower bounds in `requirements.txt`, Redis uses an unpinned `redis:7-alpine` image and `allkeys-lru`, and legacy runtime code still contains direct database and live-order paths.

However, “exists” is not enough for a committed stack pin. The chosen toolchain must be safe, obtainable together in one artifact, and expressed in terms that match the vendor's actual API products.

## Findings

### HIGH — T-01: `uv 0.11.13` is a real release but is not a defensible current security pin

The Stack commits to `uv 0.11.13`. Astral's official 0.11.x changelog confirms that version was released on 2026-05-10, but also records security fixes in `0.11.15` for a TAR parser differential and an entry-point path escape. Later 0.11.x releases and the 0.12 line also exist. Thus the pin passes “technology exists” but fails “current and fit” for a new reproducible build substrate.

This matters because `uv` consumes and installs package archives during the supply-chain step that AD-19 is explicitly intended to harden. Pinning a version predating published security fixes contradicts the rule's purpose.

**Required disposition:** replace `0.11.13` with a currently qualified patched release (at minimum one containing the 0.11.15 security fixes), record the exact artifact/checksum or image digest, and add a recurring review trigger rather than treating a package-manager patch as timeless. If the project elects the 0.12 line, qualify its breaking changes first.

Primary evidence:

- Astral official changelog: <https://github.com/astral-sh/uv/blob/main/changelogs/0.11.x.md>
- Astral official releases: <https://github.com/astral-sh/uv/releases>
- Official lock/sync semantics (confirms `uv lock --check` and `uv sync --frozen` are valid): <https://docs.astral.sh/uv/concepts/projects/sync/>

### HIGH — T-02: “Only Indodax v2” does not identify the actual authoritative contracts

AD-13 says only “endpoint Indodax v2” that passes contract tests may be authoritative venue evidence. Indodax's official documentation does not expose one uniform product called “Indodax v2.” It distinguishes at least:

- Private REST API v2.0.1;
- INDODAX Trade API 2.0;
- Market Data WebSocket (separate, offset/recoverability semantics);
- Private WebSocket (separate token/channel and order-update contract);
- unversioned Public REST API.

The official Market Data WebSocket documentation supports offsets, recoverability, and sequence values for some payloads, so the sequence-aware recovery direction is credible. But describing all approved evidence as “v2 endpoints” can accidentally exclude the official market stream/public snapshot contract or cause an implementer to assume continuity semantics are uniform across channel types. The implementation note itself admits that cursor capability, continuity, depth, and recovery still require proof.

**Required disposition:** replace the umbrella label with an explicit capability registry: product/document, base URL, endpoint/channel, contract version or documentation commit, cursor/offset semantics, snapshot source, authoritative fields, and recovery rule. Keep contract tests as the admission gate. Until that matrix is proven, venue continuity should remain an assumption/open question rather than a blanket committed capability.

Primary evidence:

- Official API catalog: <https://github.com/btcid/indodax-official-api-docs>
- Official Market Data WebSocket contract: <https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md>
- Official Private WebSocket contract: <https://github.com/btcid/indodax-official-api-docs/blob/master/Private-websocket.md>
- Official Trade API 2.0 contract: <https://github.com/btcid/indodax-official-api-docs/blob/master/INDODAX-TradeAPI-2.md>

### HIGH — T-03: the three exact runtime pins are individually real, but the spine does not yet define a constructible combined artifact

CPython 3.12.14 exists and was released on 2026-08-12. SQLite 3.53.4 exists and its exact source ID in AD-19 matches SQLite's official release history. The compatibility choice is plausible: keeping Python 3.12 reduces migration risk for this brownfield codebase, although Python now calls 3.12 a legacy/security-only series and 3.14 is the current feature line.

The brownfield deployment does not currently satisfy any of these pins:

- both Dockerfiles use floating `python:3.11-slim`;
- dependencies are installed with `pip` from lower-bound-only `requirements.txt`;
- no `pyproject.toml` or `uv.lock` exists in the repository;
- the inspected local runtime is Python 3.12.3 linked to SQLite 3.45.1;
- no image definition shows how CPython 3.12.14 is linked to the exact SQLite 3.53.4 source ID.

This is more than ordinary implementation work because CPython's `sqlite3` module uses the SQLite library embedded/linked by the built interpreter or distribution. Selecting a CPython tag does not by itself guarantee the SQLite source ID. Python 3.12 has also moved to security-only source releases; Python.org notes 3.12.10 was the last 3.12 release with binary installers. A Linux container can still build/use 3.12.14, but the spine needs an explicit, testable acquisition route.

**Required disposition:** define the qualified base artifact or build recipe that produces all three pins together; pin its digest; verify `sys.version`, `sqlite3.sqlite_version`, `sqlite_source_id()` via SQL, compile options, and effective PRAGMAs in CI; create and commit `pyproject.toml` plus `uv.lock`; and demonstrate dependency compatibility on 3.12.14. Treat the current Docker/runtime as migration input, not evidence that AD-19 is already realizable.

Primary evidence:

- Python 3.12.14 official files: <https://www.python.org/ftp/python/3.12.14/>
- Python maintained version list: <https://www.python.org/doc/versions/>
- SQLite official release history/source ID: <https://sqlite.org/changes.html>
- SQLite WAL guidance: <https://www.sqlite.org/wal.html>

Brownfield evidence: `Dockerfile`, `Dockerfile.worker`, `requirements.txt`, and `docker-compose.yml` in the repository; runtime probe performed during this review.

### MEDIUM — T-04: provenance is broad but not auditable per committed AD

The spine frontmatter names only the PRD and one technical research document. The memlog says a brownfield scan and migration research are load-bearing inputs, but does not map each AD to its source/evidence. Several commitments are derived architecture judgments rather than claims a web page can prove—examples include the exact RiskGovernor envelope, writer fencing protocol, authority cutover rules, operational thresholds, and portfolio allocation cycle. Many numerical baselines are correctly marked `[ASSUMPTION]`, but a reader cannot consistently distinguish researched fact, adopted product decision, inferred brownfield constraint, and unvalidated design hypothesis for every AD.

This does not make those decisions wrong. It makes the requested assertion (“every committed decision was researched or reality-checked”) non-reproducible from the artifact package.

**Required disposition:** add a compact decision-evidence register in the companion/memlog (not necessarily in the terse spine): `AD ID → evidence type → primary source or code paths/probe → checked date → confidence → revalidation trigger`. Explicitly label organization-selected risk limits as policy choices, not externally validated universal values.

### MEDIUM — T-05: brownfield fit is a credible target, not current reality; the cutover prerequisites need an executable inventory

The strangler namespace and no-dual-settlement rules appropriately acknowledge the brownfield system, and the implementation notes explicitly classify current Docker/unlocked dependencies and legacy tables as things to replace or migrate. That is good reality-checking.

Still, the current repository has a monolithic `bot.py`, direct Indodax live-order calls, many direct SQLite access paths, a Redis cache/queue setup sharing one evictable instance, and DRY RUN selected by mutable configuration in a process that also contains live execution methods. Therefore AD-01, AD-05/06, AD-16, and especially AD-20 are future-state invariants—not ratified conventions already present in code.

**Required disposition:** before implementation stories are declared ready, produce a mechanically generated writer/submitter/process inventory and map every legacy mutation path to `remove`, `adapter`, `projection`, or `migration-only`. Add a negative artifact test proving the DRY RUN image cannot import or reach a live submission adapter and does not receive trade-capable credentials. The existing tests and code scan are useful seeds but do not yet prove physical exclusion.

Brownfield evidence includes `bot.py`, `api/indodax_api.py`, `core/database.py`, `cache/redis_task_queue.py`, `cache/redis_state_manager.py`, and `docker-compose.yml`.

## Verification matrix

| Area / decisions | Currentness and existence | Fit / reality check | Result |
| --- | --- | --- | --- |
| AD-01 modular monolith / hexagonal boundary | Established pattern; official AWS guidance cited in research | Appropriate for Python monolith and safer than premature services | Pass |
| AD-02 Decimal/fixed-point and UTC | Python standard capability; avoids observed float/time drift classes | Exact serialization/scale remains an implementation contract | Pass with implementation proof |
| AD-03–AD-12 canonical decision, Fill authority, outbox, fencing, risk, order lifecycle | Patterns are coherent; outbox has primary-source support | Strong response to multiple current writers/tables, but mostly future-state | Pass as target; inventory required |
| AD-13 Indodax recovery | Official APIs/streams exist; offsets/sequences exist in documented contexts | “v2” is not a sufficiently precise capability boundary | Change required |
| AD-14–AD-15 replay/evidence governance | Technology-neutral and supported by cited research methods | Fits research-heavy bot; exact tool/library intentionally deferred | Pass |
| AD-16 Redis non-authoritative / SQLite canonical | SQLite and Redis capabilities documented | Current single evictable Redis instance violates future transport isolation, which notes acknowledge | Pass as migration target |
| AD-17–AD-18 read surfaces / cutover | Technology-neutral operational decisions | Appropriate, but full mutator inventory not yet attached | Pass with prerequisite |
| AD-19 runtime reproducibility | CPython 3.12.14 and SQLite 3.53.4/source ID verified; uv 0.11.13 exists | uv pin predates security fixes; combined runtime build path absent | Change required |
| AD-20 physical DRY RUN isolation | Feasible deployment pattern | Current image/process includes live submission authority | Pass only as unimplemented release gate |
| AD-21–AD-23 SLO, backup, migration | SQLite backup/PRAGMA/migration mechanisms exist | Operational thresholds are assumptions and drills are not yet evidenced | Pass as gated assumptions |
| AD-24–AD-25 allocation/calibration facts | Technology-neutral domain design | Coherent, but evidence is conceptual rather than current code | Pass as target |
| Stack: CPython 3.12.14 | Exists; security-only legacy line | Reasonable conservative brownfield choice; source/build qualification required | Conditional pass |
| Stack: SQLite 3.53.4 | Exists; exact source ID correct | Good response to current 3.45.1 risk; must prove linked runtime | Conditional pass |
| Stack: uv 0.11.13 | Exists | Published security fixes arrived in 0.11.15; not acceptable as new pin | Fail |

## What was successfully verified

- SQLite `3.53.4` and the exact `SQLITE_SOURCE_ID` written in AD-19 match SQLite's official release history.
- CPython `3.12.14` exists and is the latest security release in the 3.12 series as of the review date.
- `uv 0.11.13` exists, and the named `uv lock --check` / `uv sync --frozen` workflow is supported by official documentation.
- SQLite WAL's one-writer model, local-filesystem caveat, checkpoint concerns, Online Backup API, integrity checks, and configurable durability are real and fit the proposed single-host design when verified at runtime.
- Redis Streams/persistence limitations support treating Redis as transport/cache rather than canonical accounting authority.
- Indodax official market/private streams and Trade API products exist, but their contracts must be enumerated rather than collapsed into one “v2” label.
- Brownfield claims in the research are accurate in the inspected repository: runtime drift, unlocked dependencies, Redis eviction exposure, direct DB mutation, and mixed dry/live execution authority are observable.

## Gate recommendation

Do not finalize the spine until T-01 through T-03 are resolved. T-04 and T-05 may be handled in the implementation companion if they become explicit readiness gates with owners and artifacts. No change was made to `ARCHITECTURE-SPINE.md` by this review.

## Delta Verification — 2026-08-26

**Delta verdict: PASS — T-01 through T-05 are closed at architecture-document level. No remaining technology-currentness blocker.** Implementation evidence is still intentionally outstanding and is now expressed as a fail-closed readiness/release gate rather than implied current conformance.

| Prior finding | Verification of updated deliverables | Status |
| --- | --- | --- |
| T-01 — unsafe/outdated `uv 0.11.13` pin | Stack now pins `uv 0.11.15`, the minimum same-line release containing the cited security fixes. AD-19 additionally requires a pinned tool artifact/checksum, while the Decision Evidence Register triggers revalidation on tool/runtime security releases. This satisfies the prior disposition without forcing an unqualified 0.12 migration. | **Closed** |
| T-02 — ambiguous “Indodax v2” contract | New AD-29 requires separate effective-time registry entries for Public REST, Private REST API, Trade API 2.0, Market Data WebSocket, and Private WebSocket, including documentation commit/version, endpoint/channel, authoritative fields, cursor semantics, snapshot/recovery route, and contract-test artifact. Unproven capability is explicitly `UNQUALIFIED` and fail-closed. Implementation Notes require the per-product registry, contract tests, and gap/recovery corpus. | **Closed** |
| T-03 — exact pins not tied to a constructible qualified artifact | AD-19 now requires a qualified build recipe that produces CPython 3.12.14 linked to SQLite 3.53.4, pins base image/tool artifacts by digest/checksum, commits `pyproject.toml`/`uv.lock`, and verifies Python version, SQLite version/source ID/compile options, effective PRAGMAs, and dependency compatibility in CI. The artifact does not yet exist, but the architecture no longer claims brownfield conformance: build and qualification proof are explicit gates. | **Closed at architecture level; implementation gate remains** |
| T-04 — no auditable per-AD provenance | Implementation Notes now contain a Decision Evidence Register mapping all AD ranges to evidence type, authority/reality check, and revalidation trigger. Product-policy and research hypotheses are distinguished from official technical evidence and brownfield defects; numerical baselines remain visibly `[ASSUMPTION]`. | **Closed** |
| T-05 — target state not backed by executable brownfield inventory | Implementation Notes now require a complete writer, order-submitter, credential, process, and canonical-file inventory before implementation readiness, with every path classified `remove`, `adapter`, `projection`, or `migration-only`. Evidence gates include legacy-writer absence proof and a security assertion that the DRY RUN artifact has no live adapter, trade-capable credential, or live dependency. | **Closed** |

### Non-blocking implementation cautions

- The CI check written as `sqlite_source_id()` should be implemented using the SQLite runtime query (for example `SELECT sqlite_source_id()`), because Python's standard `sqlite3` module does not expose a same-named top-level function consistently.
- `uv 0.11.15` is acceptable for closure because it includes the identified fixes and the document now mandates security-release revalidation. It must still be requalified if a newer advisory affects it before artifact build/release.
- Passing this delta review does not certify the future image, lockfile, Indodax channel behavior, or legacy-path removal. Those proofs are correctly deferred to the newly explicit readiness/release artifacts.

No architecture deliverable was edited by this delta review; only this review record was updated.
