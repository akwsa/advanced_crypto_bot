# BMAD / AI Team Playbook — Advanced Crypto Bot

**Dibuat:** 2026-05-20  
**Path proyek:** `/home/officer/advanced_crypto_bot/advanced_crypto_bot`  
**Mode aman saat ini:** DRY RUN; jangan aktifkan real trading sebelum checklist release terpenuhi.

---

## 1. Tujuan Dokumen

Dokumen ini adalah template kerja untuk Cursor/Hermes/Pi Agent/BMAD-style multi-agent workflow agar pengembangan bot tidak acak. Fokusnya:

1. Memahami arsitektur bot dengan cepat.
2. Membagi pekerjaan ke agen yang tepat.
3. Menentukan skill Hermes yang perlu diload.
4. Menentukan API/model AI yang optimal untuk tiap jenis pekerjaan.
5. Menjaga safety trading: tes, dry-run, audit risiko, dan rollback.

---

## 2. Ringkasan Arsitektur Aktual

Entry point utama: `bot.py` (`AdvancedCryptoBot`) — orchestrator Telegram, runtime loop, command handlers, ML model initialization, worker startup.

Modul utama:

| Area | File/Folder | Peran |
|---|---|---|
| Core config & DB | `core/config.py`, `core/database.py` | Env, risk constants, SQLite/WAL, trade state |
| Signal pipeline | `signals/signal_pipeline.py`, `signals/signal_quality_engine.py`, `signals/signal_rules.py` | TA + ML + quant + final gate |
| Trading engine | `autotrade/trading_engine.py`, `autotrade/runtime.py`, `autotrade/risk_manager.py` | Trade eligibility, sizing, SL/TP, runtime sell/buy |
| ML | `analysis/ml_model*.py`, `analysis/ml_signal_trainer.py` | V1-V4 prediction, signal outcome training |
| Quant | `quant/*.py` | Mean reversion, Kelly, momentum, correlation, stat arb, VaR/CVaR, GARCH, ARIMA, frontier |
| Hunters/scalper | `autohunter/*`, `scalper/scalper_module.py` | Smart/Ultra Hunter and scalper flows |
| API/workers/cache | `api/`, `workers/`, `cache/` | Indodax, polling/background jobs, Redis/in-memory state |
| Tests | `tests/` + `deprecated.archived/tests` | Regression and behavior checks |

Observed size baseline:

- `bot.py`: ~9,704 LOC
- `signals/signal_pipeline.py`: `generate_signal_for_pair()` ~831 LOC
- `scalper/scalper_module.py`: ~4,327 LOC
- Full suite currently: `238 passed, 25 warnings` using `/home/officer/.hermes/bin/python -m pytest -q`.

---

## 3. Recommended AI Agents / Roles

Gunakan pembagian ini untuk pekerjaan besar. Jangan satu agen mengerjakan semuanya sekaligus.

### A. Orchestrator / BMAD PM

**Tugas:** pecah pekerjaan, jaga prioritas, buat checklist, pastikan tidak ada perubahan real-trading tanpa approval.

**Hermes skills:**
- `bmad-sprint-planning`
- `bmad-create-story`
- `bmad-check-implementation-readiness`
- `writing-plans`
- `subagent-driven-development`

**Model/API optimal:** GPT-5.5/freemodel aktif cukup untuk koordinasi; kalau desain besar dan banyak konteks, gunakan model reasoning besar via OpenRouter/Claude/Gemini Pro.

### B. Codebase Architect / Refactor Planner

**Tugas:** memahami dependency, membuat peta pemecahan `bot.py`, `signal_pipeline.py`, dan `scalper_module.py` tanpa merusak runtime.

**Hermes skills:**
- `codebase-inspection`
- `bmad-agent-architect`
- `bmad-document-project`
- `writing-plans`

**Model/API optimal:** Claude Sonnet/Opus atau GPT-5.5 untuk refactor besar; Gemini Pro bagus untuk membaca konteks panjang dan menyusun peta modul.

### C. Quant / ML Research Agent

**Tugas:** retrain V2/V4, cek SELL/BUY bias, validasi ARIMA/GARCH/VaR, backtesting, feature leakage, class imbalance.

**Hermes skills:**
- `jupyter-live-kernel`
- `pandas-performance`
- `systematic-debugging`
- `spike`

**Model/API optimal:** Gemini Pro atau Claude/GPT model kuat untuk reasoning statistik; eksekusi tetap lokal dengan Python, bukan mengirim data sensitif ke AI kalau data trade pribadi berisi rahasia.

### D. QA / Test Engineer

**Tugas:** menjaga regression suite, menambah test behavior bukan snapshot, dry-run safety, property tests untuk risk gates.

**Hermes skills:**
- `test-driven-development`
- `systematic-debugging`
- `requesting-code-review`

**Model/API optimal:** model coding kuat; API tidak perlu paling mahal kecuali debugging rumit.

### E. Security / Safety Auditor

**Tugas:** audit API key handling, dry-run enforcement, private API call guards, command rate limiting, secret redaction, backup/rollback.

**Hermes skills:**
- `systematic-debugging`
- `requesting-code-review`
- `github-code-review` jika via PR

**Model/API optimal:** Claude/GPT reasoning kuat untuk review; jangan kirim secret. Semua secret harus direpresentasikan sebagai `[REDACTED]`.

### F. Ops / Runtime Monitor

**Tugas:** restart bot, cek tmux/systemd/logs, validasi DB/WAL, pantau distribusi sinyal 3-5 hari.

**Hermes skills:**
- `systematic-debugging`
- `python-threading-debug`
- `blogwatcher`/cron skill bila ingin laporan periodik

**Model/API optimal:** tidak perlu mahal; yang penting tool execution stabil.

---

## 4. Skill Hermes yang Disarankan per Task

| Task | Skill wajib/utama |
|---|---|
| Inspeksi repo & LOC | `codebase-inspection` |
| Menulis plan implementasi | `writing-plans`, `bmad-create-story` |
| Debug bug runtime | `systematic-debugging`, `python-threading-debug` |
| TDD bugfix | `test-driven-development` |
| Refactor bot.py | `bmad-agent-architect`, `writing-plans`, `subagent-driven-development` |
| Review sebelum merge | `requesting-code-review` |
| Analisis ML/data | `jupyter-live-kernel`, `pandas-performance` |
| Dokumentasi brownfield | `bmad-document-project` |
| Sprint/roadmap | `bmad-sprint-planning`, `bmad-sprint-status` |

---

## 5. Rekomendasi API Key / Model AI

### Jangan jadikan Gemini default otomatis

Konfigurasi Hermes saat ini tetap `freemodel` + `gpt-5.5`. Itu aman sebagai default harian.

### Gunakan Gemini Pro untuk pekerjaan tertentu

Gemini Pro cocok untuk:

1. Membaca dokumentasi panjang dan merangkum arsitektur.
2. Membandingkan banyak file sekaligus.
3. Ide riset quant/ML dan brainstorming parameter.

Namun untuk coding kritikal trading, sebaiknya gunakan kombinasi:

| Kebutuhan | Rekomendasi model/API |
|---|---|
| Coding/refactor kritikal | Claude Sonnet/Opus atau GPT-5.5 coding-capable |
| Konteks panjang/dokumen banyak | Gemini Pro |
| Review adversarial | Dua model berbeda: Claude + GPT/Gemini |
| Eksekusi/test | Lokal Python/pytest, bukan AI |
| Tugas rutin murah | `freemodel` default saat ini |

Rule praktis: **Gemini sebagai second opinion / long-context reviewer**, bukan default tunggal untuk operasi bot.

---

## 6. Development Safety Rules

1. **Default DRY RUN.** Jangan aktifkan real trading sampai test, monitoring, dan approval lengkap.
2. **Jangan ubah `MAX_DRAWDOWN_PCT` dari `0.10` ke `10.0`.** Kode memakai fraksi; `0.10` = 10%.
3. **Jangan refactor `bot.py` besar-besaran sekaligus.** Buat adapter/extract kecil, test dulu.
4. **Jangan kirim API key ke chat/log.** Gunakan `.env`, permission ketat, dan redaksi `[REDACTED]`.
5. **Semua perubahan trading harus punya regression test.** Minimal dry-run safety + risk gate test.
6. **Gunakan Python environment yang punya dependency lengkap:** `/home/officer/.hermes/bin/python` terbukti menjalankan full tests.
7. **Setelah perubahan runtime, restart bot dan cek logs.**

---

## 7. Known Weaknesses / Risk Register

| Risiko | Dampak | Rekomendasi |
|---|---|---|
| `bot.py` terlalu besar (~9.7k LOC) | Sulit review, high regression risk | Extract command handlers bertahap, bukan rewrite |
| `generate_signal_for_pair()` sangat panjang (~831 LOC) | Signal logic sulit diuji granular | Pecah menjadi price fetch, ML predict, quant enrich, gates, persist |
| `scalper_module.py` besar (~4.3k LOC) | UI/trading/state tercampur | Pisah service trading, formatter, command handlers |
| Full tests pakai Python Hermes, venv lokal tidak punya pytest | Developer bisa salah env | Standarkan runner script lokal |
| 25 warnings pytest | Bisa menyembunyikan masalah baru | Bersihkan test yang `return bool`, handle precision warning |
| ML SELL/BUY imbalance historis | Sinyal bias, opportunity miss | Retrain dengan sample_weight/class balance dan monitoring distribusi |
| Correlation groups statis | Over/under-block exposure | Gunakan `dynamic_correlation.py` lebih aktif untuk portfolio heat |
| WebSocket tidak aktif/stabil | Price latency REST polling | Implement reconnect/backoff dan fallback observability |
| Banyak thread/background task | Race condition dan lifecycle risk | Audit dengan `python-threading-debug`; central shutdown manager |
| Indodax/Telegram rate limiting belum kuat | Security & abuse risk | Tambah per-user rate limit dan command cooldown |
| Model files pickle/joblib | Supply-chain risk jika file tidak trusted | Jangan load model dari sumber tidak dipercaya; checksum model |

---

## 8. Sprint Template

### Sprint Goal

Contoh: “Stabilkan signal quality dan retrain ML tanpa mengubah real-trading mode.”

### Story Template

```md
## Story: <judul>

### Context
- File terkait:
- Modul terkait:
- Risiko trading:

### Acceptance Criteria
- [ ] Perubahan berjalan di DRY RUN
- [ ] Tidak ada real private API call di test
- [ ] Unit/regression test ditambah
- [ ] Full/target pytest pass
- [ ] Dokumen/changelog diperbarui jika behavior berubah

### Test Plan
- Command:
- Expected result:

### Rollback Plan
- File backup/commit:
- Cara revert:
```

---

## 9. Cursor / Agent Prompt Template

Gunakan prompt ini saat meminta Cursor/AI mengerjakan bugfix:

```text
Kamu bekerja di /home/officer/advanced_crypto_bot/advanced_crypto_bot.
Bot adalah crypto trading bot Indodax + Telegram. Default harus tetap DRY RUN.
Jangan tampilkan atau ubah secret/API key. Jangan aktifkan real trading.

Wajib baca dulu:
- BMAD_AI_TEAM_PLAYBOOK.md
- INDEX.md
- BUG_REPORT_CRITICAL.md
- CATATAN_CHAT_2026-05-20.md
- SYSTEM_MAP.md
- file modul yang akan diubah

Tugas:
<jelaskan tugas kecil dan spesifik>

Aturan:
1. Buat perubahan minimal.
2. Tambah/ubah test behavior, bukan snapshot data.
3. Jalankan test dengan /home/officer/.hermes/bin/python -m pytest <target>.
4. Laporkan file berubah, hasil test, risiko, dan rollback.
```

---

## 10. Prioritas Berikutnya

1. Buat runner test standar (`scripts/test.sh`) yang memakai env benar.
2. Retrain ML V2/V4 dengan data seimbang dan laporkan distribusi BUY/SELL/HOLD.
3. Pecah `signals/signal_pipeline.py` menjadi fungsi kecil yang bisa dites.
4. Tambah rate limiter Telegram command.
5. Audit thread/background task dan duplicate notification guard.
6. Rancang WebSocket reconnect/backoff, jangan aktifkan tanpa monitoring.
