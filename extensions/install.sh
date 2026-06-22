#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXT_DIR="${HOME}/.local/share/ulauncher/extensions"

mkdir -p "${EXT_DIR}"
rm -rf "${EXT_DIR}/fd"
cp -r "${SCRIPT_DIR}/fd" "${EXT_DIR}/"

echo "fd extension installed to ${EXT_DIR}/fd"
