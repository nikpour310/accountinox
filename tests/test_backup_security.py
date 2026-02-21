import zipfile

import pytest

from apps.core.backup_utils import BACKUP_DB_FILENAME, restore_site_backup
from apps.core.models import SiteBackup


@pytest.mark.django_db
def test_restore_site_backup_blocks_zip_slip_paths():
    backup_dir = SiteBackup.backup_directory()
    file_name = 'zip-slip-test-backup.zip'
    archive_path = backup_dir / file_name

    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(BACKUP_DB_FILENAME, '[]')
        archive.writestr('../escape.txt', 'pwned')

    backup = SiteBackup.objects.create(
        file_name=file_name,
        size_bytes=archive_path.stat().st_size,
    )
    try:
        with pytest.raises(ValueError):
            restore_site_backup(backup)
    finally:
        backup.delete()
