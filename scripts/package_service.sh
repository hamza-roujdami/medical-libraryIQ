#!/usr/bin/env bash
# Builds the zip for the tools web app. Run: scripts/package_service.sh [output.zip]
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${1:-/tmp/libraryiq-service.zip}"
stage="$(mktemp -d)"
mkdir -p "$stage/libraryiq"
cp "$root"/src/libraryiq/{__init__,server,tools,lookup,access,orders,identifiers}.py "$stage/libraryiq/"
cp "$root/scripts/service-requirements.txt" "$stage/requirements.txt"
rm -f "$out"
(cd "$stage" && zip -qr "$out" .)
echo "wrote $out"
