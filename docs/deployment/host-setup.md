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
