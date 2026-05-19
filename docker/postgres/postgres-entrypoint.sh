#!/bin/bash
# Wrapper entrypoint:
#   1. Start cron daemon in the background to drive pgbackrest scheduled backups.
#   2. Exec the upstream Postgres docker-entrypoint with the original CMD.
# The cron daemon runs each crontab entry as the user specified in the
# system-cron file (/etc/cron.d/pgbackrest uses 'postgres' as the user column).
set -e

# Start cron in daemon mode (default for `cron` with no args).
cron

# Hand off to the official Postgres entrypoint, preserving CMD.
exec docker-entrypoint.sh "$@"
