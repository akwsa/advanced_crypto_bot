# Hermes Execution Cheatsheet

> Jalankan hanya setelah approval gates selesai.

---

## Available Hermes Providers

| Provider | Env Key | Use For |
|---|---|---|
| tokenrouter | `TOKENROUTER_API_KEY` | default reasoning/coding |
| swiftrouter | `SWIFTROUTER_API_KEY` | fallback coding/reasoning |
| gemini-pro | `GEMINI_API_KEY` | UX/review/large context |
| freemodel | `FREEMODEL_API_KEY` | experimental fallback |

---

## Suggested Order

1. Discovery Agent updates audit docs.
2. Winston finalizes architecture.
3. John finalizes PRD/stories.
4. Sally finalizes UX.
5. Amelia builds backend read-only.
6. Alex builds frontend read-only.
7. Peter tests and deploys.

---

## Global Guardrail Prompt Snippet

```text
This is documentation-approved implementation for BotPy Dashboard.
Do not modify bot.py unless the current task explicitly says so.
Do not enable real trading.
Do not write to existing bot tables.
Do not put admin API keys in frontend code.
Keep all new docs under docs/dashboard-web/ unless implementation phase explicitly requires code.
```

