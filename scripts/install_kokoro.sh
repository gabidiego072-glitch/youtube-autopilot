#!/usr/bin/env bash
# Download the Kokoro-82M ONNX model and voices (Apache-2.0) for natural narration.
# Usage: scripts/install_kokoro.sh [dest_dir]
set -euo pipefail
DEST="${1:-models/kokoro}"
BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
mkdir -p "$DEST"
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -f "$DEST/$f" ] || curl -fSL -o "$DEST/$f" "$BASE/$f"
done
echo "Set KOKORO_MODEL_DIR=$DEST"
