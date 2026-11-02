#!/usr/bin/env bash
# Download a free Piper voice (default: Spanish es_ES-davefx-medium, CC0 dataset).
# Usage: scripts/install_voice.sh [voice_path_in_repo] [dest_dir]
# Check each voice's MODEL_CARD before commercial use (some are fine-tuned from other datasets).
set -euo pipefail
VOICE="${1:-es/es_ES/davefx/medium}"
DEST="${2:-models/voices}"
NAME="$(echo "$VOICE" | awk -F/ '{print $2"-"$3"-"$4}')"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/${VOICE}"
mkdir -p "$DEST"
for f in "${NAME}.onnx" "${NAME}.onnx.json" MODEL_CARD; do
  curl -fSL -o "${DEST}/${f/MODEL_CARD/${NAME}.MODEL_CARD}" "${BASE}/${f}"
done
echo "Set PIPER_VOICE_MODEL=${DEST}/${NAME}.onnx"
