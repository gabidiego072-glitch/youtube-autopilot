#!/usr/bin/env bash
# Install the official Blender LTS build (free, GPL) and verify its SHA-256 checksum.
# Usage: scripts/install_blender.sh [install_dir]     (default /opt/blender)
set -euo pipefail

VERSION="${BLENDER_VERSION:-4.5.15}"
SERIES="${VERSION%.*}"
DEST="${1:-/opt/blender}"
NAME="blender-${VERSION}-linux-x64"
BASE="https://download.blender.org/release/Blender${SERIES}"

mkdir -p "$DEST"
cd "$DEST"
curl -fSL -o "${NAME}.tar.xz" "${BASE}/${NAME}.tar.xz"
curl -fsSL "${BASE}/blender-${VERSION}.sha256" | grep " ${NAME}.tar.xz$" > "${NAME}.sha256"
sha256sum -c "${NAME}.sha256"
tar -xf "${NAME}.tar.xz"
rm "${NAME}.tar.xz" "${NAME}.sha256"
echo "Installed: ${DEST}/${NAME}/blender"
echo "Set BLENDER_BINARY=${DEST}/${NAME}/blender (or add it to PATH)."
