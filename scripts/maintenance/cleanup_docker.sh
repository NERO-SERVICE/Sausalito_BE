#!/usr/bin/env bash
set -euo pipefail

echo "[cleanup] prune stopped containers"
docker container prune -f

echo "[cleanup] prune dangling/unused images"
docker image prune -f

echo "[cleanup] prune build cache"
docker builder prune -f

echo "[cleanup] done"
