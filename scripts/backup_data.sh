#!/usr/bin/env bash
# AEGIS-SAR Automated Disaster Recovery Backup Script
# Archives persistent incident dossiers, ledger, reports, audit trail, and configs.

set -euo pipefail

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
BACKUP_DIR="${BACKUP_DIR:-backups}"
mkdir -p "${BACKUP_DIR}"

BACKUP_FILE="${BACKUP_DIR}/aegis_backup_${TIMESTAMP}.tar.gz"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

echo "=== AEGIS-SAR Backup: Initiating disaster recovery backup ==="
echo "Target archive: ${BACKUP_FILE}"

# Identify existing persistent directories
PERSISTENT_DIRS=()
for dir in data/results/incidents data/ledger data/reports data/audit config; do
  if [ -d "${dir}" ] || [ -f "${dir}" ]; then
    PERSISTENT_DIRS+=("${dir}")
  fi
done

if [ ${#PERSISTENT_DIRS[@]} -eq 0 ]; then
  echo "Error: No persistent directories found to backup." >&2
  exit 1
fi

# Create compressed archive excluding temp and cache
tar -czf "${BACKUP_FILE}" \
  --exclude="*.tmp" \
  --exclude="*.pyc" \
  --exclude="__pycache__" \
  "${PERSISTENT_DIRS[@]}"

# Compute SHA-256 checksum
if command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "${BACKUP_FILE}" > "${CHECKSUM_FILE}"
elif command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${BACKUP_FILE}" > "${CHECKSUM_FILE}"
fi

FILE_SIZE=$(ls -lh "${BACKUP_FILE}" | awk '{print $5}')
echo "Backup successfully created: ${BACKUP_FILE} (${FILE_SIZE})"
echo "SHA-256 checksum recorded in: ${CHECKSUM_FILE}"
echo "=== Backup Complete ==="
