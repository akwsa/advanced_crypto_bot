# Running and Deploying Development

Last verified: 2026-09-22
Production service: `crypto-bot.service`
Production service user: `wkagung`
Production service workdir: `/home/wkagung/advanced_crypto_bot/advanced_crypto_bot`

## Current rule

Production is whatever `systemd` runs, not whatever SSH user is logged in.
Always derive the production path from:

```bash
sudo systemctl cat crypto-bot.service
```

At the time of writing:

```ini
User=wkagung
WorkingDirectory=/home/wkagung/advanced_crypto_bot/advanced_crypto_bot
ExecStart=/home/wkagung/advanced_crypto_bot/advanced_crypto_bot/venv/bin/python bot.py
StandardOutput=append:/home/wkagung/advanced_crypto_bot/advanced_crypto_bot/logs/bot.log
StandardError=append:/home/wkagung/advanced_crypto_bot/advanced_crypto_bot/logs/bot.log
```

The Google Cloud SSH login may be `agungkuthamawidagdo`, and that user may have a separate checkout under `/home/agungkuthamawidagdo/...`.
Do not deploy there unless the service file has first been migrated and verified.

## What went wrong on 2026-09-22

A local commit was pushed from the parent repository layout where app files were under `advanced_crypto_bot/...`.
The production service checkout is already inside the app root, where files must be `bot.py`, `autotrade/runtime.py`, etc.

Pulling the mismatched branch into `/home/wkagung/advanced_crypto_bot/advanced_crypto_bot` removed app-root files, including `bot.py`, and the service failed with:

```text
venv/bin/python: can't open file '/home/wkagung/advanced_crypto_bot/advanced_crypto_bot/bot.py': [Errno 2] No such file or directory
```

Rollback restored service to `cdcb9a4`, then the remote branch was repaired with a service-safe commit `69a329c`.

## Mandatory pre-deploy checks

Run this before any pull into production:

```bash
SVC=crypto-bot.service
WD=$(sudo systemctl cat "$SVC" | sed -n 's/^WorkingDirectory=//p' | tail -1)
USER=$(sudo systemctl cat "$SVC" | sed -n 's/^User=//p' | tail -1)
echo "service_user=$USER"
echo "service_workdir=$WD"
sudo -u "$USER" test -f "$WD/bot.py"
sudo -u "$USER" git -C "$WD" rev-parse --show-toplevel
sudo -u "$USER" git -C "$WD" rev-parse --short HEAD
```

Abort if `bot.py` is missing or the workdir is not the service app root.

## Safe deploy block

Use this shape for production pulls:

```bash
SVC=crypto-bot.service
BR=kiro/dryrun-activation-dashboard
WD=$(sudo systemctl cat "$SVC" | sed -n 's/^WorkingDirectory=//p' | tail -1)
USER=$(sudo systemctl cat "$SVC" | sed -n 's/^User=//p' | tail -1)

echo "=== SERVICE TARGET ==="
echo "user=$USER wd=$WD"
sudo -u "$USER" test -f "$WD/bot.py"

echo "=== BACKUP DB ==="
sudo -u "$USER" bash -lc "cd '$WD' && cp data/trading.db /tmp/trading_backup_$(date +%Y%m%d_%H%M).db"

echo "=== FETCH AND INSPECT DIFF ==="
sudo -u "$USER" git -C "$WD" fetch origin "$BR"
sudo -u "$USER" git -C "$WD" diff --name-status HEAD..origin/"$BR" | sed -n '1,120p'

echo "=== SAFETY CHECK ==="
sudo -u "$USER" bash -lc "cd '$WD' && git diff --name-status HEAD..origin/$BR | grep -E '^[AMD][[:space:]]+(bot.py|advanced_crypto_bot/bot.py)' && exit 44 || exit 0"

echo "=== PULL ==="
sudo -u "$USER" git -C "$WD" pull --ff-only origin "$BR"
sudo -u "$USER" git -C "$WD" rev-parse --short HEAD

echo "=== COMPILE ==="
sudo -u "$USER" bash -lc "cd '$WD' && venv/bin/python -m py_compile bot.py autotrade/runtime.py"

echo "=== RESTART ==="
sudo rm -f /tmp/advanced_crypto_bot-autotrade-worker.lock*
sudo systemctl restart "$SVC"
sleep 20
systemctl --no-pager --full status "$SVC"
sudo tail -120 "$WD/logs/bot.log"
```

If the safety check exits `44`, stop and inspect the branch layout. Do not pull.

## Manual bot process cleanup

Do not start production manually with `nohup` while the service exists.
If a manual admin bot is running, stop the service first, then remove only the duplicate manual process and stale lock:

```bash
sudo systemctl stop crypto-bot.service
ps -eo pid,user,lstart,cmd | grep "[b]ot.py" || true
sudo pkill -9 -f "python3 bot.py" || true
sudo rm -f /tmp/advanced_crypto_bot-autotrade-worker.lock*
sudo systemctl restart crypto-bot.service
```

Verify the service is active and Telegram notifications are being sent:

```bash
systemctl --no-pager --full status crypto-bot.service
sudo tail -120 /home/wkagung/advanced_crypto_bot/advanced_crypto_bot/logs/bot.log | grep -E "Signal notification sent|SQ-WORKER|DRY RUN|Traceback|ERROR" || true
```

## Current safe state after the incident

Remote branch `kiro/dryrun-activation-dashboard` was repaired so its HEAD is service-safe.
Production VM was fast-forwarded to the safe remote commit and the service remained active.

Known safe markers:

- `cdcb9a4` - last working service tree before the bad deploy.
- `69a329c` - service-safe remote repair commit with the same app tree as `cdcb9a4`.

Do not redeploy the bad commit `5cd5683` directly into `/home/wkagung/...`.
If a change is needed from that work, recreate it against the service app-root layout and verify the pre-deploy diff does not delete `bot.py`.
