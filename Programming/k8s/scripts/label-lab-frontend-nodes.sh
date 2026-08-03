#!/usr/bin/env bash
set -euo pipefail

if (( $# == 0 )); then
  echo "Usage: $0 <node-with-aims-frontend-image> [node...]" >&2
  exit 2
fi

for node in "$@"; do
  kubectl get node "$node" >/dev/null
  kubectl label node "$node" aims.hust.vn/frontend-image=prod-sim --overwrite
done

echo "Labeled $# node(s) for the node-local AIMS frontend lab image."
