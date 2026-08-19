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

if ! command -v distro-info >/dev/null 2>&1; then
  echo "Error: distro-info not found (needed for the apt-file devel source)." >&2
  exit 1
fi
DEVEL_CODENAME="$(distro-info --devel)"

APT_FILE_CONF_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/apt-file"
APT_FILE_DEVEL_CACHE="${HOME}/.cache/apt-file.devel"
APT_FILE_DEFAULT_CACHE="${HOME}/.cache/apt-file"

mkdir -p "${APT_FILE_CONF_DIR}" \
         "${APT_FILE_DEVEL_CACHE}/sources" "${APT_FILE_DEVEL_CACHE}/lists" \
         "${APT_FILE_DEFAULT_CACHE}/lists"

install -m 644 "${SCRIPT_DIR}/configs/apt-file.default.conf" "${APT_FILE_CONF_DIR}/apt-file.default.conf"
install -m 644 "${SCRIPT_DIR}/configs/apt-file.devel.conf"  "${APT_FILE_CONF_DIR}/apt-file.devel.conf"

rm -f "${APT_FILE_DEVEL_CACHE}/sources/"*.sources
sed "s/@DEVEL@/${DEVEL_CODENAME}/g" \
  "${SCRIPT_DIR}/configs/apt-file/devel.sources" \
  > "${APT_FILE_DEVEL_CACHE}/sources/${DEVEL_CODENAME}.sources"
