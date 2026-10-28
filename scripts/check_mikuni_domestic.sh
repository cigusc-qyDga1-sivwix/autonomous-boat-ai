#!/usr/bin/env bash
# Run the normal official replay page from the machine's existing eligible network.
# No VPN, no media recording, no cookies, no credentials or GitHub runner needed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v docker >/dev/null || { echo "Docker is required." >&2; exit 127; }
docker build -q -f "$ROOT/docker/mikuni-domestic-check/Dockerfile" -t boatlab-mikuni-domestic-check "$ROOT"
docker run --rm --pull=never --read-only \
  --tmpfs /tmp:rw,nosuid,size=512m \
  --tmpfs /home/pwuser:rw,nosuid,size=256m \
  --shm-size=512m --memory=1536m --cpus=2 \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --pids-limit=256 \
  boatlab-mikuni-domestic-check "$@"
