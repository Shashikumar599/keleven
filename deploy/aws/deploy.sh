#!/usr/bin/env bash
# Build the app image for the server's CPU, send it over ssh, and restart the app. Run from anywhere:
#   bash deploy/aws/deploy.sh
# Overrides (environment): HOST (default the Elastic IP), KEY (default ~/pem/keleven.pem), REMOTE_DIR (default ~/keleven).
# Does not touch the server's .env or the database volume; the data stays as it is.
set -euo pipefail
cd "$(dirname "$0")/../.."

HOST="${HOST:-3.105.221.163}"
KEY="${KEY:-$HOME/pem/keleven.pem}"
REMOTE_DIR="${REMOTE_DIR:-keleven}"
SSH=(ssh -i "$KEY" -o ConnectTimeout=15 "ec2-user@$HOST")

[ -f "$KEY" ] || { echo "key not found: $KEY (set KEY=...)"; exit 1; }

echo "1/4 build (linux/amd64)"
docker buildx build --platform linux/amd64 -t keleven:latest --load .
arch=$(docker image inspect keleven:latest --format '{{.Architecture}}')
[ "$arch" = "amd64" ] || { echo "image is $arch, the server needs amd64"; exit 1; }

echo "2/4 send the compose file"
scp -i "$KEY" -o ConnectTimeout=15 deploy/aws/docker-compose.yml "ec2-user@$HOST:$REMOTE_DIR/docker-compose.yml"

echo "3/4 send the image and load it (streamed, no temp file)"
docker save keleven:latest | gzip | "${SSH[@]}" 'gunzip | docker load'

echo "4/4 restart the app"
"${SSH[@]}" "cd $REMOTE_DIR && docker compose up -d && docker image prune -f >/dev/null && \
  for i in \$(seq 1 30); do curl -fsS localhost/healthz && echo && break || sleep 2; done && docker compose ps"

echo "done: the app is running the new image. Open http://$HOST (or the CloudFront URL)."
