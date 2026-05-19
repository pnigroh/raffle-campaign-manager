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

echo "==> Phase 0/7: capture SQLite row counts as pre-migration baseline"
$COMPOSE exec -T web python manage.py shell <<'PY' > "${MIGRATION_DIR}/precount.txt"
from campaigns.models import Campaign, Submission, Raffle
from django.contrib.auth.models import User
print(f"campaigns_campaign: {Campaign.objects.count()}")
print(f"campaigns_submission: {Submission.objects.count()}")
print(f"campaigns_raffle: {Raffle.objects.count()}")
print(f"auth_user: {User.objects.count()}")
PY
echo "    baseline written to ${MIGRATION_DIR}/precount.txt:"
cat "${MIGRATION_DIR}/precount.txt"

echo "==> Phase 1/7: dump SQLite data via the running legacy container"
$COMPOSE exec -T web python manage.py dumpdata \
    --natural-foreign --natural-primary \
    --exclude=contenttypes --exclude=auth.permission --exclude=sessions \
    > "$DUMP_FILE"
LINES=$(wc -l < "$DUMP_FILE")
echo "    dumped $(du -h "$DUMP_FILE" | cut -f1) ($LINES lines)"

echo "==> Phase 2/7: stop legacy web container (no more writes)"
$COMPOSE stop web

echo "==> Phase 3/7: bring up Postgres (waits for healthy)"
$COMPOSE up -d postgres

# Give Postgres a few seconds beyond healthcheck to ensure init scripts ran.
sleep 5

echo "==> Phase 4/7: run Django migrations on the empty Postgres DB"
# Temporarily start a one-off web container with the new DATABASE_URL.
# This requires .env.prod to already be flipped to the Postgres URL.
$COMPOSE run --rm --no-deps web python manage.py migrate --noinput

echo "==> Phase 5/7: loaddata + reset sequences"
# Copy the dump into the web image's filesystem at /tmp and load it.
# Using --rm + a volume mount keeps the migration ephemeral.
$COMPOSE run --rm --no-deps -v "$MIGRATION_DIR":/migration web \
    python manage.py loaddata /migration/sqlite_dump.json

$COMPOSE run --rm --no-deps web \
    python -m scripts.reset_postgres_sequences

echo "==> Phase 6/7: start web container against Postgres"
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
