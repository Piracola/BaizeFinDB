# BaizeFinDB Linux Server Deployment Skeleton

This directory contains a Linux deployment skeleton for a future Ubuntu server
running the FastAPI API, static Web UI, Telegram webhook, Celery worker, and
Celery beat scheduler. It is not a full production-hardening guide.

## Files

| File | Purpose |
| --- | --- |
| `../../Dockerfile` | Builds the FastAPI API image. Runtime configuration stays outside the image. |
| `../../docker-compose.server.yml` | Compose overlay that adds `api`, `worker`, and `beat` services on top of local `postgres` and `redis`. |
| `../scripts/server_deploy_check.py` | Standard-library deployment preflight for `.env`, compose config, optional image build, container state, API health, OPS overview/history/trends/readiness, provider status, Telegram status, radar overview, signal list, sampled signal analysis, backup check-only evidence, and M5 read-only smoke checks. |
| `../scripts/server_runtime_check.py` | Standard-library runtime sampler for health, ops overview, ops history, ops readiness, and optional ops trends after the API is running. |
| `../scripts/server_delivery_acceptance.py` | One-command delivery acceptance orchestrator that runs deploy preflight, backup check-only evidence, and runtime sampling into one bounded evidence bundle. |
| `../scripts/postgres_backup.py` | Standard-library PostgreSQL backup helper that runs `pg_dump` through the server compose overlay. |
| `../scripts/postgres_restore.py` | Standard-library PostgreSQL restore helper that streams a backup into `psql` through the server compose overlay. |
| `baizefindb-compose.service` | Example systemd unit for starting the compose project on boot. |
| `nginx-baizefindb.conf` | Example nginx reverse proxy for HTTPS/domain traffic to `127.0.0.1:8000`. |

## Ubuntu Prerequisites

Install Docker Engine and the Docker Compose plugin on the server. Verify:

```bash
docker --version
docker compose version
```

Clone or copy the repository to a fixed path. The examples below use:

```bash
/opt/baizefindb
```

## Environment

Create `.env` from the example and fill only server-safe values:

```bash
cd /opt/baizefindb
cp .env.example .env
chmod 600 .env
```

Required notes:

- Do not commit `.env`.
- Do not put real Telegram tokens, webhook secrets, database passwords, or API tokens in tracked files.
- `docker-compose.server.yml` overrides `DATABASE_URL` and `REDIS_URL` for the API container so it reaches `postgres` and `redis` by compose service name.
- `SERVER_DATABASE_URL` and `SERVER_REDIS_URL` are optional escape hatches for a later hardened setup. Use placeholders in docs, never real values.
- `RADAR_SCAN_INTERVAL_SECONDS` controls the Celery beat interval for the collect-then-scan task. The default is `300`.
- `RADAR_CONTINUOUS_P1_TRIGGER_COUNT` controls how many consecutive P1 scans create a quick-report candidate. The default is `3`.
- `RADAR_CONTINUITY_WINDOW_MINUTES` controls the continuity window for repeated P1 checks. The default is `30`.
- `TUSHARE_TOKEN` enables manual Tushare `stock_basic`, `anns_d`, and `stock_company` verification and collection. It does not enable Beat by itself; only `TUSHARE_ANNS_D_BEAT_ENABLED=true` adds the optional `anns_d` Beat task.
- `TELEGRAM_REQUIRE_BINDING=true` closes the local open fallback when no environment allow-list and no active database binding exist. Keep `/id` available to discover chat ids, then write active bindings before enabling pushes.
- `TELEGRAM_PUSH_ENABLED=true` makes the collect-then-scan task send a folded Telegram radar push after each successful scan. Keep it `false` until token, chat whitelist or active bindings, webhook secret, and strict binding choice are ready.

Example placeholders:

```dotenv
APP_ENV=server
TELEGRAM_BOT_TOKEN=<telegram-bot-token>
TELEGRAM_ALLOWED_CHAT_IDS=<comma-separated-chat-ids>
TELEGRAM_WEBHOOK_SECRET=<telegram-webhook-secret>
TELEGRAM_REQUIRE_BINDING=true
TELEGRAM_PUSH_ENABLED=false
SERVER_DATABASE_URL=postgresql+asyncpg://<db-user>:<db-password>@postgres:5432/<db-name>
SERVER_REDIS_URL=redis://redis:6379/0
RADAR_SCAN_INTERVAL_SECONDS=300
RADAR_CONTINUOUS_P1_TRIGGER_COUNT=3
RADAR_CONTINUITY_WINDOW_MINUTES=30
TUSHARE_TOKEN=<tushare-token>
```

For the current skeleton, the bundled PostgreSQL service still uses the existing
development defaults from `docker-compose.yml`. Replace those before any real
production use.

## Build And Start

Validate compose files:

```bash
docker compose config
docker compose -f docker-compose.yml -f docker-compose.server.yml config
```

Or run the bundled preflight:

```bash
python infra/scripts/server_deploy_check.py --strict-env
python infra/scripts/server_deploy_check.py --strict-env --json-output evidence/server-deploy-check.json
```

The preflight uses `docker compose config --quiet` so real environment values
from `.env` are validated without being printed to deployment logs. `--json-output`
writes a structured report with generated time, overall status, summary counts,
and each check result while preserving the terminal output.

Build the API image:

```bash
docker build -t baizefindb-api:dev .
```

Start database dependencies:

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis
```

Run migrations:

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml run --rm api alembic upgrade head
```

Start the API, worker, and beat scheduler:

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat
```

The beat process schedules `baizefindb.radar.collect_and_scan` every
`RADAR_SCAN_INTERVAL_SECONDS` seconds. That task first runs the minimal AKShare
collection and then runs the radar scan, so the scan consumes the freshest
available provider snapshots. If `TELEGRAM_PUSH_ENABLED=true`, it then sends the
latest scan as one P0/P1/P2 folded Telegram push and records the delivery in
`push_logs`.

## Health Checks

Check container state:

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml ps
```

Check API health from the server:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/health/ready
curl -fsS "http://127.0.0.1:8000/ops/overview?lookback_hours=24"
```

`/health/ready` should only return ready when PostgreSQL and Redis are reachable.
`/ops/overview` is read-only and summarizes server disk/CPU/memory resources,
recent radar scans, provider fetches, data quality, Telegram push logs, and
model degradation logs.

The same checks can be run through the bundled preflight:

```bash
python infra/scripts/server_deploy_check.py --check-containers --check-api
```

Check the read-only M5 endpoint contracts after the API is up, including OPS
overview/history/trends/readiness, AKShare status, Tushare status, Tushare
readiness, radar overview, Telegram status, `/radar/signals`, and sampled
`/radar/signals/{id}/analysis` when at least one signal exists. Empty radar
signal lists are warning-only so a fresh server is not blocked before its first
scan:

```bash
python infra/scripts/server_deploy_check.py --check-m5-smoke
```

Sample the running API for a short validation window. Endpoint failures or
`blocked` readiness return a failing exit code; warnings are recorded unless
`--fail-on-warning` is supplied:

```bash
python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --json-output runtime-check.json
```

Add `--include-ops-trends` when the same read-only runtime report should include
a compact summary of the latest `/ops/trends` bucket. This only reads existing
runtime tables and current server context; it does not persist resource samples
or provide a full monitoring stack:

```bash
python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --include-ops-trends --trend-bucket-count 12 --json-output runtime-check.json
```

When warning or blocked readiness needs shareable sanitized evidence, opt in to
writing OPS evidence during the same read-only runtime check. The evidence path
uses the `export_ops_evidence.py` report logic and defaults to the health/OPS
evidence endpoints without `/ops/trends`:

```bash
python infra/scripts/server_runtime_check.py --samples 3 --interval-seconds 30 --ops-evidence-output evidence/ops-evidence.json
```

If the same command also includes `--include-ops-trends --trend-bucket-count <n>`,
the evidence report additionally reads `/ops/trends` and writes sanitized
`snapshots.ops_trends`. This remains read-only, and `n` must be between 1 and 48.

If the only runtime warning is `radar_stale`, run a scan from existing provider
snapshots and repeat the runtime check:

```bash
curl -fsS -X POST http://127.0.0.1:8000/radar/scans/run
python infra/scripts/server_runtime_check.py --samples 2 --interval-seconds 1
```

Verify the backup toolchain without exporting data:

```bash
python infra/scripts/server_deploy_check.py --check-backup
python infra/scripts/server_deploy_check.py --check-backup --backup-check-json-output evidence/postgres-backup-check.json
python infra/scripts/postgres_backup.py --check-only --check-json-output evidence/postgres-backup-check.json
```

For one delivery acceptance run after the API is up, use the orchestrator. It
delegates to the existing deploy preflight, backup check-only evidence, and
runtime sampler, then writes a bounded summary under
`evidence/server-delivery-acceptance/`:

```bash
python infra/scripts/server_delivery_acceptance.py
```

By default the API target is `http://127.0.0.1:8000`. Use `--base-url` when
validating a reverse proxy, non-default port, or domain endpoint from the same
server:

```bash
python infra/scripts/server_delivery_acceptance.py --base-url https://<your-domain>
```

Delivery acceptance reads the top-level `status` field from each helper evidence
JSON. Warning-only evidence stays visible as non-blocking `warn`; missing,
unreadable, invalid, failing, `error`, or `blocked` evidence marks the stage as
`fail`. Use `--evidence-dir`, `--runtime-samples`, `--runtime-interval-seconds`,
and `--fail-fast` to adjust the evidence bundle or stop on the first failing
stage.

Verify Tushare `stock_basic` without writing to the database:

```bash
python infra/scripts/verify_tushare_stock_basic.py
python infra/scripts/verify_tushare_announcements.py --ann-date 20260503
python infra/scripts/verify_tushare_stock_company.py --exchange SZSE
```

Manually write Tushare provider snapshots after migrations:

```bash
python infra/scripts/collect_tushare_stock_basic.py
python infra/scripts/collect_tushare_announcements.py --ann-date 20260503
python infra/scripts/collect_tushare_stock_company.py --exchange SZSE
```

## Telegram Webhook

Expose the API through HTTPS before setting the Telegram webhook. The webhook path is:

```text
https://<your-domain>/telegram/webhook
```

Set the webhook with placeholders:

```bash
BOT_TOKEN="<telegram-bot-token>"
WEBHOOK_SECRET="<same-as-TELEGRAM_WEBHOOK_SECRET>"
WEBHOOK_URL="https://<your-domain>/telegram/webhook"

curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=${WEBHOOK_URL}" \
  -d "secret_token=${WEBHOOK_SECRET}"
```

If `TELEGRAM_WEBHOOK_SECRET` is configured, Telegram must send
`X-Telegram-Bot-Api-Secret-Token`; the FastAPI route validates it.

## systemd Auto Start

Copy and enable the example unit after adjusting `WorkingDirectory` if needed:

```bash
sudo cp infra/linux/baizefindb-compose.service /etc/systemd/system/baizefindb.service
sudo systemctl daemon-reload
sudo systemctl enable --now baizefindb.service
sudo systemctl status baizefindb.service
```

The unit starts the compose project. Run database migrations manually during
deployments before restarting the API.

## nginx Reverse Proxy

Install nginx and copy the sample config:

```bash
sudo cp infra/linux/nginx-baizefindb.conf /etc/nginx/sites-available/baizefindb
sudo ln -s /etc/nginx/sites-available/baizefindb /etc/nginx/sites-enabled/baizefindb
sudo nginx -t
sudo systemctl reload nginx
```

Replace `<your-domain>` and TLS certificate paths before enabling the site. The
sample includes an explicit `/telegram/webhook` location reminder.

## Logs

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml logs -f api
docker compose -f docker-compose.yml -f docker-compose.server.yml logs -f worker
docker compose -f docker-compose.yml -f docker-compose.server.yml logs -f beat
docker compose -f docker-compose.yml -f docker-compose.server.yml logs --tail=100 postgres
docker compose -f docker-compose.yml -f docker-compose.server.yml logs --tail=100 redis
journalctl -u baizefindb.service -f
```

## Backup

Run a timestamped PostgreSQL backup through the bundled helper:

```bash
python infra/scripts/postgres_backup.py
```

Or specify an exact output path before an upgrade:

```bash
python infra/scripts/postgres_backup.py --output backups/pre-upgrade.sql
```

The helper runs:

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml exec -T postgres \
  pg_dump -U baizefindb -d baizefindb
```

For a no-data preflight, use
`server_deploy_check.py --check-backup --backup-check-json-output <path>` or run
`postgres_backup.py --check-only --check-json-output <path>` directly. Both paths
only run `pg_dump --version` through the server compose overlay and write bounded
metadata about the repo root, output path, command shape, service, database user,
database name, and version-check result. They do not create a `.sql` file or
stream database contents.

`backups/` is ignored by git. Also back up `.env` through a secure server-side
secret process, not through git.

## Restore

Restoring is destructive for the target database state. Verify the compose
project, database name, and backup path before running it.

```bash
python infra/scripts/postgres_restore.py backups/pre-upgrade.sql --confirm-restore
```

The helper runs:

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U baizefindb -d baizefindb
```

## Upgrade

```bash
cd /opt/baizefindb
git pull --ff-only
docker compose -f docker-compose.yml -f docker-compose.server.yml build api
docker compose -f docker-compose.yml -f docker-compose.server.yml run --rm api alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat
curl -fsS http://127.0.0.1:8000/health/ready
```

## Rollback

Keep the previous git revision and database backup before upgrading. A minimal rollback:

```bash
git checkout <previous-known-good-commit>
docker compose -f docker-compose.yml -f docker-compose.server.yml build api
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat
```

If a migration changed data or schema, restore from the pre-upgrade database backup
with `infra/scripts/postgres_restore.py` or use a tested downgrade plan. Do not
improvise destructive database commands on the server.
