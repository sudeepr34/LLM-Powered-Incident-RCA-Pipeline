#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="incident-rca:latest"
CONTAINER_NAME="incident-rca-api"
DATA_DIR="$ROOT_DIR/.data"

mkdir -p "$DATA_DIR"

podman build -t "$IMAGE_NAME" "$ROOT_DIR"
podman rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

# Defaults to the offline summariser. To use a local model instead, run an
# Ollama daemon on the host and pass:
#   -e RCA_ENABLE_LLM=true -e RCA_LLM_PROVIDER=ollama \
#   -e RCA_LLM_BASE_URL=http://host.containers.internal:11434
podman run -d --name "$CONTAINER_NAME" \
  -p 8000:8000 \
  -e RCA_LOG_LEVEL=INFO \
  -e RCA_DEFAULT_SOURCE=podman \
  -e RCA_DATABASE_URL=sqlite:////data/rca.db \
  -v "$DATA_DIR:/data" \
  "$IMAGE_NAME"

echo "Container started."
echo "Health check: curl http://localhost:8000/api/health"
echo "Logs: podman logs -f $CONTAINER_NAME"
