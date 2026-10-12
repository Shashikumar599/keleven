#!/usr/bin/env bash
# Dump the data the hosted app needs from the LOCAL database into deploy/office_rag_data.dump (git-ignored, about 30 MB).
# Not dumped: pipeline_versions (the migrations create it), qa_* (the question log starts empty when hosted).
# Usage:  set -a; source .env; set +a; bash deploy/export_data.sh
set -euo pipefail
OUT="${1:-deploy/office_rag_data.dump}"
TABLES=(episodes lines chunk_sets chunks embedding_models chunk_embeddings
        extraction_runs episode_extractions
        graph_builds graph_current graph_entities graph_entity_links graph_characters graph_places graph_events
        graph_event_participants graph_relations graph_refers_back graph_episode_summaries)
ARGS=(); for t in "${TABLES[@]}"; do ARGS+=(-t "public.$t"); done
docker exec office-rag-db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --data-only --format=custom "${ARGS[@]}" > "$OUT"
ls -lh "$OUT"
