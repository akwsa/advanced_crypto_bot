# Phase 1 Deploy & Runbook — Read-only Dashboard

> Status: safe runbook untuk development/local deployment. Tidak menjalankan real deploy otomatis dan tidak mengubah mode trading.

---

## 1. Guardrails Operasional

Sebelum menjalankan dashboard:

- Pastikan branch kerja: `dashboard-phase1-readonly`.
- Pastikan backup DB sudah ada:
  - `data/trading.db.backup-*`
  - `data/signals.db.backup-*`
- Dashboard API hanya read-only.
- Jangan expose dashboard ke internet tanpa auth/Nginx protection.
- Jangan menaruh Telegram/Indodax/API key di frontend.
- Jangan membuat endpoint POST/PUT/PATCH/DELETE untuk Phase 1.

---

## 2. Local Backend Run

Dari root project:

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
scripts/test.sh -q tests/test_dashboard_api_phase1.py tests/test_dashboard_api_readonly_phase1_endpoints.py tests/test_dashboard_frontend_static.py
uvicorn dashboard_api.main:app --host 127.0.0.1 --port 8000
```

Buka:

```text
http://127.0.0.1:8000/
```

API docs:

```text
http://127.0.0.1:8000/docs
```

---

## 3. Smoke Test Manual

Jalankan dari terminal lain:

```bash
curl -s http://127.0.0.1:8000/api/v1/health
curl -s http://127.0.0.1:8000/api/v1/safety/status
curl -s http://127.0.0.1:8000/api/v1/system/data-sources
curl -s http://127.0.0.1:8000/api/v1/pairs/active
curl -s http://127.0.0.1:8000/api/v1/positions/open
curl -s http://127.0.0.1:8000/api/v1/signals/latest?limit=5
curl -s http://127.0.0.1:8000/api/v1/trades/history?limit=5
curl -N http://127.0.0.1:8000/api/v1/events/stream?once=true
```

Expected:

- semua HTTP 200,
- response wrapper `{success, data, meta}` untuk REST,
- safety status menampilkan `real_trading_locked: true` saat DRY RUN,
- SSE mengirim `event: heartbeat`,
- tidak ada write action.

---

## 4. Nginx Reverse Proxy Draft

Gunakan hanya setelah auth/deployment target diputuskan.

```nginx
server {
    listen 8080;
    server_name localhost;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/v1/events/stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 24h;
    }
}
```

Jika dashboard akan dibuka dari luar mesin lokal, tambahkan minimal salah satu:

- VPN/Tailscale/private network only,
- Nginx Basic Auth,
- Cloudflare Access,
- backend auth session.

---

## 5. PM2 Draft

```bash
pm2 start "uvicorn dashboard_api.main:app --host 127.0.0.1 --port 8000" --name dashboard-api
pm2 logs dashboard-api
pm2 status
```

Stop:

```bash
pm2 stop dashboard-api
```

---

## 6. Final Safety Checklist

- [ ] `scripts/test.sh -q tests/test_dashboard_api_phase1.py tests/test_dashboard_api_readonly_phase1_endpoints.py tests/test_dashboard_frontend_static.py tests/test_dashboard_heartbeat.py` pass.
- [ ] `/openapi.json` hanya punya GET untuk `/api/v1/*`.
- [ ] Folder `dashboard_api/` dan `dashboard_frontend/` tidak import `bot.py`.
- [ ] `bot.py` tetap berjalan normal tanpa dashboard.
- [ ] Frontend menampilkan `DRY RUN LOCKED`.
- [ ] Frontend tidak punya tombol execute trade / hunter toggle / SLTP write.
- [ ] Secrets tidak muncul di frontend source.
