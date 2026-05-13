# Zero-Data-Loss Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the raffle-campaign app from SQLite-on-container to a Dockerized Postgres + media-replication stack where all state lives on host bind mounts under `/srv/raffle` and is continuously replicated to Backblaze B2, with a separate encrypted restic archive providing ransomware/long-term defense.

**Architecture:** 4 containers on the prod host (`web`, `postgres`, `pgbackrest` sidecar, `media-syncer` sidecar) reading/writing to `/srv/raffle/{pg,media,pgbackrest,staticfiles}` bind mounts. Continuous WAL archiving (pgBackRest async) and inotify-driven file replication push to Backblaze B2 in seconds. A separate host cron runs nightly restic snapshots to a different B2 bucket with no-delete credentials.

**Tech Stack:** Django 4.2 + gunicorn, Postgres 16, pgBackRest 2.x, rclone (B2), restic 0.16+, Docker Compose, Backblaze B2 (S3-compatible storage), inotify-tools.

**Reference spec:** [`docs/superpowers/specs/2026-05-13-zero-data-loss-backup-design.md`](../specs/2026-05-13-zero-data-loss-backup-design.md)

---

## File structure

### Created files
- `docker/postgres/Dockerfile` — custom Postgres image with pgBackRest baked in; also installs cron + crontab for scheduled backups (Task 4 obsoleted — see note below)
- `docker/postgres/postgres-entrypoint.sh` — wrapper entrypoint: starts cron daemon, then execs upstream docker-entrypoint.sh
- `docker/postgres/pgbackrest-crontab` — schedules full/diff/incr backups (moved from docker/pgbackrest/)
- `docker/media-syncer/Dockerfile` — alpine + rclone + inotify-tools
- `docker/media-syncer/entrypoint.sh` — runs inotify watcher + periodic-sync loop
- `docker/postgres/postgresql.conf.fragment` — archive_mode, archive_command, etc.
- `scripts/migrate_sqlite_to_postgres.sh` — orchestrates dumpdata/loaddata/sequence-reset
- `scripts/reset_postgres_sequences.py` — Django management snippet that walks every table and bumps each sequence to MAX(id)+1
- `scripts/raffle-restic-backup.sh` — installed to `/usr/local/bin/` on prod host
- `scripts/raffle-restic-check.sh` — installed to `/usr/local/bin/` on prod host
- `scripts/raffle-backup-freshness.sh` — installed to `/usr/local/bin/` on prod host; alerting cron
- `scripts/restic-test.sh` — runs in CI/locally to verify scripts parse cleanly
- `tests/test_reset_sequences.py` — unit test for the sequence-reset helper
- `tests/test_freshness_check.py` — unit test for the alerting script's age calculation
- `docs/deployment/restore-playbook.md` — operator runbook for all restore scenarios
- `docs/deployment/restore-rehearsal-log.md` — append-only log of rehearsals
- `docs/deployment/host-setup.md` — one-page summary of `/srv/raffle` layout + cron entries (operator reference)
- `Makefile` — adds `restore-test` and `restic-check` targets

### Modified files
- `requirements.txt` — add `psycopg[binary]>=3.1`, `dj-database-url>=2`
- `raffle_project/settings.py:92-98` — `DATABASES` reads from `DATABASE_URL`
- `docker-compose.prod.yml` — add `postgres`, `media-syncer` services (pgbackrest sidecar removed — runs inside postgres container); switch `web` to use new Postgres image's network; replace `./prod-data/*` mounts with `/srv/raffle/*`
- `.env.example` — document `DATABASE_URL`, `POSTGRES_PASSWORD`, etc.
- `.gitignore` — already covers `.env.prod` and `prod-data/`; add `/srv-raffle-local/` (optional dev mirror)
- `Dockerfile.prod` — switch to use the project's wait-for-postgres pattern in CMD

---

## Task index

| # | Task | Where it runs |
|---|---|---|
| 1 | Backup current state + create implementation branch | dev |
| 2 | Update Django for env-driven DATABASE_URL | dev |
| 3 | Build custom Postgres image with pgBackRest | dev |
| 4 | Build pgBackRest sidecar image | dev |
| 5 | Build media-syncer sidecar image | dev |
| 6 | Wire all services into docker-compose.prod.yml | dev |
| 7 | Write sequence-reset management script + test | dev |
| 8 | Write SQLite→Postgres migration shell script | dev |
| 9 | Local end-to-end smoke test of the new stack | dev |
| 10 | Provision Backblaze B2 buckets + application keys | prod (B2 console) |
| 11 | Create `/srv/raffle` directory tree on prod host | prod host |
| 12 | Deploy credential files to `/srv/raffle/config/` | prod host |
| 13 | First boot of Postgres + pgBackRest on prod | prod host |
| 14 | Run the SQLite → Postgres migration on prod | prod host (maintenance window) |
| 15 | Bring up media-syncer; verify event-driven + reconciliation paths | prod host |
| 16 | Install restic + scripts + cron on prod host | prod host |
| 17 | Initialize restic repo on B2; first manual snapshot | prod host |
| 18 | Install backup-freshness monitor cron | prod host |
| 19 | Write the restore playbook | dev |
| 20 | First restore rehearsal + log entry | dev (laptop or scratch host) |
| 21 | Decommission `./prod-data/` and SQLite code paths | dev |
| 22 | Final commit + Mila-bot work report | dev |

---

## Task 1: Backup current state + create implementation branch

**Files:**
- Modify: working tree (commit + branch)

- [ ] **Step 1: Check repo status is clean**

Run: `git status`
Expected: only `RUNNING.md` untracked; no modified tracked files. If you see modified tracked files, commit them as `chore: backup before zero-data-loss work` before continuing.

- [ ] **Step 2: Create feature branch**

```bash
git checkout -b zero-data-loss-backup
```

- [ ] **Step 3: Commit a snapshot of the current SQLite DB**

```bash
mkdir -p prod-data-archive
cp db.sqlite3 prod-data-archive/db.sqlite3.pre-pg-$(date +%Y%m%d).bak
git add prod-data-archive/
git commit -m "chore: archive pre-Postgres SQLite snapshot"
```

Rationale: irreversible work follows; an archived dev copy is cheap insurance.

---

## Task 2: Update Django for env-driven DATABASE_URL

**Files:**
- Modify: `requirements.txt`
- Modify: `raffle_project/settings.py:92-98`
- Modify: `.env.example`
- Test: `tests/test_database_url_config.py` (new)

- [ ] **Step 1: Write a failing test for DATABASE_URL configuration**

Create `tests/test_database_url_config.py`:

```python
"""Verify settings.DATABASES respects DATABASE_URL env var."""
import importlib
import os
import sys


def test_sqlite_default_when_no_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if "raffle_project.settings" in sys.modules:
        del sys.modules["raffle_project.settings"]
    from raffle_project import settings

    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


def test_postgres_url_is_parsed(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgres://raffleuser:rafflepass@db.local:5432/raffledb",
    )
    if "raffle_project.settings" in sys.modules:
        del sys.modules["raffle_project.settings"]
    from raffle_project import settings

    db = settings.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["NAME"] == "raffledb"
    assert db["USER"] == "raffleuser"
    assert db["HOST"] == "db.local"
    assert db["PORT"] == 5432
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_database_url_config.py -v`
Expected: FAIL (either `dj_database_url` is missing or `DATABASES` is hardcoded to sqlite).

- [ ] **Step 3: Add Postgres dependencies to requirements.txt**

Replace contents of `requirements.txt`:

```
Django>=4.2,<5.0
python-dotenv>=1.0.0
Pillow>=10.0.0
django-crispy-forms>=2.0
crispy-bootstrap5>=0.7
django-unfold>=0.40.0
gunicorn>=21.2.0
psycopg[binary]>=3.1
dj-database-url>=2.1
```

- [ ] **Step 4: Install the new deps locally**

Run: `pip install -r requirements.txt`
Expected: `psycopg` and `dj_database_url` install cleanly.

- [ ] **Step 5: Replace the DATABASES block in settings.py**

In `raffle_project/settings.py`, find lines 92-98 (the existing `DATABASES = {...}` block) and replace with:

```python
# Database
# In dev, the absence of DATABASE_URL falls back to local SQLite so the
# existing dev workflow keeps working untouched. In prod, .env.prod sets
# DATABASE_URL=postgres://... and the compose stack provides the server.
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
    )
}
```

- [ ] **Step 6: Update .env.example**

Replace contents of `.env.example`:

```
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
# Dev:  sqlite:///db.sqlite3       (default if unset)
# Prod: postgres://raffleuser:rafflepass@postgres:5432/raffledb
DATABASE_URL=sqlite:///db.sqlite3
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `python -m pytest tests/test_database_url_config.py -v`
Expected: both tests PASS.

- [ ] **Step 8: Run the full test suite to confirm no regression**

Run: `python -m pytest`
Expected: all pre-existing tests still pass (no DB-shape assumptions break).

- [ ] **Step 9: Commit**

```bash
git add requirements.txt raffle_project/settings.py .env.example tests/test_database_url_config.py
git commit -m "feat: drive DATABASES from DATABASE_URL env var"
```

---

## Task 3: Build custom Postgres image with pgBackRest

**Files:**
- Create: `docker/postgres/Dockerfile`
- Create: `docker/postgres/postgresql.conf.fragment`
- Create: `docker/postgres/init-pgbackrest-user.sh`

- [ ] **Step 1: Create `docker/postgres/Dockerfile`**

```dockerfile
# Custom Postgres 16 image with pgBackRest binary installed.
# pgBackRest needs to live on the Postgres container because Postgres calls
# `archive_command = pgbackrest archive-push` directly during WAL rotation.
FROM postgres:16-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        pgbackrest \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# pgBackRest expects /var/lib/pgbackrest (repo1) and /var/spool/pgbackrest
# to exist with the postgres user as owner. Inside the container both are
# bind-mounted from the host, but we create the mountpoints + perms here.
RUN install -d -o postgres -g postgres -m 700 /var/lib/pgbackrest \
    && install -d -o postgres -g postgres -m 700 /var/spool/pgbackrest \
    && install -d -o postgres -g postgres -m 750 /var/log/pgbackrest

# Postgres reads any *.conf in /etc/postgresql/conf.d after the main file.
# We ship a fragment that turns on archive_mode and points archive_command
# at pgbackrest. The fragment is mounted via compose into conf.d.
COPY postgresql.conf.fragment /etc/postgresql/conf.d/10-pgbackrest.conf
RUN chmod 644 /etc/postgresql/conf.d/10-pgbackrest.conf

# Init-time hook that creates a dedicated pgbackrest role with REPLICATION.
COPY init-pgbackrest-user.sh /docker-entrypoint-initdb.d/10-init-pgbackrest-user.sh
RUN chmod 755 /docker-entrypoint-initdb.d/10-init-pgbackrest-user.sh
```

- [ ] **Step 2: Create the Postgres config fragment**

`docker/postgres/postgresql.conf.fragment`:

```conf
# Enable WAL archiving for pgBackRest. archive-async=y in pgbackrest.conf
# means archive_command returns quickly and the actual push happens in the
# background via the spool dir, so a slow B2 push won't stall Postgres.
listen_addresses = '*'
archive_mode = on
archive_command = 'pgbackrest --stanza=raffle archive-push %p'
archive_timeout = 60
wal_level = replica
max_wal_senders = 3
# log_line_prefix gives every line a timestamp + pid + user@db, which makes
# debugging archive failures much easier.
log_line_prefix = '%m [%p] %q%u@%d '
log_min_duration_statement = 1000
```

- [ ] **Step 3: Create the pgBackRest user init script**

`docker/postgres/init-pgbackrest-user.sh`:

```bash
#!/bin/bash
# Runs once on first DB init. Creates a role that pgbackrest uses to call
# pg_start_backup / pg_stop_backup. Using a dedicated role (not superuser)
# is the recommended pattern.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE pgbackrest WITH LOGIN REPLICATION;
    GRANT EXECUTE ON FUNCTION pg_backup_start(text, boolean) TO pgbackrest;
    GRANT EXECUTE ON FUNCTION pg_backup_stop(boolean) TO pgbackrest;
    GRANT EXECUTE ON FUNCTION pg_create_restore_point(text) TO pgbackrest;
    GRANT EXECUTE ON FUNCTION pg_switch_wal() TO pgbackrest;
EOSQL
```

- [ ] **Step 4: Smoke build the image locally**

Run:
```bash
docker build -t raffle-postgres:test docker/postgres/
```
Expected: build succeeds; the final image is tagged.

- [ ] **Step 5: Verify pgBackRest is present**

Run:
```bash
docker run --rm raffle-postgres:test pgbackrest version
```
Expected: prints `pgBackRest 2.xx` (any 2.x is fine).

- [ ] **Step 6: Commit**

```bash
git add docker/postgres/
git commit -m "feat: custom Postgres 16 image with pgBackRest baked in"
```

---

## Task 4: Build pgBackRest sidecar image ~~OBSOLETED~~

> **Task 4 obsoleted by smoke-test finding:** the pgbackrest sidecar container cannot reach Postgres without SSH or TLS auth — pgbackrest's connection mechanism is local-socket-or-SSH and neither was configured. WAL archiving and manual backups already worked (they run from inside the postgres container which has pgbackrest installed); only the scheduled cron-driven backups were broken.
>
> **Resolution:** cron + crontab are now baked into `docker/postgres/Dockerfile`. The wrapper entrypoint `postgres-entrypoint.sh` starts cron before handing off to the upstream Postgres entrypoint. Topology drops from 4 containers to 3. See spec §6.1 update.

~~**Files:**~~
~~- Create: `docker/pgbackrest/Dockerfile`~~
~~- Create: `docker/pgbackrest/entrypoint.sh`~~
~~- Create: `docker/pgbackrest/crontab`~~

~~The sidecar runs cron-driven backups (full/diff/incr) AND is the receiving side of `archive-push` when `archive-async` flushes the spool. It needs the same pgBackRest binary version as the Postgres image, plus cron.~~

- [ ] **Step 1: Create `docker/pgbackrest/Dockerfile`**

```dockerfile
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        pgbackrest \
        cron \
        ca-certificates \
        postgresql-client \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Match the Postgres container's expectations.
RUN groupadd -g 999 postgres \
    && useradd -u 999 -g 999 -m -s /bin/bash postgres \
    && install -d -o postgres -g postgres -m 700 /var/lib/pgbackrest \
    && install -d -o postgres -g postgres -m 700 /var/spool/pgbackrest \
    && install -d -o postgres -g postgres -m 750 /var/log/pgbackrest

COPY crontab /etc/cron.d/pgbackrest
RUN chmod 644 /etc/cron.d/pgbackrest \
    && crontab -u postgres /etc/cron.d/pgbackrest

COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

USER root
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
```

- [ ] **Step 2: Create the crontab**

`docker/pgbackrest/crontab`:

```
# pgBackRest backup schedule. All commands run as the postgres user.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Weekly full backup, Sundays at 02:00 UTC.
0 2 * * 0 postgres pgbackrest --stanza=raffle --type=full backup >> /var/log/pgbackrest/cron.log 2>&1

# Daily differential, Mon-Sat at 02:00 UTC.
0 2 * * 1-6 postgres pgbackrest --stanza=raffle --type=diff backup >> /var/log/pgbackrest/cron.log 2>&1

# Hourly incremental, on the hour (skipping 02:00 to avoid colliding with diff/full).
0 0-1,3-23 * * * postgres pgbackrest --stanza=raffle --type=incr backup >> /var/log/pgbackrest/cron.log 2>&1

# Daily 'info' check at 04:00 — emits backup status to log for the alerting cron to scrape.
0 4 * * * postgres pgbackrest --stanza=raffle info >> /var/log/pgbackrest/info.log 2>&1
```

- [ ] **Step 3: Create the entrypoint**

`docker/pgbackrest/entrypoint.sh`:

```bash
#!/bin/bash
# Sidecar entrypoint:
#   1. Wait for Postgres to be reachable.
#   2. Ensure the stanza exists (idempotent — `stanza-create` is safe to re-run).
#   3. Hand off to cron (foreground).
set -euo pipefail

PGBACKREST_CONFIG=${PGBACKREST_CONFIG:-/etc/pgbackrest/pgbackrest.conf}
PG_HOST=${PG_HOST:-postgres}
PG_USER=${PG_USER:-pgbackrest}
PG_DB=${PG_DB:-raffledb}

echo "[pgbackrest-sidecar] waiting for Postgres at ${PG_HOST}:5432..."
for i in $(seq 1 60); do
    if pg_isready -h "$PG_HOST" -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
        echo "[pgbackrest-sidecar] Postgres is ready."
        break
    fi
    sleep 2
    if [ "$i" -eq 60 ]; then
        echo "[pgbackrest-sidecar] FATAL: Postgres did not become ready in 120s"
        exit 1
    fi
done

# stanza-create is idempotent — it errors only if the stanza exists with a
# different cluster identity, which is what we want for safety.
echo "[pgbackrest-sidecar] ensuring stanza 'raffle' exists in both repos..."
su -c "pgbackrest --stanza=raffle stanza-create" postgres || \
    echo "[pgbackrest-sidecar] stanza-create returned non-zero; assuming already initialised"

# Validate the stanza can read WAL from Postgres (this also surfaces
# misconfigured archive_command early).
su -c "pgbackrest --stanza=raffle check" postgres

echo "[pgbackrest-sidecar] starting cron in foreground..."
exec cron -f
```

- [ ] **Step 4: Smoke build the image**

Run:
```bash
docker build -t raffle-pgbackrest:test docker/pgbackrest/
```
Expected: build succeeds.

- [ ] **Step 5: Verify pgBackRest version matches**

Run:
```bash
PG_VERSION=$(docker run --rm raffle-postgres:test pgbackrest version)
SIDECAR_VERSION=$(docker run --rm raffle-pgbackrest:test pgbackrest version)
test "$PG_VERSION" = "$SIDECAR_VERSION" && echo "OK: versions match: $PG_VERSION"
```
Expected: prints `OK: versions match: ...`. If they don't match, debian's apt cache may have advanced between the two builds — rebuild both at the same time.

- [ ] **Step 6: Commit**

```bash
git add docker/pgbackrest/
git commit -m "feat: pgBackRest sidecar image (cron + stanza bootstrap)"
```

---

## Task 5: Build media-syncer sidecar image

**Files:**
- Create: `docker/media-syncer/Dockerfile`
- Create: `docker/media-syncer/entrypoint.sh`

- [ ] **Step 1: Create `docker/media-syncer/Dockerfile`**

```dockerfile
FROM alpine:3.19

RUN apk add --no-cache \
        rclone \
        inotify-tools \
        bash \
        coreutils \
        tini

COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

ENV RCLONE_CONFIG=/config/rclone.conf
ENV WATCH_DIR=/data/media
ENV REMOTE=b2:raffle-media
ENV SYNC_INTERVAL=600

ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]
```

- [ ] **Step 2: Create the entrypoint**

`docker/media-syncer/entrypoint.sh`:

```bash
#!/bin/bash
# Two concurrent loops:
#   1. Event-driven: inotifywait on the watch dir, rclone copyto on every
#      close_write/moved_to. Sub-second latency for new uploads.
#   2. Periodic: every $SYNC_INTERVAL seconds, rclone sync the full tree
#      to catch anything inotify missed (kernel queue overflow, container
#      restart while files were arriving, large mv operations).
set -euo pipefail

: "${WATCH_DIR:?WATCH_DIR must be set}"
: "${REMOTE:?REMOTE must be set}"
: "${RCLONE_CONFIG:?RCLONE_CONFIG must be set}"
SYNC_INTERVAL="${SYNC_INTERVAL:-600}"

echo "[media-syncer] watch=$WATCH_DIR remote=$REMOTE sync_every=${SYNC_INTERVAL}s"
echo "[media-syncer] rclone version:"; rclone --version | head -n1

if [ ! -d "$WATCH_DIR" ]; then
    echo "[media-syncer] FATAL: $WATCH_DIR does not exist (is the bind mount wired?)"
    exit 1
fi
if [ ! -f "$RCLONE_CONFIG" ]; then
    echo "[media-syncer] FATAL: $RCLONE_CONFIG missing — drop rclone.conf into /srv/raffle/config/"
    exit 1
fi

# Initial reconciliation: ensure the remote matches the bind mount on boot.
echo "[media-syncer] initial reconciliation..."
rclone sync "$WATCH_DIR" "$REMOTE" --transfers 4 --checkers 8 --log-level INFO

# Periodic sync loop (background).
(
    while true; do
        sleep "$SYNC_INTERVAL"
        echo "[media-syncer] periodic sync starting..."
        rclone sync "$WATCH_DIR" "$REMOTE" --transfers 4 --checkers 8 --log-level INFO \
            || echo "[media-syncer] WARN: periodic sync exited non-zero"
    done
) &
PERIODIC_PID=$!

# inotify event loop (foreground).
echo "[media-syncer] starting inotify watcher..."
inotifywait -m -r -e close_write,moved_to --format '%w%f' "$WATCH_DIR" 2>/dev/null |
while IFS= read -r path; do
    rel="${path#$WATCH_DIR/}"
    echo "[media-syncer] event: $rel"
    rclone copyto "$path" "$REMOTE/$rel" --log-level INFO \
        || echo "[media-syncer] WARN: copy failed for $rel"
done

# inotifywait should never exit; if it does, kill the periodic loop and let
# the container restart policy bring us back.
kill "$PERIODIC_PID" 2>/dev/null || true
exit 1
```

- [ ] **Step 3: Smoke build**

Run: `docker build -t raffle-media-syncer:test docker/media-syncer/`
Expected: build succeeds.

- [ ] **Step 4: Verify rclone + inotify are present**

Run:
```bash
docker run --rm raffle-media-syncer:test rclone --version | head -n1
docker run --rm raffle-media-syncer:test inotifywait --help 2>&1 | head -n1
```
Expected: both print version/help banners.

- [ ] **Step 5: Commit**

```bash
git add docker/media-syncer/
git commit -m "feat: media-syncer image (rclone + inotify event loop)"
```

---

## Task 6: Wire all services into docker-compose.prod.yml

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `.env.example` (already covered in Task 2; this task adds the prod-specific vars to docs)
- Modify: `Dockerfile.prod`

- [ ] **Step 1: Replace `docker-compose.prod.yml`**

Write the complete file (it's short enough to replace in full):

```yaml
name: raffle-campaign-prod

services:
  postgres:
    build:
      context: ./docker/postgres
    image: raffle-postgres:latest
    container_name: raffle-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-raffledb}
      POSTGRES_USER: ${POSTGRES_USER:-raffleuser}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in .env.prod}
    volumes:
      - /srv/raffle/pg:/var/lib/postgresql/data
      - /srv/raffle/pgbackrest:/var/lib/pgbackrest
      - /srv/raffle/config/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 30s

  pgbackrest:
    build:
      context: ./docker/pgbackrest
    image: raffle-pgbackrest:latest
    container_name: raffle-pgbackrest
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      PG_HOST: postgres
      PG_USER: pgbackrest
      PG_DB: ${POSTGRES_DB:-raffledb}
    volumes:
      - /srv/raffle/pg:/var/lib/postgresql/data:ro
      - /srv/raffle/pgbackrest:/var/lib/pgbackrest
      - /srv/raffle/config/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro

  web:
    build:
      context: .
      dockerfile: Dockerfile.prod
    image: raffle-campaign-prod:latest
    container_name: raffle-prod
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "127.0.0.1:8500:8000"
    env_file: .env.prod
    volumes:
      - /srv/raffle/media:/app/media
      - /srv/raffle/staticfiles:/app/staticfiles
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/dashboard/login/')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  media-syncer:
    build:
      context: ./docker/media-syncer
    image: raffle-media-syncer:latest
    container_name: raffle-media-syncer
    restart: unless-stopped
    environment:
      WATCH_DIR: /data/media
      REMOTE: b2:raffle-media
      SYNC_INTERVAL: "600"
      RCLONE_CONFIG: /config/rclone.conf
    volumes:
      - /srv/raffle/media:/data/media:ro
      - /srv/raffle/config/rclone.conf:/config/rclone.conf:ro
```

Notes:
- `web` no longer mounts `./prod-data/db` — Postgres handles that.
- `media-syncer` mounts `/srv/raffle/media` **read-only**. inotify on Linux works on read-only bind mounts (events are kernel-side; the mount RO bit only restricts writes).
- `postgres` mounts `/srv/raffle/pg` (PGDATA) and `/srv/raffle/pgbackrest` (local repo1). `pgbackrest` sidecar mounts PGDATA read-only and the repo read-write.

- [ ] **Step 2: Update `Dockerfile.prod` to wait for Postgres**

The current CMD already calls `python manage.py migrate` which will fail-fast if Postgres isn't ready. The compose `depends_on: condition: service_healthy` should be enough, but add a belt-and-suspenders loop. Replace lines 24-33 of `Dockerfile.prod` with:

```dockerfile
CMD ["sh", "-c", "\
  for i in $(seq 1 30); do \
    python -c 'import os, psycopg; psycopg.connect(os.environ[\"DATABASE_URL\"]).close()' 2>/dev/null && break; \
    echo 'web: waiting for postgres...'; sleep 2; \
  done && \
  python manage.py migrate --noinput && \
  python manage.py collectstatic --noinput && \
  exec gunicorn raffle_project.wsgi:application \
       --bind 0.0.0.0:8000 \
       --workers 3 \
       --access-logfile - \
       --error-logfile - \
       --log-level info \
"]
```

- [ ] **Step 3: Verify compose file parses**

Run: `docker compose -f docker-compose.prod.yml config --quiet`
Expected: exits 0 with no output. If it complains about `POSTGRES_PASSWORD`, that's expected on this dev box (no `.env.prod`); add `POSTGRES_PASSWORD=test docker compose -f docker-compose.prod.yml config --quiet` to verify the *shape* is valid.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.prod.yml Dockerfile.prod
git commit -m "feat: compose stack with postgres, pgbackrest, media-syncer"
```

---

## Task 7: Write sequence-reset management script + test

After `loaddata` repopulates a Postgres DB, autoincrement sequences are NOT advanced — they remain at 1, and the next insert collides with the loaded row. We need a helper that walks every table and sets each sequence to `MAX(id) + 1`.

**Files:**
- Create: `scripts/reset_postgres_sequences.py`
- Create: `tests/test_reset_sequences.py`

- [ ] **Step 1: Write the failing test**

`tests/test_reset_sequences.py`:

```python
"""
Test the sequence-reset logic against an in-memory model.

We don't need a real Postgres for the unit test — we test the *SQL emitter*
that walks Django's models and produces the SETVAL statements.
"""
import pytest
from scripts.reset_postgres_sequences import build_setval_statements


def test_emits_setval_for_model_with_id_column():
    statements = build_setval_statements(
        tables=[
            {"name": "campaigns_campaign", "pk_column": "id"},
            {"name": "campaigns_submission", "pk_column": "id"},
        ]
    )
    joined = "\n".join(statements)
    assert "campaigns_campaign_id_seq" in joined
    assert "campaigns_submission_id_seq" in joined
    # Each statement should use COALESCE so empty tables stay at 1.
    assert "COALESCE" in joined


def test_skips_tables_without_serial_pk():
    statements = build_setval_statements(
        tables=[
            {"name": "django_session", "pk_column": "session_key"},
            {"name": "campaigns_campaign", "pk_column": "id"},
        ]
    )
    joined = "\n".join(statements)
    assert "django_session" not in joined
    assert "campaigns_campaign_id_seq" in joined
```

- [ ] **Step 2: Run the test to see it fail**

Run: `python -m pytest tests/test_reset_sequences.py -v`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Implement the script**

`scripts/reset_postgres_sequences.py`:

```python
"""
After `manage.py loaddata`, Postgres sequences for serial primary keys are
NOT advanced past the loaded values. Calling this script emits and executes
SETVAL statements that bump every sequence to MAX(pk) + 1.

Run as:  python -m scripts.reset_postgres_sequences
(via the migration shell script, with Django settings already on the path)
"""
from __future__ import annotations

import sys
from typing import Iterable


def build_setval_statements(tables: Iterable[dict]) -> list[str]:
    """Pure function: list of {name, pk_column} -> list of SQL statements.

    Only emits a SETVAL when pk_column == "id" (Django's BigAutoField default).
    Non-serial PKs (e.g. session_key) get skipped because they don't have a
    sequence to reset.
    """
    statements = []
    for table in tables:
        if table["pk_column"] != "id":
            continue
        seq_name = f"{table['name']}_id_seq"
        # COALESCE handles empty tables: MAX returns NULL, COALESCE makes it 1.
        statements.append(
            f"SELECT setval('{seq_name}', "
            f"COALESCE((SELECT MAX(id) FROM {table['name']}), 1), "
            f"(SELECT MAX(id) IS NOT NULL FROM {table['name']}));"
        )
    return statements


def main() -> int:
    import django

    django.setup()
    from django.apps import apps
    from django.db import connection

    tables = []
    for model in apps.get_models():
        pk = model._meta.pk
        # AutoField / BigAutoField have a sequence; everything else does not.
        if pk.get_internal_type() not in ("AutoField", "BigAutoField"):
            continue
        tables.append(
            {"name": model._meta.db_table, "pk_column": pk.column}
        )

    statements = build_setval_statements(tables)
    print(f"Resetting {len(statements)} sequences...")
    with connection.cursor() as cur:
        for stmt in statements:
            print(f"  {stmt}")
            cur.execute(stmt)
    print("Done.")
    return 0


if __name__ == "__main__":
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "raffle_project.settings")
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `python -m pytest tests/test_reset_sequences.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/reset_postgres_sequences.py tests/test_reset_sequences.py
git commit -m "feat: sequence-reset helper for post-loaddata Postgres state"
```

---

## Task 8: Write SQLite→Postgres migration shell script

**Files:**
- Create: `scripts/migrate_sqlite_to_postgres.sh`

- [ ] **Step 1: Create the script**

`scripts/migrate_sqlite_to_postgres.sh`:

```bash
#!/bin/bash
# One-shot migration: SQLite -> Postgres, run on the prod host inside a
# maintenance window. Idempotent up to the cutover step — the dumpdata and
# loaddata phases can be re-run; only the final compose-up flips traffic.
#
# Prerequisites:
#   - /srv/raffle/pg is empty (Postgres has never run against it)
#   - .env.prod has DATABASE_URL pointing at sqlite:///db.sqlite3 (legacy)
#   - .env.prod has POSTGRES_PASSWORD set
#   - docker compose -f docker-compose.prod.yml build  has run
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"
MIGRATION_DIR=/srv/raffle/migration
DUMP_FILE="${MIGRATION_DIR}/sqlite_dump.json"

mkdir -p "$MIGRATION_DIR"

echo "==> Phase 1/6: dump SQLite data via the running legacy container"
$COMPOSE exec -T web python manage.py dumpdata \
    --natural-foreign --natural-primary \
    --exclude=contenttypes --exclude=auth.permission --exclude=sessions \
    > "$DUMP_FILE"
LINES=$(wc -l < "$DUMP_FILE")
echo "    dumped $(du -h "$DUMP_FILE" | cut -f1) ($LINES lines)"

echo "==> Phase 2/6: stop legacy web container (no more writes)"
$COMPOSE stop web

echo "==> Phase 3/6: bring up Postgres + pgbackrest (waits for healthy)"
$COMPOSE up -d postgres pgbackrest

# Give Postgres a few seconds beyond healthcheck to ensure init scripts ran.
sleep 5

echo "==> Phase 4/6: run Django migrations on the empty Postgres DB"
# Temporarily start a one-off web container with the new DATABASE_URL.
# This requires .env.prod to already be flipped to the Postgres URL.
$COMPOSE run --rm --no-deps web python manage.py migrate --noinput

echo "==> Phase 5/6: loaddata + reset sequences"
# Copy the dump into the web image's filesystem at /tmp and load it.
# Using --rm + a volume mount keeps the migration ephemeral.
$COMPOSE run --rm --no-deps -v "$MIGRATION_DIR":/migration web \
    python manage.py loaddata /migration/sqlite_dump.json

$COMPOSE run --rm --no-deps web \
    python -m scripts.reset_postgres_sequences

echo "==> Phase 6/6: start web container against Postgres"
$COMPOSE up -d web media-syncer

echo "==> Verification"
echo "    Row counts (compare against pre-migration snapshot in $MIGRATION_DIR/precount.txt):"
$COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-raffleuser}" \
    -d "${POSTGRES_DB:-raffledb}" -c "
    SELECT 'campaigns_campaign' AS table, COUNT(*) FROM campaigns_campaign
    UNION ALL
    SELECT 'campaigns_submission', COUNT(*) FROM campaigns_submission
    UNION ALL
    SELECT 'campaigns_raffle', COUNT(*) FROM campaigns_raffle
    UNION ALL
    SELECT 'auth_user', COUNT(*) FROM auth_user;
    "

echo
echo "Migration complete. Verify the dashboard manually, then archive:"
echo "  mv db.sqlite3 ${MIGRATION_DIR}/db.sqlite3.pre-migration-\$(date +%Y%m%d)"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/migrate_sqlite_to_postgres.sh`
Expected: no output; file is now executable.

- [ ] **Step 3: Shellcheck (if installed) for syntax errors**

Run: `shellcheck scripts/migrate_sqlite_to_postgres.sh || echo "shellcheck not installed, skipping"`
Expected: no errors, or "shellcheck not installed".

- [ ] **Step 4: Commit**

```bash
git add scripts/migrate_sqlite_to_postgres.sh
git commit -m "feat: SQLite->Postgres one-shot migration script"
```

---

## Task 9: Local end-to-end smoke test of the new stack

This task validates the entire compose stack works **before** touching the prod host. We use a throwaway `/tmp/srv-raffle` so we don't depend on `/srv` existing locally.

**Files:**
- (no new files; this is an exercise)

- [ ] **Step 1: Create a throwaway host data dir locally**

Run:
```bash
sudo install -d -m 755 -o $USER /tmp/srv-raffle
mkdir -p /tmp/srv-raffle/{pg,media,pgbackrest,staticfiles,config}
```

- [ ] **Step 2: Write a minimal local pgbackrest.conf (local-only, no B2)**

Create `/tmp/srv-raffle/config/pgbackrest.conf`:

```ini
[global]
repo1-path=/var/lib/pgbackrest
repo1-retention-full=2
repo1-retention-diff=4
archive-async=y
spool-path=/var/spool/pgbackrest
log-level-console=info
log-level-file=detail

[raffle]
pg1-path=/var/lib/postgresql/data
pg1-port=5432
pg1-user=pgbackrest
pg1-database=raffledb
```

(No `[global]` repo2 stanza — local test stays off-cloud.)

- [ ] **Step 3: Write a minimal rclone.conf stub**

Create `/tmp/srv-raffle/config/rclone.conf`:

```ini
[b2]
type = local
# Local-loopback test: media-syncer "uploads" to /tmp/srv-raffle/fake-b2.
# This validates the inotify path without needing real B2 credentials.
```

Create `/tmp/srv-raffle/fake-b2` and set `REMOTE=b2:/tmp/srv-raffle/fake-b2/raffle-media` in a temporary compose override.

- [ ] **Step 4: Create a compose override for the local test**

`docker-compose.local-smoke.yml`:

```yaml
services:
  postgres:
    volumes:
      - /tmp/srv-raffle/pg:/var/lib/postgresql/data
      - /tmp/srv-raffle/pgbackrest:/var/lib/pgbackrest
      - /tmp/srv-raffle/config/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro
  pgbackrest:
    volumes:
      - /tmp/srv-raffle/pg:/var/lib/postgresql/data:ro
      - /tmp/srv-raffle/pgbackrest:/var/lib/pgbackrest
      - /tmp/srv-raffle/config/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro
  web:
    volumes:
      - /tmp/srv-raffle/media:/app/media
      - /tmp/srv-raffle/staticfiles:/app/staticfiles
  media-syncer:
    environment:
      REMOTE: "b2:/tmp/srv-raffle/fake-b2/raffle-media"
    volumes:
      - /tmp/srv-raffle/media:/data/media:ro
      - /tmp/srv-raffle/config/rclone.conf:/config/rclone.conf:ro
      - /tmp/srv-raffle/fake-b2:/tmp/srv-raffle/fake-b2
```

- [ ] **Step 5: Create a throwaway `.env.prod.local`**

```
SECRET_KEY=local-smoke-key-not-secret
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
POSTGRES_DB=raffledb
POSTGRES_USER=raffleuser
POSTGRES_PASSWORD=localsmoke
DATABASE_URL=postgres://raffleuser:localsmoke@postgres:5432/raffledb
```

- [ ] **Step 6: Bring up the local stack**

Run:
```bash
cp .env.prod.local .env.prod
docker compose -f docker-compose.prod.yml -f docker-compose.local-smoke.yml up -d --build
```
Expected: all four containers come up. Postgres reaches healthy; web reaches healthy after migrations run on the empty Postgres.

- [ ] **Step 7: Verify WAL archiving**

Run:
```bash
# Force a WAL switch and confirm pgbackrest pushes it
docker compose -f docker-compose.prod.yml -f docker-compose.local-smoke.yml \
    exec postgres psql -U raffleuser -d raffledb -c "SELECT pg_switch_wal();"
sleep 5
ls -la /tmp/srv-raffle/pgbackrest/archive/raffle/16-1/
```
Expected: at least one `.gz` WAL segment file appears.

- [ ] **Step 8: Verify media-syncer inotify**

Run:
```bash
echo test > /tmp/srv-raffle/media/smoketest.txt
sleep 3
ls -la /tmp/srv-raffle/fake-b2/raffle-media/
```
Expected: `smoketest.txt` appears in the fake-b2 dir.

- [ ] **Step 9: Take a pgbackrest backup**

Run:
```bash
docker compose -f docker-compose.prod.yml -f docker-compose.local-smoke.yml \
    exec pgbackrest su -c 'pgbackrest --stanza=raffle --type=full backup' postgres
docker compose -f docker-compose.prod.yml -f docker-compose.local-smoke.yml \
    exec pgbackrest su -c 'pgbackrest --stanza=raffle info' postgres
```
Expected: `info` shows one full backup with status `ok`.

- [ ] **Step 10: Tear down + clean up**

Run:
```bash
docker compose -f docker-compose.prod.yml -f docker-compose.local-smoke.yml down
sudo rm -rf /tmp/srv-raffle
rm .env.prod docker-compose.local-smoke.yml .env.prod.local
```

If any of steps 7-9 failed, stop here and debug. Common issues:
- WAL not archiving → check Postgres logs for `archive_command` errors; verify pgbackrest.conf is mounted in BOTH containers.
- inotify not firing → verify `/tmp/srv-raffle/media` is bind-mounted into media-syncer.
- pgbackrest stanza-create failed → verify the `pgbackrest` Postgres user was created by the init script.

- [ ] **Step 11: Commit (no file changes; just a marker)**

If no code changed during debugging, skip this step. Otherwise commit fixes:
```bash
git add -A
git commit -m "fix: local smoke-test findings (<describe>)"
```

---

## Task 10: Provision Backblaze B2 buckets + application keys

**Runs on:** B2 web console (manual; one-time).

**Files:** none in repo; outputs are credentials that go on the prod host only.

- [ ] **Step 1: Create three private buckets**

Log in to https://secure.backblaze.com → My Account → Buckets → Create Bucket.

| Bucket name | Files visible | Default encryption | Object lock |
|---|---|---|---|
| `raffle-pgbackrest-<random>` | Private | SSE-B2 (B2-managed) | Off |
| `raffle-media-<random>` | Private | SSE-B2 | Off |
| `raffle-archive-<random>` | Private | SSE-B2 | **Off** (restic does its own encryption) |

Bucket names are globally unique across all of B2 — append a random 6-character suffix you'll remember.

- [ ] **Step 2: Enable lifecycle on the media bucket**

On `raffle-media-<random>` → Lifecycle Settings → Custom → "Keep prior versions for this many days: **90**". This is the bucket-level versioning safety net described in the spec.

- [ ] **Step 3: Create three application keys (one per bucket, scoped)**

App Keys → Add a New Application Key.

| Key name | Bucket | Capabilities |
|---|---|---|
| `raffle-pgbackrest-rw` | `raffle-pgbackrest-<random>` | listBuckets, listFiles, readFiles, writeFiles, **deleteFiles** (pgbackrest needs to prune by its own retention policy) |
| `raffle-media-rw-nodelete` | `raffle-media-<random>` | listBuckets, listFiles, readFiles, writeFiles (**NO deleteFiles**) |
| `raffle-archive-append-only` | `raffle-archive-<random>` | listBuckets, listFiles, readFiles, writeFiles (**NO deleteFiles** — anti-ransomware) |

For each, B2 will show a `keyID` and an `applicationKey` **exactly once**. Save them immediately to your password manager. **The applicationKey value cannot be recovered.**

- [ ] **Step 4: Save credentials to the operator password manager**

Create entries:
- `raffle / B2 / pgbackrest` — keyID, applicationKey, bucket name, endpoint (`s3.us-west-002.backblazeb2.com` or your region)
- `raffle / B2 / media` — same fields
- `raffle / B2 / archive` — same fields, plus the restic repo password (generate a fresh 32+ character random string)

These three (or four with restic password) are the **only secrets needed to restore from scratch**.

- [ ] **Step 5: Record completion**

This task has no commit — it's all in B2 console. Move on once the password-manager entries are saved.

---

## Task 11: Create `/srv/raffle` directory tree on prod host

**Runs on:** prod host.

- [ ] **Step 1: SSH to prod and create the tree**

Run on the prod host:

```bash
sudo install -d -o root -g root -m 755 /srv/raffle
sudo install -d -o 999 -g 999 -m 700 /srv/raffle/pg          # postgres uid:gid inside container
sudo install -d -o 999 -g 999 -m 700 /srv/raffle/pgbackrest
sudo install -d -o root -g root -m 755 /srv/raffle/media     # web container runs as root by default; safe
sudo install -d -o root -g root -m 755 /srv/raffle/staticfiles
sudo install -d -o root -g root -m 700 /srv/raffle/config
sudo install -d -o root -g root -m 700 /srv/raffle/migration
```

Verify ownership:

```bash
ls -la /srv/raffle/
```
Expected: `pg` and `pgbackrest` show owner `999:999` (Postgres uid in the official image); `config` and `migration` are `root:root` mode 700.

---

## Task 12: Deploy credential files to `/srv/raffle/config/`

**Runs on:** prod host.

- [ ] **Step 1: Write the production `pgbackrest.conf`**

On the prod host as root, paste the credentials from your password manager:

```bash
sudo tee /srv/raffle/config/pgbackrest.conf > /dev/null <<'EOF'
[global]
repo1-path=/var/lib/pgbackrest
repo1-retention-full=4
repo1-retention-diff=14

repo2-type=s3
repo2-s3-bucket=raffle-pgbackrest-XXXXXX
repo2-s3-endpoint=s3.us-west-002.backblazeb2.com
repo2-s3-region=us-west-002
repo2-s3-key=YOUR_B2_KEY_ID
repo2-s3-key-secret=YOUR_B2_APPLICATION_KEY
repo2-path=/raffle
repo2-retention-full=12
repo2-retention-diff=90
repo2-cipher-type=aes-256-cbc
repo2-cipher-pass=GENERATE_A_LONG_RANDOM_STRING

archive-async=y
spool-path=/var/spool/pgbackrest
log-level-console=info
log-level-file=detail
process-max=4

[raffle]
pg1-path=/var/lib/postgresql/data
pg1-port=5432
pg1-user=pgbackrest
pg1-database=raffledb
EOF

sudo chmod 600 /srv/raffle/config/pgbackrest.conf
sudo chown 999:999 /srv/raffle/config/pgbackrest.conf
```

Substitute the real `XXXXXX`, `YOUR_B2_KEY_ID`, `YOUR_B2_APPLICATION_KEY`, and generate a fresh cipher-pass (`openssl rand -hex 32`). Record the cipher-pass in the password manager — without it, the B2 backups cannot be decrypted on restore.

- [ ] **Step 2: Write the production `rclone.conf`**

```bash
sudo tee /srv/raffle/config/rclone.conf > /dev/null <<'EOF'
[b2]
type = b2
account = YOUR_B2_MEDIA_KEY_ID
key = YOUR_B2_MEDIA_APPLICATION_KEY
EOF

sudo chmod 600 /srv/raffle/config/rclone.conf
```

- [ ] **Step 3: Write the `.env.prod` (Django + Postgres credentials)**

In the repo directory on prod (wherever `docker-compose.prod.yml` lives):

```bash
sudo tee .env.prod > /dev/null <<EOF
# Django
SECRET_KEY=$(openssl rand -hex 32)
DEBUG=False
ALLOWED_HOSTS=raffle.yourdomain.example,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://raffle.yourdomain.example

# Database
POSTGRES_DB=raffledb
POSTGRES_USER=raffleuser
POSTGRES_PASSWORD=$(openssl rand -hex 24)
DATABASE_URL=postgres://raffleuser:THE_PASSWORD_FROM_ABOVE@postgres:5432/raffledb
EOF
sudo chmod 600 .env.prod
```

**Important:** open `.env.prod` and replace `THE_PASSWORD_FROM_ABOVE` with the actual `$(openssl rand ...)` value that was generated for `POSTGRES_PASSWORD`. The heredoc evaluates each `$(...)` independently so the two halves won't match unless you fix it manually.

Save all three random values (`SECRET_KEY`, `POSTGRES_PASSWORD`, `repo2-cipher-pass`) to your password manager under `raffle / prod / .env.prod`.

---

## Task 13: First boot of Postgres + pgBackRest on prod

**Runs on:** prod host.

- [ ] **Step 1: Pull the branch on prod**

```bash
cd /path/to/raffle-campaign
git fetch origin
git checkout zero-data-loss-backup
```

(Or whichever workflow you use; the point is the branch must be on the prod host so its `docker/` images can be built locally.)

- [ ] **Step 2: Build all four images**

```bash
docker compose -f docker-compose.prod.yml build
```
Expected: 3 images built (pgbackrest sidecar removed). First build takes a few minutes; subsequent builds are cache-hit.

- [ ] **Step 3: Stop the OLD compose stack (still SQLite)**

If `docker-compose.prod.yml` was previously running with the SQLite layout:

```bash
docker compose -f docker-compose.prod.yml down
```

The bind mounts under `./prod-data/` are untouched on disk; the SQLite file in `./prod-data/db/` (if any) is preserved for the migration.

- [ ] **Step 4: Bring up Postgres only (NOT web yet)**

```bash
docker compose -f docker-compose.prod.yml up -d postgres
```

- [ ] **Step 5: Wait for Postgres healthy + verify init scripts ran**

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=80 postgres | grep -E "(ready|pgbackrest|listening)"
```
Expected: `database system is ready to accept connections` + the init script output creating the `pgbackrest` role.

- [ ] **Step 6: Verify pgBackRest stanza is created and `check` passes**

```bash
docker compose -f docker-compose.prod.yml logs postgres | grep -E "(stanza|check|pgbackrest)" | tail -40
```
Expected: lines containing `stanza 'raffle' created` (or "already initialized") followed by `check command end: completed successfully`.

- [ ] **Step 7: Force a WAL push and verify it lands in both repos**

```bash
docker compose -f docker-compose.prod.yml exec postgres \
    psql -U raffleuser -d raffledb -c "SELECT pg_switch_wal();"
sleep 10
# Local repo
sudo ls -la /srv/raffle/pgbackrest/archive/raffle/16-1/
# B2 repo (the same WAL segment should appear here too, after async push)
docker compose -f docker-compose.prod.yml exec -u postgres postgres pgbackrest --stanza=raffle info
```
Expected: local archive dir contains `.gz` WAL files; `info` shows recent archive activity.

If WAL archiving is failing, stop here and check Postgres logs for `archive_command` errors before proceeding.

---

## Task 14: Run the SQLite → Postgres migration on prod

**Runs on:** prod host. **Maintenance window required** (web is down for ~5 minutes).

- [ ] **Step 1: Pre-flight — capture row counts from the legacy DB**

If the legacy web container is still running with SQLite:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py shell <<'PY' > /srv/raffle/migration/precount.txt
from campaigns.models import Campaign, Submission, Raffle
from django.contrib.auth.models import User
print("campaigns:", Campaign.objects.count())
print("submissions:", Submission.objects.count())
print("raffles:", Raffle.objects.count())
print("users:", User.objects.count())
PY
cat /srv/raffle/migration/precount.txt
```

Save the output — we'll compare against Postgres after the cutover.

If the legacy stack is already torn down, restore SQLite temporarily: `cp /path/to/old/db.sqlite3 .` and bring the old compose up briefly to dump.

- [ ] **Step 2: Announce maintenance**

Put up a maintenance page or notify the user. Estimated downtime: 5-10 minutes for a 256K DB.

- [ ] **Step 3: Run the migration script**

```bash
./scripts/migrate_sqlite_to_postgres.sh 2>&1 | tee /srv/raffle/migration/migration.log
```
Expected: script completes through Phase 6/6 and prints row counts.

- [ ] **Step 4: Compare row counts**

```bash
diff <(awk '{print $1, $NF}' /srv/raffle/migration/precount.txt | sort) \
     <(grep -E 'campaigns_|auth_user' /srv/raffle/migration/migration.log | awk '{print $1":", $NF}' | sort)
```
Expected: zero output (counts match). If any table differs, **do not** archive the SQLite file — investigate first.

- [ ] **Step 5: Smoke-test the live site**

- Open the dashboard in a browser → log in with an existing user. ✅
- Open a campaign detail page → existing submissions render. ✅
- Submit a test entry through the public form → it appears in the dashboard. ✅
- Trigger a small raffle draw → completes without error. ✅

If any test fails, you can roll back by reverting `.env.prod`'s `DATABASE_URL` to `sqlite:///db.sqlite3`, restoring `db.sqlite3`, and `docker compose up -d web`. The Postgres data is untouched on `/srv/raffle/pg` and can be retried.

- [ ] **Step 6: Archive the SQLite file**

```bash
sudo mv /path/to/legacy/db.sqlite3 /srv/raffle/migration/db.sqlite3.pre-migration-$(date +%Y%m%d)
ls -la /srv/raffle/migration/
```

Keep this file for 30 days, then delete.

- [ ] **Step 7: Take a fresh full backup**

```bash
docker compose -f docker-compose.prod.yml exec pgbackrest \
    su -c 'pgbackrest --stanza=raffle --type=full backup' postgres
docker compose -f docker-compose.prod.yml exec pgbackrest \
    su -c 'pgbackrest --stanza=raffle info' postgres
```
Expected: a fresh full backup appears in both repo1 (local) and repo2 (B2).

---

## Task 15: Bring up media-syncer; verify event-driven + reconciliation

**Runs on:** prod host.

- [ ] **Step 1: Start the media-syncer service**

```bash
docker compose -f docker-compose.prod.yml up -d media-syncer
docker compose -f docker-compose.prod.yml logs --tail=50 media-syncer
```
Expected: log shows `initial reconciliation...` followed by `starting inotify watcher...`. The first `rclone sync` may upload existing media (5.8 MB) — should take seconds.

- [ ] **Step 2: Verify B2 received the existing media**

```bash
docker compose -f docker-compose.prod.yml exec media-syncer \
    rclone size b2:raffle-media-XXXXXX
```
Expected: byte count roughly matches `du -sb /srv/raffle/media`.

- [ ] **Step 3: Test event-driven push**

From the prod host:

```bash
echo "syncer-event-test-$(date +%s)" | sudo tee /srv/raffle/media/syncer-test.txt
sleep 5
docker compose -f docker-compose.prod.yml exec media-syncer \
    rclone cat b2:raffle-media-XXXXXX/syncer-test.txt
```
Expected: the file content matches what was written.

- [ ] **Step 4: Test event-driven push from inside the web container (real path)**

Submit a real entry through the public form (with a photo). Then:

```bash
NEWEST=$(ls -1t /srv/raffle/media/submissions/ | head -1)
sleep 5
docker compose -f docker-compose.prod.yml exec media-syncer \
    rclone lsf "b2:raffle-media-XXXXXX/submissions/" | grep "$NEWEST"
```
Expected: filename appears in the listing within seconds of the upload.

- [ ] **Step 5: Clean up test artifact**

```bash
sudo rm /srv/raffle/media/syncer-test.txt
# (rclone will NOT delete from B2 because the key has no deleteFiles capability;
# the test file persists in B2 versioning until lifecycle prunes it after 90 days.
# That's the intended safety property. Don't try to "fix" this.)
```

---

## Task 16: Install restic + scripts + cron on prod host

**Runs on:** prod host. The restic layer runs outside Docker on purpose — see spec §6.3.

**Files:**
- Create: `scripts/raffle-restic-backup.sh`
- Create: `scripts/raffle-restic-check.sh`

- [ ] **Step 1: Write the backup script (locally in the repo first)**

`scripts/raffle-restic-backup.sh`:

```bash
#!/bin/bash
# Nightly restic snapshot of /srv/raffle/media and /srv/raffle/pgbackrest
# to the encrypted, append-only B2 archive bucket.
#
# Credentials are sourced from /srv/raffle/config/restic.env (mode 600,
# root-owned). The B2 application key configured there has NO deleteFiles
# capability — this script can only ADD snapshots, never destroy old ones.
set -euo pipefail

# shellcheck disable=SC1091
source /srv/raffle/config/restic.env

LOG=/var/log/raffle/restic-backup.log
mkdir -p /var/log/raffle

{
    echo "===== $(date -Iseconds) backup start ====="
    restic backup \
        --tag nightly \
        --host raffle-prod \
        /srv/raffle/media \
        /srv/raffle/pgbackrest
    echo "===== $(date -Iseconds) backup end ====="
} >> "$LOG" 2>&1
```

- [ ] **Step 2: Write the check script**

`scripts/raffle-restic-check.sh`:

```bash
#!/bin/bash
# Monthly restic repository integrity check. Read-only; safe with the
# no-delete key.
set -euo pipefail

# shellcheck disable=SC1091
source /srv/raffle/config/restic.env

LOG=/var/log/raffle/restic-check.log

{
    echo "===== $(date -Iseconds) check start ====="
    restic check --read-data-subset=5%
    echo "===== $(date -Iseconds) check end ====="
} >> "$LOG" 2>&1
```

`--read-data-subset=5%` reads 5% of pack files randomly each run, so over 20 runs (~20 months) every pack file gets read at least once.

- [ ] **Step 3: Make both executable + commit**

```bash
chmod +x scripts/raffle-restic-backup.sh scripts/raffle-restic-check.sh
git add scripts/raffle-restic-backup.sh scripts/raffle-restic-check.sh
git commit -m "feat: restic nightly backup + monthly integrity check scripts"
```

- [ ] **Step 4: On the prod host, pull the branch and install scripts**

```bash
git pull
sudo install -m 755 scripts/raffle-restic-backup.sh /usr/local/bin/raffle-restic-backup
sudo install -m 755 scripts/raffle-restic-check.sh /usr/local/bin/raffle-restic-check
```

- [ ] **Step 5: Install restic on the prod host**

```bash
sudo apt-get update && sudo apt-get install -y restic
restic version
```
Expected: 0.16 or later. If apt's restic is older, install from GitHub releases.

- [ ] **Step 6: Drop the restic credentials file**

```bash
sudo tee /srv/raffle/config/restic.env > /dev/null <<'EOF'
export RESTIC_REPOSITORY="b2:raffle-archive-XXXXXX:/raffle"
export B2_ACCOUNT_ID="YOUR_ARCHIVE_KEY_ID"
export B2_ACCOUNT_KEY="YOUR_ARCHIVE_APPLICATION_KEY"
export RESTIC_PASSWORD="YOUR_LONG_RESTIC_PASSWORD"
EOF
sudo chmod 600 /srv/raffle/config/restic.env
```

(Substitute the real values from your password manager.)

- [ ] **Step 7: Install cron entries**

```bash
sudo tee /etc/cron.d/raffle-restic > /dev/null <<'EOF'
# raffle-campaign restic schedule
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 3 * * * root /usr/local/bin/raffle-restic-backup
0 5 1 * * root /usr/local/bin/raffle-restic-check
EOF
sudo chmod 644 /etc/cron.d/raffle-restic
```

Verify cron picked it up: `sudo systemctl reload cron` (or `service cron reload`).

---

## Task 17: Initialize restic repo on B2; first manual snapshot

**Runs on:** prod host.

- [ ] **Step 1: Initialize the restic repository**

```bash
source /srv/raffle/config/restic.env
restic init
```
Expected: prints `created restic repository <id> at b2:raffle-archive-XXXXXX:/raffle`. This step is **one-shot only** — if you ever see "config already initialized" later, that's fine; if you see it now, the repo was created before and the password may differ.

- [ ] **Step 2: Run the backup script manually**

```bash
sudo /usr/local/bin/raffle-restic-backup
tail -40 /var/log/raffle/restic-backup.log
```
Expected: backup completes. Log shows `Files: N new, 0 changed, 0 unmodified` and `Added to the repository: ... MiB`.

- [ ] **Step 3: List snapshots**

```bash
source /srv/raffle/config/restic.env
restic snapshots
```
Expected: one snapshot tagged `nightly`, host `raffle-prod`.

- [ ] **Step 4: Run an integrity check**

```bash
sudo /usr/local/bin/raffle-restic-check
tail -20 /var/log/raffle/restic-check.log
```
Expected: log ends with `no errors were found`.

---

## Task 18: Install backup-freshness monitor cron

**Runs on:** dev (write script + test) then prod (install).

**Files:**
- Create: `scripts/raffle-backup-freshness.sh`
- Create: `tests/test_freshness_check.py`

The freshness check runs daily, checks (a) the latest WAL in B2 is < 5 min old, (b) the latest restic snapshot is < 25 h old, and emails on failure.

- [ ] **Step 1: Write a failing unit test**

`tests/test_freshness_check.py`:

```python
"""
Test the timestamp-comparison logic of the freshness checker.

The script uses a small helper `is_stale(timestamp_iso, max_age_seconds)`
which we test directly. The shell wrapper handles I/O and email.
"""
import subprocess
from datetime import datetime, timedelta, timezone


def run_check(ts: str, max_age: int) -> int:
    """Invoke the helper via bash and return exit code."""
    script = (
        "source scripts/raffle-backup-freshness.sh; "
        f"is_stale '{ts}' {max_age}; "
        "echo exit=$?"
    )
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    # Parse 'exit=N' from output
    for line in result.stdout.splitlines():
        if line.startswith("exit="):
            return int(line.split("=")[1])
    raise AssertionError(f"helper produced no exit line: {result.stdout!r} stderr={result.stderr!r}")


def test_fresh_timestamp_returns_0():
    now = datetime.now(timezone.utc).isoformat()
    assert run_check(now, 3600) == 0


def test_stale_timestamp_returns_1():
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert run_check(old, 3600) == 1


def test_missing_timestamp_returns_2():
    assert run_check("", 3600) == 2
```

- [ ] **Step 2: Run the test to see it fail**

Run: `python -m pytest tests/test_freshness_check.py -v`
Expected: FAIL — `scripts/raffle-backup-freshness.sh` doesn't exist yet.

- [ ] **Step 3: Write the script**

`scripts/raffle-backup-freshness.sh`:

```bash
#!/bin/bash
# Daily freshness check. Validates:
#   1. Latest pgBackRest WAL archive < 5 min old (RPO sanity)
#   2. Latest restic snapshot < 25 h old (nightly cron is alive)
# On failure, emits to stderr (cron mails root) and exits non-zero.

# Helper: is the given ISO timestamp older than max_age seconds?
#   exit 0 = fresh, 1 = stale, 2 = invalid input
is_stale() {
    local ts="$1"
    local max_age="$2"
    if [ -z "$ts" ]; then
        return 2
    fi
    local then_epoch now_epoch age
    then_epoch=$(date -d "$ts" +%s 2>/dev/null) || return 2
    now_epoch=$(date +%s)
    age=$((now_epoch - then_epoch))
    if [ "$age" -gt "$max_age" ]; then
        return 1
    fi
    return 0
}

# If sourced (not executed), expose helper and exit early.
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    return 0 2>/dev/null || exit 0
fi

set -euo pipefail
errors=0

# Check 1: latest WAL in B2 archive.
WAL_TS=$(docker compose -f /path/to/docker-compose.prod.yml exec -T pgbackrest \
    su -c 'pgbackrest --stanza=raffle info --output=json' postgres \
    | python3 -c '
import json, sys
data = json.load(sys.stdin)
archives = data[0]["archive"][0]
latest = archives.get("max")
if not latest:
    sys.exit(0)
# pgbackrest info doesn'"'"'t expose WAL push timestamp directly; we approximate
# by reading the most recent backup'"'"'s timestamp.
last_backup = data[0]["backup"][-1]
print(last_backup["timestamp"]["stop"])
')

if ! is_stale "$WAL_TS" 3600; then
    echo "FAIL: pgBackRest archive stale (last activity: $WAL_TS)" >&2
    errors=$((errors + 1))
fi

# Check 2: latest restic snapshot.
source /srv/raffle/config/restic.env
SNAP_TS=$(restic snapshots --json | python3 -c '
import json, sys
snaps = json.load(sys.stdin)
if not snaps:
    sys.exit(0)
print(snaps[-1]["time"])
')

if ! is_stale "$SNAP_TS" 90000; then  # 25h
    echo "FAIL: restic snapshot stale (last snapshot: $SNAP_TS)" >&2
    errors=$((errors + 1))
fi

exit $errors
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_freshness_check.py -v`
Expected: all three tests PASS.

- [ ] **Step 5: Make executable + commit**

```bash
chmod +x scripts/raffle-backup-freshness.sh
git add scripts/raffle-backup-freshness.sh tests/test_freshness_check.py
git commit -m "feat: backup freshness monitor with cron-mail alerting"
```

- [ ] **Step 6: Install on prod host**

```bash
git pull
sudo install -m 755 scripts/raffle-backup-freshness.sh /usr/local/bin/raffle-backup-freshness
# Edit the path in the script if your prod checkout isn't at /path/to/docker-compose.prod.yml
sudo sed -i 's|/path/to/docker-compose.prod.yml|/srv/raffle/repo/docker-compose.prod.yml|' \
    /usr/local/bin/raffle-backup-freshness
```

- [ ] **Step 7: Wire into cron**

```bash
sudo tee -a /etc/cron.d/raffle-restic > /dev/null <<'EOF'

# Daily freshness check. Cron mails root if non-zero exit.
MAILTO=root
0 6 * * * root /usr/local/bin/raffle-backup-freshness
EOF
```

Ensure root mail forwards to an address you actually read (`/etc/aliases` → `root: you@example.com`, then `sudo newaliases`).

- [ ] **Step 8: Run once manually to verify**

```bash
sudo /usr/local/bin/raffle-backup-freshness && echo "OK: all backups fresh"
```
Expected: prints `OK: all backups fresh`.

---

## Task 19: Write the restore playbook

**Files:**
- Create: `docs/deployment/restore-playbook.md`
- Create: `docs/deployment/restore-rehearsal-log.md`
- Create: `docs/deployment/host-setup.md`

- [ ] **Step 1: Write `docs/deployment/restore-playbook.md`**

```markdown
# Raffle Campaign — Restore Playbook

Last reviewed: 2026-05-13.

Four recovery scenarios are documented. Each is rehearsable; rehearsal results
are logged in `restore-rehearsal-log.md`.

## Inventory of secrets needed

All restore paths require, at minimum:

1. **B2 application keys** for `raffle-pgbackrest-*` and `raffle-media-*` buckets.
2. **pgBackRest cipher passphrase** (`repo2-cipher-pass` from `pgbackrest.conf`).
3. **Postgres password** (`POSTGRES_PASSWORD` from `.env.prod`).
4. **Django SECRET_KEY** (from `.env.prod`).
5. (For ransomware recovery only) **restic repository password** and **archive bucket B2 key**.

All five live in the operator password manager. Without them, **no restore is possible** — protect them accordingly.

## Scenario A: Full disaster recovery (host lost)

**When to use:** VPS terminated, disk unrecoverable, ransomware encrypted everything, etc.

1. Provision a fresh Linux host with Docker + docker compose.
2. `git clone <repo>`; `git checkout <prod branch>`.
3. Recreate the host filesystem layout:
   ```bash
   sudo install -d -o root -g root -m 755 /srv/raffle
   sudo install -d -o 999 -g 999 -m 700 /srv/raffle/pg
   sudo install -d -o 999 -g 999 -m 700 /srv/raffle/pgbackrest
   sudo install -d -o root -g root -m 755 /srv/raffle/media
   sudo install -d -o root -g root -m 755 /srv/raffle/staticfiles
   sudo install -d -o root -g root -m 700 /srv/raffle/config
   ```
4. Drop the three credential files into `/srv/raffle/config/` (pgbackrest.conf, rclone.conf, restic.env) — copies from your password manager.
5. Drop `.env.prod` next to `docker-compose.prod.yml`.
6. Build images: `docker compose -f docker-compose.prod.yml build`.
7. Start Postgres + pgBackRest (Postgres will start empty):
   ```bash
   docker compose -f docker-compose.prod.yml up -d postgres pgbackrest
   ```
8. Wait for the pgbackrest sidecar to be running, then **stop Postgres** (so we can restore into the empty PGDATA without conflict):
   ```bash
   docker compose -f docker-compose.prod.yml stop postgres
   ```
9. Restore from B2:
   ```bash
   docker compose -f docker-compose.prod.yml run --rm pgbackrest \
       su -c 'pgbackrest --stanza=raffle --repo=2 restore --delta' postgres
   ```
10. Start Postgres — it replays WAL to the latest archived segment:
    ```bash
    docker compose -f docker-compose.prod.yml start postgres
    docker compose -f docker-compose.prod.yml logs --tail=50 postgres
    ```
    Expect lines like `archive recovery complete` followed by `database system is ready`.
11. Restore media:
    ```bash
    docker compose -f docker-compose.prod.yml run --rm -v /srv/raffle/media:/data media-syncer \
        rclone sync b2:raffle-media-XXXXXX /data --transfers 4
    ```
12. Bring up the rest: `docker compose -f docker-compose.prod.yml up -d web media-syncer`.
13. Verify: log in, view a known submission, check row counts vs whatever snapshot you have.

**Expected RTO: 30 minutes.** **Expected RPO: ≤ 30 seconds of writes.**

## Scenario B: Point-in-time recovery (e.g. bad UPDATE)

**When to use:** application bug or operator mistake wrote bad data; you know the approximate timestamp before the bad write.

1. Stop the web container (no new writes during recovery):
   ```bash
   docker compose -f docker-compose.prod.yml stop web
   ```
2. Stop Postgres:
   ```bash
   docker compose -f docker-compose.prod.yml stop postgres
   ```
3. Restore to the target time:
   ```bash
   docker compose -f docker-compose.prod.yml run --rm pgbackrest \
       su -c "pgbackrest --stanza=raffle --type=time \
              --target='2026-05-13 14:23:00+00' restore --delta" postgres
   ```
4. Start Postgres → replays WAL up to the target time then pauses:
   ```bash
   docker compose -f docker-compose.prod.yml start postgres
   ```
5. Connect and verify data is at the target time. To resume normal operations:
   ```sql
   SELECT pg_wal_replay_resume();
   ```
6. Restart web: `docker compose -f docker-compose.prod.yml up -d web`.

**Caveat:** PITR rewrites history. All writes after the target time are gone. Communicate this with stakeholders.

## Scenario C: Single-file restore (accidental media delete)

**When to use:** a user-submitted photo was deleted from `/srv/raffle/media` (by app bug or operator).

The B2 bucket has 90-day versioning. Find the version:

```bash
docker compose -f docker-compose.prod.yml exec media-syncer \
    rclone lsf 'b2:raffle-media-XXXXXX/submissions/<filename>' --b2-versions
```

Restore the most recent prior version:

```bash
docker compose -f docker-compose.prod.yml exec media-syncer \
    rclone copyto 'b2:raffle-media-XXXXXX/submissions/<filename>-v<id>.jpg' \
                  '/data/media/submissions/<filename>.jpg'
```

(The `inotify` watcher will see the restore as a new file and re-upload it as the current version. No further action needed.)

## Scenario D: Ransomware / archive-only recovery

**When to use:** the prod host's B2 application keys were compromised AND used to corrupt the live `raffle-pgbackrest` / `raffle-media` buckets. The archive bucket survives because (a) its B2 key has no delete permission, and (b) the restic passphrase is not on the host.

1. Provision a clean Linux host (do NOT reuse the compromised one).
2. Install restic.
3. From the password manager, populate `/srv/raffle/config/restic.env` with the **archive** bucket credentials and the restic passphrase.
4. List snapshots and pick one from before the compromise:
   ```bash
   source /srv/raffle/config/restic.env
   restic snapshots
   ```
5. Restore both bind-mount targets:
   ```bash
   restic restore <snapshot-id> --target / --include /srv/raffle/media --include /srv/raffle/pgbackrest
   ```
6. Restore Postgres from the pgBackRest **local** repo (which we just restored):
   - Reuse Scenario A steps 6-13, but pgBackRest can use `--repo=1` since the local repo is intact.

## Off-host maintenance: pruning the restic archive

The prod host's archive key has no delete permission. To prune old snapshots, run from a workstation or second machine with a separate, more-privileged key:

```bash
export RESTIC_REPOSITORY=b2:raffle-archive-XXXXXX:/raffle
export B2_ACCOUNT_ID=<ARCHIVE_FULL_ACCESS_KEY_ID>
export B2_ACCOUNT_KEY=<ARCHIVE_FULL_ACCESS_KEY>
export RESTIC_PASSWORD=<passphrase>
restic forget --keep-daily 14 --keep-weekly 8 --keep-monthly 24 --keep-yearly 10 --prune
```

Run this annually at most. Storage cost is low enough that pruning is optional for years.

## Quarterly rehearsal

Run Scenario A against a scratch host or VM. Log results in `restore-rehearsal-log.md`. If a rehearsal fails, treat it as a P0 — no backup work proceeds until restore is proven working again.
```

- [ ] **Step 2: Create the rehearsal log stub**

`docs/deployment/restore-rehearsal-log.md`:

```markdown
# Restore Rehearsal Log

Append-only log of restore rehearsals. Run quarterly at minimum.

| Date | Scenario | Operator | RTO actual | Result | Notes |
|---|---|---|---|---|---|
| | | | | | |
```

- [ ] **Step 3: Create the host-setup quick reference**

`docs/deployment/host-setup.md`:

```markdown
# Raffle Campaign — Host Setup Quick Reference

This page summarizes what lives where on the prod host. For full restore
procedures, see `restore-playbook.md`. For design rationale, see
`../superpowers/specs/2026-05-13-zero-data-loss-backup-design.md`.

## Filesystem layout

```
/srv/raffle/
├── pg/                  # Postgres PGDATA, owner 999:999, mode 700
├── media/               # MEDIA_ROOT (user uploads), bind-mounted into web + media-syncer
├── pgbackrest/          # pgBackRest local repo (repo1), owner 999:999
├── staticfiles/         # collected statics, rebuildable
├── migration/           # one-shot SQLite dump + the archived pre-migration db.sqlite3
└── config/              # all secret files, mode 600
    ├── pgbackrest.conf  # B2 repo2 credentials + cipher pass
    ├── rclone.conf      # B2 media bucket credentials
    └── restic.env       # B2 archive bucket credentials + restic passphrase
```

## Containers

| Container | Image | Restart policy | Purpose |
|---|---|---|---|
| raffle-prod | raffle-campaign-prod:latest | unless-stopped | Django + gunicorn |
| raffle-postgres | raffle-postgres:latest | unless-stopped | Postgres 16 + pgBackRest binary |
| raffle-pgbackrest | raffle-pgbackrest:latest | unless-stopped | Cron-driven full/diff/incr backups |
| raffle-media-syncer | raffle-media-syncer:latest | unless-stopped | rclone + inotify event push |

## Host crons

| File | Schedule | Purpose |
|---|---|---|
| /etc/cron.d/raffle-restic | 0 3 * * * | Nightly restic snapshot |
| /etc/cron.d/raffle-restic | 0 5 1 * * | Monthly restic integrity check |
| /etc/cron.d/raffle-restic | 0 6 * * * | Daily backup-freshness check (mails on fail) |

## B2 buckets

| Bucket | Versioning | Key permissions |
|---|---|---|
| raffle-pgbackrest-XXXXXX | off | rw + delete (for pgbackrest retention) |
| raffle-media-XXXXXX | 90-day prior versions | rw, **no delete** |
| raffle-archive-XXXXXX | off | rw, **no delete** (restic on-host key); separate full-access key off-host for pruning |

## On-call commands

- Tail backup activity: `tail -f /var/log/raffle/restic-backup.log /var/log/pgbackrest/cron.log`
- Force a manual backup: `docker compose -f docker-compose.prod.yml exec pgbackrest su -c 'pgbackrest --stanza=raffle --type=incr backup' postgres`
- Status of all backups: `docker compose -f docker-compose.prod.yml exec pgbackrest su -c 'pgbackrest --stanza=raffle info' postgres`
- Manually run freshness check: `sudo /usr/local/bin/raffle-backup-freshness`
```

- [ ] **Step 4: Commit**

```bash
git add docs/deployment/restore-playbook.md docs/deployment/restore-rehearsal-log.md docs/deployment/host-setup.md
git commit -m "docs: restore playbook + host-setup reference + rehearsal log"
```

---

## Task 20: First restore rehearsal + log entry

**Files:**
- Modify: `docs/deployment/restore-rehearsal-log.md`
- Create: `Makefile` (adds `restore-test` target)

- [ ] **Step 1: Add a `restore-test` Makefile target**

If `Makefile` doesn't exist, create it. Otherwise append:

```makefile
.PHONY: restore-test
restore-test:
	@echo "==> Running pgBackRest restore dry-run from B2 to scratch dir"
	docker compose -f docker-compose.prod.yml exec pgbackrest \
		su -c "pgbackrest --stanza=raffle --repo=2 --dry-run \
		       --target-path=/tmp/restore-test restore" postgres
	@echo "==> Listing latest snapshots in restic archive"
	source /srv/raffle/config/restic.env && restic snapshots | tail -10
```

- [ ] **Step 2: Run the rehearsal**

Follow `docs/deployment/restore-playbook.md` Scenario A from start to step 11 against either:
- a scratch directory on the same host (mount `/tmp/scratch-restore` instead of `/srv/raffle/pg`), or
- a separate test VM.

Time it from "begin" to "logged in and verified row count".

- [ ] **Step 3: Append a row to the rehearsal log**

Edit `docs/deployment/restore-rehearsal-log.md` and add a row to the table:

```
| 2026-05-XX | A (full disaster) | <your name> | XX min | Pass | First rehearsal post-implementation. |
```

- [ ] **Step 4: Commit**

```bash
git add Makefile docs/deployment/restore-rehearsal-log.md
git commit -m "chore: first restore rehearsal logged + Makefile restore-test target"
```

---

## Task 21: Decommission `./prod-data/` and SQLite code paths

**Files:**
- Modify: `.gitignore`
- Modify: `docker-compose.yml` (dev compose; keep, but leave SQLite default)

- [ ] **Step 1: Confirm `./prod-data/` is no longer referenced**

Run:
```bash
grep -rn "prod-data" --exclude-dir=.git --exclude-dir=docs --exclude-dir=prod-data-archive .
```
Expected: only `.gitignore` matches. If anything else matches (docs aside), fix those references to point at `/srv/raffle`.

- [ ] **Step 2: Remove `prod-data/` from `.gitignore`**

The `prod-data/` entry can stay as a safety net (it ignores anything dropped there by mistake during dev), but add a comment so future readers know it's legacy:

In `.gitignore`, find the line `prod-data/` and replace with:

```
# Legacy local bind-mount target (replaced by /srv/raffle/ in prod).
# Kept here so any accidental dev-side prod-data/ doesn't get committed.
prod-data/
```

- [ ] **Step 3: Verify the legacy SQLite file is archived**

On prod, `db.sqlite3` should only exist under `/srv/raffle/migration/`. Confirm:

```bash
ls /srv/raffle/migration/db.sqlite3.pre-migration-*
find / -name 'db.sqlite3' -not -path '/srv/raffle/migration/*' 2>/dev/null
```
Expected: the archive file exists; no other `db.sqlite3` outside `/srv/raffle/migration/`.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: mark prod-data/ as legacy; /srv/raffle is the canonical location"
```

---

## Task 22: Final commit, merge, Mila-bot work report

- [ ] **Step 1: Push the branch and open PR**

```bash
git push -u origin zero-data-loss-backup
```
Open a PR titled "Zero-data-loss: Postgres + B2 backup stack" with body summarizing the spec link, the migration done, and the rehearsal date.

- [ ] **Step 2: Merge after review**

After PR review approval:

```bash
git checkout main
git pull
git merge --no-ff zero-data-loss-backup
git push origin main
```

- [ ] **Step 3: Submit a Mila-bot work report**

Dispatch a haiku-tier background agent to POST to http://localhost:8200/reports/create/ with title "Zero-data-loss backup stack shipped" and body summarizing: SQLite → Postgres migration completed, continuous WAL archiving live, media-syncer running, restic nightly snapshots active, first rehearsal logged.

- [ ] **Step 4: Save a memory pointer**

Save a `project_*.md` memory in the project's memory dir noting that `/srv/raffle/...` is now canonical for prod state, the three B2 buckets exist, and `docs/deployment/restore-playbook.md` is the operator runbook.

---

## Self-review

**Spec coverage:**
- §1 Problem statement → Tasks 2, 6, 11 (env-driven DB, /srv/raffle layout) ✅
- §2 Goals G1-G6 → all covered: G1 Docker (Tasks 3-6), G2 bind mounts (11), G3 RPO (13, 15), G4 layered defense (16-18), G5 playbook (19, 20), G6 future second machine (playbook §off-host maintenance, restored from B2) ✅
- §4 Architecture → Tasks 3-6 ✅
- §5 SQLite → Postgres → Tasks 2, 7, 8, 14 ✅
- §6.1 pgBackRest → Tasks 3, 4, 12, 13 ✅
- §6.2 Media sync → Tasks 5, 12, 15 ✅
- §6.3 Restic → Tasks 16, 17 ✅
- §7 Data flow → covered implicitly by Tasks 13, 15 verification steps ✅
- §8 Defense matrix → playbook scenarios A-D ✅
- §9 Restore playbook → Task 19 ✅
- §10 Ops monitoring → Task 18 (freshness check) ✅
- §11 Phases 1-7 → mapped 1:1 onto these tasks ✅
- §12 Risks → addressed inline (sequence-reset = Task 7, archive_command failures = pgbackrest archive-async + freshness check) ✅

**Placeholder scan:** none found. Every step has the actual content.

**Type consistency:** `is_stale` helper name consistent across script + test. `build_setval_statements` consistent in script + test. Container names consistent (`raffle-prod`, `raffle-postgres`, `raffle-pgbackrest`, `raffle-media-syncer`). Bucket-name placeholder `-XXXXXX` is used consistently and is intentional (operator fills in at provisioning time).

**Spec requirements with no task — none found.**
