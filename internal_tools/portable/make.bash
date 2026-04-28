#!/usr/bin/env bash
set -x -e

SCRIPT_PARENT_DIR="$(dirname $(readlink -f "$0"))"
GIT_SHA_SHORT="$(git rev-parse --short HEAD)"
ZIP_NAME="portable_exploration_tool_${GIT_SHA_SHORT}.zip"

rm -f "$ZIP_NAME"

# Windows 11 default (checked 2026-04-28) is to unpack
# a zip in a folder with the same name as the zip itself.
(
  cd "${SCRIPT_PARENT_DIR}/package_contents"
  zip -v -r "${OLDPWD}/${ZIP_NAME}" .
)
