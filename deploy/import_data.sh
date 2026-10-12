#!/usr/bin/env bash
# Load a deploy/export_data.sh dump into a TARGET database that already has the migrations applied (empty tables).
# Needs a pg_restore of version 17; this runs one from a container, so only Docker is required.
# Usage:  TARGET_URL='postgresql://admin:PASSWORD@host.docker.internal:PORT/office_rag' bash deploy/import_data.sh [dump-file]
# The host in TARGET_URL must be reachable from inside a container: use host.docker.internal for something running on this
# machine (a local test database, or the Cloud SQL Auth Proxy; see docs/hosting.md).
set -euo pipefail
DUMP="${1:-deploy/office_rag_data.dump}"
: "${TARGET_URL:?set TARGET_URL}"
docker run --rm -i --add-host=host.docker.internal:host-gateway pgvector/pgvector:0.8.7-pg17 \
  pg_restore --data-only --no-owner --exit-on-error -d "$TARGET_URL" < "$DUMP"
echo "restored $DUMP"
