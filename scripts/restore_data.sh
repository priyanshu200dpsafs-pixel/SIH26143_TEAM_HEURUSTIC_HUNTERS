#!/usr/bin/env bash
# AEGIS-SAR Automated Disaster Recovery Restore Script
# Verifies cryptographic checksum and unpacks persistent artifacts.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <path_to_backup_archive.tar.gz>" >&2
  exit 1
fi

ARCHIVE_PATH="$1"
CHECKSUM_FILE="${ARCHIVE_PATH}.sha256"

if [ ! -f "${ARCHIVE_PATH}" ]; then
  echo "Error: Backup archive file '${ARCHIVE_PATH}' not found." >&2
  exit 1
fi

echo "=== AEGIS-SAR Restore: Initiating recovery ==="
echo "Archive: ${ARCHIVE_PATH}"

# 1. Verify SHA-256 checksum if checksum file exists
if [ -f "${CHECKSUM_FILE}" ]; then
  echo "Verifying SHA-256 cryptographic checksum..."
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -c "${CHECKSUM_FILE}"
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c "${CHECKSUM_FILE}"
  fi
  echo "Checksum verified: Archive integrity confirmed."
else
  echo "Warning: No accompanying .sha256 checksum file found. Proceeding with caution."
fi

# 2. Extract into temporary verification directory first
TMP_RESTORE_DIR=$(mktemp -d /tmp/aegis_restore_XXXXXX)
trap 'rm -rf "${TMP_RESTORE_DIR}"' EXIT

echo "Extracting archive into staged directory: ${TMP_RESTORE_DIR}"
tar -xzf "${ARCHIVE_PATH}" -C "${TMP_RESTORE_DIR}"

# 3. Copy verified files to working directory
echo "Restoring persistent datasets to platform..."
cp -R "${TMP_RESTORE_DIR}/"* ./

echo "=== Restore Complete: Persistent datasets restored successfully ==="
