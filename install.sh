#!/usr/bin/env bash

# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 white-toolbelt contributors

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/bin"
TARGET_DIR="${HOME}/.local/bin"

if [[ ! -d "${TARGET_DIR}" ]]; then
  echo "Error: target directory '${TARGET_DIR}' does not exist." >&2
  echo "Please create it first, for example: mkdir -p '${TARGET_DIR}'" >&2
  exit 1
fi

if [[ ! -d "${BIN_DIR}" ]]; then
  echo "Error: source directory '${BIN_DIR}' does not exist." >&2
  exit 1
fi

for file in "${BIN_DIR}"/*; do
  if [[ -f "${file}" ]]; then
    name="$(basename "${file}")"
    ln -sfn "${file}" "${TARGET_DIR}/${name}"
    echo "Linked ${TARGET_DIR}/${name} -> ${file}"
  fi
done
