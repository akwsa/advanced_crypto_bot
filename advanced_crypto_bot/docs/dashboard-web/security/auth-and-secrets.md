# Auth & Secrets Plan

## Core Rule

Admin secrets must never be embedded in frontend build output.

Do not do this:

```ts
headers: {
  'X-API-Key': import.meta.env.VITE_ADMIN_API_KEY
}
```

Any `VITE_*` value is visible in browser bundle.

---

## Phase 1 Recommended Auth Options

### Option A — Private Network / VPS Only

Use Nginx Basic Auth or VPN-only access.

Pros:

- Simple.
- Good enough for private dashboard.

Cons:

- Not enough for write endpoints or public access.

### Option B — Backend Session Cookie

Backend login creates HTTP-only secure cookie.

Pros:

- Admin key/password not exposed to JS.
- Better for write endpoints.

Cons:

- Need CSRF handling.

### Option C — JWT

Backend returns access token and refresh token.

Pros:

- Common API pattern.

Cons:

- If stored in localStorage, token theft risk.
- Must design refresh/logout properly.

---

## Recommendation

- Phase 1 private dashboard: Nginx Basic Auth or backend session.
- Phase 1.5 write endpoints: backend session/cookie with CSRF protection or carefully implemented JWT.
- Phase 2 dangerous controls: require re-auth + confirmation phrase.

---

## Required Environment Variables Draft

Dashboard backend:

```env
DASHBOARD_ENV=production
DASHBOARD_SECRET_KEY=...
DASHBOARD_ADMIN_USERNAME=...
DASHBOARD_ADMIN_PASSWORD_HASH=...
DASHBOARD_ALLOWED_ORIGINS=https://dashboard.example.com
TRADING_DB_PATH=/path/to/data/trading.db
SIGNAL_DB_PATH=/path/to/data/signals.db
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

Hermes agent providers:

```env
TOKENROUTER_API_KEY=...
SWIFTROUTER_API_KEY=...
GEMINI_API_KEY=...
FREEMODEL_API_KEY=...
```

Never commit `.env` values.

---

## Audit Log Requirements

For all write actions:

- actor
- action
- entity type
- entity id
- old value
- new value
- IP address
- user agent
- timestamp

