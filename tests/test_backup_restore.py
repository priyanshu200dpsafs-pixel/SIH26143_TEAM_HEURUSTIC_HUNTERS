"""Automated Disaster Recovery Backup & Restore Tests for AEGIS-SAR."""

import os
import subprocess
import hashlib
from pathlib import Path
import pytest


def calculate_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_backup_and_restore_cycle(tmp_path):
    """Test full backup creation, checksum verification, and restore cycle."""
    repo_root = Path(__file__).resolve().parent.parent
    backup_script = repo_root / 'scripts' / 'backup_data.sh'
    restore_script = repo_root / 'scripts' / 'restore_data.sh'

    assert backup_script.exists(), 'backup_data.sh does not exist'
    assert restore_script.exists(), 'restore_data.sh does not exist'

    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 1. Run backup script
    env = os.environ.copy()
    env['BACKUP_DIR'] = str(backup_dir)

    result = subprocess.run(
        [str(backup_script)],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f'Backup script failed: {result.stderr}'
    assert 'Backup Complete' in result.stdout

    # 2. Verify backup archive and checksum exist
    archives = list(backup_dir.glob('aegis_backup_*.tar.gz'))
    assert len(archives) == 1, f'Expected 1 backup archive, found {len(archives)}'
    archive = archives[0]
    checksum_file = Path(str(archive) + '.sha256')
    assert checksum_file.exists(), 'SHA-256 checksum file was not created'

    # Verify cryptographic integrity
    actual_hash = calculate_sha256(archive)
    recorded_checksum_content = checksum_file.read_text().strip()
    assert actual_hash in recorded_checksum_content

    # 3. Test tamper detection (restore should fail if corrupted)
    corrupted_archive = tmp_path / 'corrupted.tar.gz'
    corrupted_checksum = tmp_path / 'corrupted.tar.gz.sha256'
    corrupted_archive.write_bytes(archive.read_bytes() + b'CORRUPTION_BYTES')
    with open(corrupted_checksum, 'w') as f:
        f.write(actual_hash + '  ' + corrupted_archive.name + chr(10))

    tamper_result = subprocess.run(
        [str(restore_script), str(corrupted_archive)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert tamper_result.returncode != 0, 'Corrupted archive unexpectedly passed verification!'

    # 4. Test valid restore into an isolated staging directory
    staging_dir = tmp_path / 'restore_staging'
    staging_dir.mkdir(parents=True, exist_ok=True)

    restore_result = subprocess.run(
        [str(restore_script), str(archive)],
        cwd=str(staging_dir),
        capture_output=True,
        text=True,
    )
    assert restore_result.returncode == 0, f'Restore script failed: {restore_result.stderr}'
    assert 'Restore Complete' in restore_result.stdout

    # Check that restored files exist in staging dir
    assert (staging_dir / 'data').exists() or (staging_dir / 'config').exists()
