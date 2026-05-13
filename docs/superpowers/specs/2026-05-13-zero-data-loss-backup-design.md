# Zero-Data-Loss Backup Strategy — Design Spec

**Date:** 2026-05-13
**Status:** Approved (design phase complete; implementation plan to follow)
**Author:** brainstorm session with user

---

## 1. Problem statement

The raffle-campaign Django app currently runs in Docker on a Plesk VPS. Two problems with the present setup violate the user's data-loss tolerance:

1. **The SQLite database is not actually persisted outside the container.** `settings.py` puts `db.sqlite3` at `BASE_DIR / 'db.sqlite3'` (repo root), but `docker-compose.prod.yml` bind-mounts `./prod-data/db:/app/db`. The mount covers an empty directory, not the live DB file. A `docker compose down -v` or container rebuild can lose the database.
2. **There is no off-host replication.** Both the DB and user-submitted images (`media/`) live on a single VPS disk. Disk loss, VPS termination, accidental delete, or ransomware = total data loss.

The user's stated goal: *"the database and the images submitted by users are 1) backed up constantly, 2) live outside the container to make sure we have 0 data loss possible"* — with a comprehensive strategy for "absolutely no data loss possible."

## 2. Goals

- **G1.** App continues to run in Docker; no change to deployment topology (single Plesk VPS, behind Plesk's Nginx proxy).
- **G2.** All persistent state lives on host bind mounts outside any container.
- **G3.** Continuous off-host replication to Backblaze B2:
  - Database RPO ≤ 30 s.
  - User-uploaded media RPO ≤ 10 s for new files; ≤ 10 min for any drift.
- **G4.** Multiple defense layers against threats beyond hardware failure: accidental delete, logic-bug corruption, ransomware.
- **G5.** Restore playbook is written, version-controlled, and rehearsable.
- **G6.** Forward-compatible with a future second off-host mirror (pull from B2) without changing the prod host.

## 3. Non-goals

- High-availability / hot failover. A single VPS with strong backups is acceptable for current scale.
- Multi-region active-active.
- Zero-downtime migrations during the SQLite → Postgres cutover. A short maintenance window is acceptable.

## 4. Architecture

### 4.1 Topology

```
                          Plesk VPS
   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │   /srv/raffle/         ← single off-container source of truth│
   │     pg/                ← Postgres data dir (bind mount)     │
   │     media/             ← user uploads (bind mount)          │
   │     pgbackrest/        ← local backup repo (bind mount)     │
   │     staticfiles/       ← collected statics (bind mount)     │
   │                                                             │
   │   docker compose services:                                  │
   │     web         (Django + gunicorn)                          │
   │     postgres    (Postgres 16 + pgBackRest cron inside)       │
   │     media-syncer (rclone + inotifywait)                      │
   │                                                             │
   │   Host cron (outside Docker):                                │
   │     nightly restic backup → second B2 bucket                 │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
                                │
                                │ HTTPS over the public internet
                                ▼
                  ┌─────────────────────────────────────┐
                  │            Backblaze B2             │
                  │   raffle-pgbackrest   (PITR repo)   │
                  │   raffle-media        (versioned)   │
                  │   raffle-archive      (restic, enc) │
                  └─────────────────────────────────────┘
                                │
                                │ (future) pull from B2
                                ▼
                       ┌──────────────────┐
                       │  Second machine  │ (not yet set up)
                       └──────────────────┘
```

### 4.2 Host filesystem layout

```
/srv/raffle/
├── pg/                  # Postgres PGDATA (chmod 700, owner = postgres uid in container)
├── media/               # MEDIA_ROOT — user submissions, campaign logos
├── pgbackrest/          # pgBackRest local repository (repo1)
│   ├── archive/
│   └── backup/
├── staticfiles/         # collected static (rebuildable; backed up opportunistically)
└── config/
    ├── pgbackrest.conf
    ├── rclone.conf      # B2 credentials for media-syncer (chmod 600)
    └── restic.env       # B2 credentials + repo password for archive (chmod 600)
```

`/srv` is the Linux convention for served data and is independent of any git checkout, so wiping the repo never wipes the data.

### 4.3 Services and responsibilities

| Service | Type | Responsibility |
|---|---|---|
| `web` | container | Django + gunicorn, reads/writes via Postgres and `/srv/raffle/media`. |
| `postgres` | container | Postgres 16. Configured with `archive_mode=on` and `archive_command` invoking pgBackRest. Also runs a cron daemon (inside the container) for `full` (weekly), `diff` (daily), `incr` (hourly) backups. Two repos: local (`/srv/raffle/pgbackrest`) and B2 (`raffle-pgbackrest`). |
| `media-syncer` | sidecar container | Two loops: (1) `inotifywait` on `/srv/raffle/media` → `rclone copyto` to B2 on every fs event; (2) every 10 min, `rclone sync /srv/raffle/media b2:raffle-media` for reconciliation. |
| host cron | OS-level | Nightly `restic backup /srv/raffle/media /srv/raffle/pgbackrest` → `b2:raffle-archive`, encrypted with an operator-held passphrase. |

## 5. Database: SQLite → Postgres migration

### 5.1 Why migrate
The user chose Postgres for first-class continuous WAL archiving (pgBackRest is the industry-standard PITR tool for Postgres). SQLite + Litestream was the alternative; both work, but Postgres + pgBackRest aligns better with operational expectations.

The current SQLite-not-persisted bug is incidentally resolved by the migration since the migration cutover establishes a fresh, correctly-persisted Postgres data directory at `/srv/raffle/pg`.

### 5.2 Migration plan

1. Bring up Postgres container alongside the existing SQLite app (no traffic yet).
2. From the running app: `python manage.py dumpdata --natural-foreign --natural-primary --exclude=contenttypes --exclude=auth.permission --exclude=sessions > /srv/raffle/migration/sqlite_dump.json`
3. Update `settings.py` to read `DATABASES` from `DATABASE_URL` env var.
4. Run `python manage.py migrate` against empty Postgres → creates schema.
5. Run `python manage.py loaddata /srv/raffle/migration/sqlite_dump.json` → restores rows.
6. Sanity check: row counts for `campaigns.Campaign`, `campaigns.Submission`, `auth.User`, `campaigns.Raffle` all match the SQLite side.
7. Re-sync Postgres sequences (`SELECT setval(...)` for every `id` column) — `loaddata` does NOT advance them and the next insert will collide otherwise.
8. Stop SQLite-backed `web`, start Postgres-backed `web`. Smoke test: log in, view a campaign, submit a test entry.
9. Archive `db.sqlite3` and the dump file under `/srv/raffle/migration/` for 30 days, then delete.

### 5.3 Django settings changes

- Add `psycopg[binary]>=3.1` to `requirements.txt`.
- Add `dj-database-url>=2` to `requirements.txt`.
- Replace `DATABASES` block in `settings.py` with `DATABASES = {'default': dj_database_url.config(default='sqlite:///' + str(BASE_DIR / 'db.sqlite3'))}` (SQLite fallback keeps dev workflow working without Postgres).
- Add `DATABASE_URL=postgres://raffle:<secret>@postgres:5432/raffle` to `.env.prod`.
- `MEDIA_ROOT` stays at `BASE_DIR / 'media'`; the bind mount supplies the host path. (No code change needed since the container path `/app/media` is unchanged.)

## 6. Backup mechanisms (concrete configuration)

### 6.1 Postgres + pgBackRest

**Postgres config** (mounted via configmap or set via `POSTGRES_INITDB_ARGS` / `command:` overrides in compose):

```
archive_mode = on
archive_command = 'pgbackrest --stanza=raffle archive-push %p'
archive_timeout = 60          # force a WAL segment switch at least every 60 s
wal_level = replica
max_wal_senders = 3
```

**pgBackRest stanza config** (`/srv/raffle/config/pgbackrest.conf`):

```ini
[global]
repo1-path=/var/lib/pgbackrest
repo1-retention-full=4
repo1-retention-diff=14

repo2-type=s3
repo2-s3-bucket=raffle-pgbackrest
repo2-s3-endpoint=s3.us-west-002.backblazeb2.com
repo2-s3-region=us-west-002
repo2-s3-key=<B2_KEY_ID>
repo2-s3-key-secret=<B2_APPLICATION_KEY>
repo2-path=/raffle
repo2-retention-full=12       # ~3 months of weekly fulls
repo2-retention-diff=90
repo2-cipher-type=aes-256-cbc
repo2-cipher-pass=<long random string>

archive-async=y
spool-path=/var/spool/pgbackrest

[raffle]
pg1-path=/var/lib/postgresql/data
pg1-port=5432
pg1-user=postgres
```

**pgBackRest cron schedule** (cron daemon inside the Postgres container):

| Cron | Command | Frequency |
|---|---|---|
| `0 2 * * 0` | `pgbackrest --stanza=raffle --type=full backup` | Weekly full |
| `0 2 * * 1-6` | `pgbackrest --stanza=raffle --type=diff backup` | Daily diff |
| `0 * * * *` | `pgbackrest --stanza=raffle --type=incr backup` | Hourly incr |

**Guarantees:**
- Every committed transaction generates WAL → pushed to both repos within seconds.
- `archive_timeout=60` ensures WAL segments rotate even on idle DBs, so we never lose more than ~60 s of writes regardless of WAL volume.
- PITR available to any second in the last 90 days from repo2 (B2).

### 6.2 Media: rclone + inotify

**media-syncer container** runs a small entrypoint script:

```bash
#!/bin/sh
# loop 1: periodic full sync (catches missed events, large renames)
( while true; do
    rclone sync /srv/raffle/media b2:raffle-media \
      --b2-versions --transfers 4 --checkers 8 \
      --log-level INFO
    sleep 600
  done ) &

# loop 2: event-driven push (sub-second latency for new uploads)
inotifywait -m -r -e close_write,moved_to --format '%w%f' /srv/raffle/media |
  while read -r path; do
    rel="${path#/srv/raffle/media/}"
    rclone copyto "$path" "b2:raffle-media/$rel" --log-level INFO || \
      echo "ERROR copying $path"
  done
```

**Bucket-level B2 configuration:**
- Versioning: enabled (default for B2).
- Lifecycle rule: retain prior versions for **90 days**, then prune. This gives a 90-day undelete window for any individual file.
- Application key used by `media-syncer` has `writeFiles` permission but **NOT** `deleteFiles` — accidental or malicious `rclone delete` from prod cannot purge old versions. (`rclone sync` upload overwrites still create new versions; the prior versions persist.)

### 6.3 Restic archive (anti-ransomware layer)

**Why separate from the live replication path:** if a prod-host compromise can manipulate `rclone.conf` or the pgBackRest config, the attacker can push corrupt data to those buckets. Restic is the deep safety net:
- **Different bucket** (`raffle-archive`).
- **Different B2 application key**, scoped to that bucket only, with **no delete permission**.
- **Restic repo password is held by the operator** (in a password manager), NOT stored on the prod host. The prod host only has the B2 keys; without the repo password, an attacker cannot decrypt or destructively modify the archive.
- Cipher: restic's built-in AES-256.

**Host cron** (`/etc/cron.d/raffle-restic`):

```
0 3 * * * root /usr/local/bin/raffle-restic-backup.sh   # nightly snapshot
0 5 1 * * root /usr/local/bin/raffle-restic-check.sh    # monthly integrity check (read-only)
```

**Retention / pruning policy:**

The prod-host B2 application key intentionally has **no delete permission**, so `restic forget --prune` cannot run from the prod host (and must not — that's the anti-ransomware property). Snapshots therefore accumulate indefinitely from the prod side. Given restic's deduplication and the small data footprint (~6 MB media + small pgBackRest local repo today), a daily snapshot for several years remains in the single-digit GB range and costs cents/month at B2 rates. We accept unbounded growth here.

When pruning is eventually wanted, it is performed **off-host** (operator workstation or future second machine) using a separate, more-privileged B2 application key that lives only on that off-host machine. Retention applied at prune time: `--keep-daily 14 --keep-weekly 8 --keep-monthly 24 --keep-yearly 10`. Procedure documented in the restore playbook under "Off-host maintenance."

**Targets:** `/srv/raffle/media` and `/srv/raffle/pgbackrest` (the pgBackRest local repo is already a consistent snapshot of recent backups; archiving it gives an offline-restorable second copy without needing the running Postgres).

## 7. Data flow on a representative request

User submits a campaign entry with a photo:

1. Browser POSTs to Django; gunicorn worker handles the request.
2. Django saves the uploaded file → kernel writes to `/srv/raffle/media/submissions/<uuid>.jpg` on the bind mount.
3. inotify fires `close_write` → media-syncer's event loop runs `rclone copyto` → file in `b2:raffle-media/submissions/<uuid>.jpg` within seconds.
4. Django saves the `Submission` row → Postgres COMMIT → WAL record written.
5. Postgres reaches a WAL segment boundary (or `archive_timeout=60` elapses) → `archive_command` invokes `pgbackrest archive-push` → WAL segment pushed asynchronously to repo1 (local) and repo2 (B2).
6. (Nightly at 03:00) restic snapshots `/srv/raffle/media` and `/srv/raffle/pgbackrest` to `b2:raffle-archive`, deduplicated and encrypted.

## 8. Defense matrix (the comprehensive "no data loss" strategy)

| Threat | Defense | Recovery action |
|---|---|---|
| Container rebuilt; `docker compose down -v` | All state on host bind mounts under `/srv/raffle` | None needed; data is untouched |
| Host disk fails | Continuous replication to B2 (WAL + inotify push) | Restore on new host (§9) |
| VPS terminated / unrecoverable | Same B2 replicas | Provision new VPS, run restore playbook (~30 min RTO) |
| Accidental `DROP TABLE` / bad `UPDATE` | pgBackRest PITR (90-day window) | `pgbackrest restore --type=time --target='2026-05-13 14:23:00'` |
| Accidental file delete in app | B2 bucket versioning (90 days) | `rclone copyto b2:raffle-media/<path>?versionId=<v> /srv/raffle/media/<path>` |
| Long-running logic bug corrupts data over weeks/months | Nightly restic snapshots accumulate indefinitely (pruning is off-host only) | `restic restore <snapshot> --include /srv/raffle/...` |
| Ransomware encrypts prod host | Restic archive: separate bucket, separate key (no-delete), separate passphrase NOT on host | Restore from restic on fresh host |
| B2 application key leaked → attacker pushes bad data to live buckets | Restic archive is unaffected (different key, no-delete permission, encrypted with operator passphrase) | Restore from restic |
| Operator runs wrong restore command | Restore playbook is in git; restic and pgBackRest both support `--dry-run`; quarterly rehearsal target | n/a — rehearsal catches this |
| B2 region outage (rare) | Live replication is paused, not lost (local pgBackRest repo1 keeps accumulating); future second-machine pull would be independent | Wait it out; pgBackRest repo1 holds the gap |

## 9. Restore playbook (summary; detail will live in `docs/deployment/restore-playbook.md`)

### 9.1 Full disaster recovery to a new host

1. Provision new Linux host, install Docker + Docker Compose.
2. Create `/srv/raffle/{pg,media,pgbackrest,staticfiles,config}` with correct ownership.
3. Drop `pgbackrest.conf`, `rclone.conf`, `restic.env` into `/srv/raffle/config/` (these are the only secrets needed to restore; they are held offline in a password manager).
4. Clone repo, copy `.env.prod`, `docker compose -f docker-compose.prod.yml up -d postgres pgbackrest`.
5. `docker compose exec pgbackrest pgbackrest --stanza=raffle --repo=2 restore --delta` → pulls latest backup + WAL from B2.
6. `docker compose exec postgres pg_ctl start` → Postgres replays WAL to latest committed transaction.
7. `rclone sync b2:raffle-media /srv/raffle/media` → media restored.
8. `docker compose up -d web media-syncer` → app live.
9. Verify: log in, view campaigns, check row counts vs pre-disaster snapshot.

**Target RTO: 30 minutes.** **Target RPO: ~30 seconds of writes.**

### 9.2 Point-in-time recovery (e.g., accidental DELETE)

1. Stop `web` (no new writes during recovery).
2. `pgbackrest --stanza=raffle --type=time --target='2026-05-13 14:23:00' restore`
3. Start Postgres → recovers up to the target time.
4. Verify data, restart `web`.

### 9.3 Single-file restore from B2 versioning

```
rclone lsf b2:raffle-media/submissions/<uuid>.jpg --b2-versions
rclone copyto 'b2:raffle-media/submissions/<uuid>-v123.jpg' /srv/raffle/media/submissions/<uuid>.jpg
```

### 9.4 Restic restore (older than 90 days, or ransomware case)

```
export RESTIC_REPOSITORY=b2:raffle-archive
export RESTIC_PASSWORD=<from password manager>
restic snapshots
restic restore <snapshot-id> --target /tmp/restore --include /srv/raffle/media
```

### 9.5 Quarterly rehearsal

A `make restore-test` target spins up a throwaway container, runs `pgbackrest restore --repo=2` to a scratch directory, and verifies the latest backup is valid. Run quarterly; results logged in `docs/deployment/restore-rehearsal-log.md`.

## 10. Operational concerns

- **Monitoring:** pgBackRest emits exit codes on cron; media-syncer logs to stdout (captured by `docker logs`). Add a once-daily host cron that checks (a) the timestamp of the latest WAL in B2 is < 5 min old, (b) restic last-backup timestamp is < 25 h old, and emails on failure.
- **Storage cost (B2 pricing as of 2026):** ~$6/TB/mo. Current data is < 10 MB; cost is rounding-error. Will not exceed a few dollars/month even with 100× growth.
- **Network egress:** B2 egress is $0.01/GB. A full restore of all current data is < 1¢. The Cloudflare CDN egress allowance covers free reads if needed later.
- **Secret handling:** The three credential files (`pgbackrest.conf`, `rclone.conf`, `restic.env`) are gitignored. They live on the host and in the operator's password manager. They are NOT in the Docker image.
- **The `.env.prod` file** (which contains `DATABASE_URL` and Django `SECRET_KEY`) gets the same treatment: gitignored, host-only, password-manager-backed.

## 11. Implementation phases (preview; the implementation plan will expand each)

1. **Phase 1 — Host preparation.** Create `/srv/raffle/...`, B2 buckets, application keys.
2. **Phase 2 — Postgres + pgBackRest.** Add to compose, configure, smoke test on an empty DB.
3. **Phase 3 — SQLite → Postgres migration.** Dump/load/cutover; archive SQLite file.
4. **Phase 4 — Media-syncer.** Add rclone+inotify sidecar; verify event-driven and reconciliation paths.
5. **Phase 5 — Restic archive.** Host cron for nightly backup + monthly integrity check; document off-host pruning procedure; monitoring email on cron failure.
6. **Phase 6 — Restore playbook + rehearsal.** Write the playbook, run the first rehearsal, log it.
7. **Phase 7 — Decommission old paths.** Remove `./prod-data/` mounts from compose; remove SQLite-related code paths.

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Postgres migration loses or corrupts data | `dumpdata`/`loaddata` is well-trodden; row-count check + functional smoke test before cutover; SQLite file archived for 30 days. |
| Sequence values not advanced after `loaddata` | Explicit `setval()` step in migration plan; covered in §5.2 step 7. |
| pgBackRest archive_command failures silently block WAL writes | `archive-async=y` decouples push from commit; spool dir lets WAL keep rotating; alerting cron flags stale WAL in B2. |
| inotify event loss under burst | Periodic 10-min `rclone sync` reconciliation catches drift. |
| B2 application key leaked | Live keys scoped to single bucket and lack delete permission; archive key has no overlap; rotate keys quarterly. |
| Operator forgets restic password | Stored in password manager and in a sealed offline location; documented in onboarding for any future operator. |
| Restore playbook rots | Quarterly rehearsal target; rehearsal failures block other backup work until fixed. |

## 13. Future enhancements (out of scope for this iteration)

- Second machine: install rclone with read-only B2 credentials, pull `b2:raffle-media` and `b2:raffle-pgbackrest` on a cron. Zero changes to the prod host.
- Streaming replica Postgres on a second host (synchronous or asynchronous). Adds HA on top of DR.
- Switch media storage to django-storages with B2 as primary (host bind mount becomes a CDN cache). Eliminates the inotify path; trades it for upload-time latency.
- Move from B2 to a multi-region object store if traffic / compliance ever demands it.
