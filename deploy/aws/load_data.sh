#!/usr/bin/env bash
# On the server, once the db container is healthy: apply the migrations, then restore the data dump.
# Expects ./db/migrations/*.sql, ./office_rag_data.dump and ./.env next to this script.
set -euo pipefail
cd "$(dirname "$0")"
set -a; source .env; set +a
for f in db/migrations/*.sql; do
  echo "applying $f"
  docker compose exec -T db psql -U office_admin -d office_rag -v ON_ERROR_STOP=1 -q -v app_password="$APP_DB_PASSWORD" < "$f"
done
docker compose exec -T db pg_restore --data-only --no-owner --exit-on-error -U office_admin -d office_rag < office_rag_data.dump
docker compose exec -T db psql -U office_admin -d office_rag -c "SELECT (SELECT count(*) FROM lines) AS lines, (SELECT count(*) FROM chunk_embeddings) AS embeddings, (SELECT count(*) FROM graph_events) AS events"
