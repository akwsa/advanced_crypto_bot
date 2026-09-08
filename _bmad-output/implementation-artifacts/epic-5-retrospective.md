# Retrospective Epic 5 — Legacy Authority Cutover

Tanggal: 2026-09-08
Status: selesai

## Epic Review

Epic 5 menyelesaikan enam story dan memindahkan desain replacement dari inventaris legacy menuju cutover yang fenced, dapat dipulihkan, dan mempertahankan history:

- `5.1`: seluruh legacy authority dan fakta diklasifikasikan; ambiguity menjadi blocker, bukan asumsi.
- `5.2`: runtime artifact dikualifikasi dengan manifest immutable dan verifikasi fail-closed.
- `5.3`: migration offline serta backup/restore gate dipisahkan dari runtime DDL.
- `5.4`: proven execution diimpor sebagai `ApprovedExternalFact`; ambiguity tetap dikarantina.
- `5.5`: cutover mengikuti urutan freeze, stop, drain, checkpoint, epoch claim, lalu enable target.
- `5.6`: rollback bersifat additive dan retention menghasilkan evidence tombstone yang teraudit.

### What Worked

- Append-only canonical facts dan single-writer fencing memberi invariant yang konsisten dari migration hingga rollback.
- Contract tests menjadi executable specification untuk identity, authority, replay, accounting, recovery, dan cutover.
- Full regression di luar sandbox menangkap regression legacy yang tidak terlihat pada suite domain saja.
- Review adversarial menemukan celah invariant yang masih tersisa pada Story 3.4; auto-fix kemudian ditutup dengan contract tests.

### Challenges and Lessons

- Fixture berbasis wall-clock dan test order membuat regression tidak deterministik; waktu harus dibekukan saat fixture dibuat atau dibandingkan secara eksplisit.
- Managed sandbox memiliki perilaku timeout pada sebagian TestClient/suite panjang; gate environment perlu dibedakan dari failure aplikasi dan diverifikasi ulang di luar sandbox.
- Status story, sprint tracker, orchestration state, dan commit harus disinkronkan sebagai satu transition; state yang stale memperbesar risiko resume yang salah.
- Boundary Telegram/HTML harus disanitasi sebelum pengiriman pertama, bukan hanya pada fallback error path.

## Next Epic Preparation

- Pertahankan DRY RUN sebagai satu-satunya execution authority MVP; live trading tetap memerlukan PRD dan approval terpisah.
- Jadikan full regression luar sandbox sebagai release evidence yang disimpan bersama commit.
- Tambahkan pemeriksaan CI untuk fixture time-order, clean-store replay, backup restore, dan marker/state consistency.
- Untuk setiap recovery, rekonsiliasi `sprint-status.yaml`, story file, orchestration state, dan git status sebelum spawn agent baru.

## Action Items

| Owner | Action | Priority |
|---|---|---|
| Officer | Review live-readiness proposal terpisah sebelum any real-money authority change. | High |
| Developer | Automate detection of stale orchestration/story/sprint state before resume. | Medium |
| Developer | Preserve outside-sandbox full-regression output as durable CI artifact. | Medium |
| QA | Add deterministic clock/order-isolation checks for legacy regression fixtures. | Medium |

## Outcome

Epic 5 memenuhi acceptance criteria seluruh enam story. Platform remains DRY RUN-only and no live trading activation is implied by this retrospective.
