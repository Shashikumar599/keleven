#!/usr/bin/env bash
# Fresh machine: database, schema, cleaned transcripts, chunks. Everything except embedding, which calls Voyage (costs tokens):
# run that yourself at the end (see docs/setup.md).
#
#   cp .env.example .env   # fill in the values
#   scripts/bootstrap.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "missing .env: copy .env.example and fill it in"; exit 1; }
set -a; source .env; set +a
PY=.venv/bin/python
[ -x "$PY" ] || { echo "missing .venv: python3 -m venv .venv && .venv/bin/pip install -e ."; exit 1; }

echo "== 1/5 database"
docker compose -f docker-compose.db.yml up -d
for i in $(seq 1 30); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' office-rag-db 2>/dev/null)" = healthy ] && break
  sleep 2
done
[ "$(docker inspect -f '{{.State.Health.Status}}' office-rag-db)" = healthy ] || { echo "database not healthy"; exit 1; }

PSQL=(docker exec -i office-rag-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q)
if "${PSQL[@]}" -tAc "select to_regclass('public.lines')" | grep -q lines; then
  echo "tables already exist: not applying migrations (this script is for an empty database)"; exit 1
fi

echo "== 2/5 migrations"
for f in db/migrations/*.sql; do
  echo "  $f"
  "${PSQL[@]}" -v app_password="$APP_DB_PASSWORD" < "$f"
done

echo "== 3/5 clean the raw transcripts (data/raw -> data/processed)"
$PY ingest/clean.py

echo "== 4/5 load into Postgres"
$PY ingest/load.py

echo "== 5/5 chunks (pack_300t_3s_80min: 300 tokens, 3 scenes, min 80)"
$PY ingest/chunk.py --max-tokens 300 --max-scenes 3 --min-tokens 80

"${PSQL[@]}" -tAc "select 'lines: '||count(*) from lines" 
"${PSQL[@]}" -tAc "select 'chunks: '||count(*) from chunks"
echo "expected on the original machine: lines 57973, chunks 4658"
echo
echo "Next, by hand (Voyage calls, cost tokens):  python ingest/embed.py --dry-run   then   python ingest/embed.py"
