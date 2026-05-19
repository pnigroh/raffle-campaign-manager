#!/bin/bash
# Runs once on first DB init. Two responsibilities:
#   1. Create the pgbackrest role with the privileges it needs.
#      - pg_read_all_settings is required for pgbackrest stanza-create/check.
#      - REPLICATION lets it call pg_backup_start/stop and pg_switch_wal.
#   2. Append our archive config to postgresql.conf so archive_mode etc. take
#      effect on the post-init server restart. The standard Postgres docker
#      image does NOT include /etc/postgresql/conf.d via include_dir, so
#      dropping a fragment there is not enough on its own.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE pgbackrest WITH LOGIN REPLICATION;
    GRANT pg_read_all_settings TO pgbackrest;
    GRANT EXECUTE ON FUNCTION pg_backup_start(text, boolean) TO pgbackrest;
    GRANT EXECUTE ON FUNCTION pg_backup_stop(boolean) TO pgbackrest;
    GRANT EXECUTE ON FUNCTION pg_create_restore_point(text) TO pgbackrest;
    GRANT EXECUTE ON FUNCTION pg_switch_wal() TO pgbackrest;
EOSQL

echo "" >> "$PGDATA/postgresql.conf"
echo "# --- pgBackRest archive settings (appended by 10-init-pgbackrest-user.sh) ---" >> "$PGDATA/postgresql.conf"
cat /etc/postgresql/conf.d/10-pgbackrest.conf >> "$PGDATA/postgresql.conf"
