import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from django.utils.text import get_valid_filename

from .models import SiteBackup

BACKUP_DB_FILENAME = 'database.json'
BACKUP_METADATA_FILENAME = 'metadata.json'
BACKUP_MEDIA_DIRNAME = 'media'
BACKUP_FORMAT_VERSION = 1


def _next_backup_filename(base_time) -> str:
    base_name = f"site-backup-{base_time:%Y%m%d-%H%M%S}"
    backup_dir = SiteBackup.backup_directory()

    candidate = f'{base_name}.zip'
    if not (backup_dir / candidate).exists():
        return candidate

    index = 1
    while True:
        candidate = f'{base_name}-{index}.zip'
        if not (backup_dir / candidate).exists():
            return candidate
        index += 1


def _next_filename_from_base(base_name: str) -> str:
    backup_dir = SiteBackup.backup_directory()
    stem = Path(base_name).stem
    suffix = '.zip'

    candidate = f'{stem}{suffix}'
    if not (backup_dir / candidate).exists() and not SiteBackup.objects.filter(file_name=candidate).exists():
        return candidate

    index = 1
    while True:
        candidate = f'{stem}-{index}{suffix}'
        if not (backup_dir / candidate).exists() and not SiteBackup.objects.filter(file_name=candidate).exists():
            return candidate
        index += 1


def _sanitize_import_name(uploaded_name: str) -> str:
    raw_name = Path(uploaded_name or '').name
    if not raw_name:
        raw_name = f'imported-backup-{timezone.now():%Y%m%d-%H%M%S}.zip'

    stem = get_valid_filename(Path(raw_name).stem) or f'imported-backup-{timezone.now():%Y%m%d-%H%M%S}'
    return _next_filename_from_base(stem)


def _build_metadata(file_name: str) -> dict:
    return {
        'format_version': BACKUP_FORMAT_VERSION,
        'created_at': timezone.now().isoformat(),
        'site_name': getattr(settings, 'SITE_BASE_URL', '') or 'accountinox',
        'file_name': file_name,
        'database_engine': settings.DATABASES['default']['ENGINE'],
        'includes_media': True,
        'database_dump': BACKUP_DB_FILENAME,
        'media_dir': BACKUP_MEDIA_DIRNAME,
    }


def create_site_backup(*, user=None) -> SiteBackup:
    backup_dir = SiteBackup.backup_directory()
    backup_time = timezone.now()
    file_name = _next_backup_filename(backup_time)
    archive_path = backup_dir / file_name

    with tempfile.TemporaryDirectory(prefix='site-backup-') as temp_dir:
        temp_root = Path(temp_dir)
        db_dump_path = temp_root / BACKUP_DB_FILENAME
        metadata_path = temp_root / BACKUP_METADATA_FILENAME

        with db_dump_path.open('w', encoding='utf-8') as dump_file:
            call_command(
                'dumpdata',
                format='json',
                stdout=dump_file,
                verbosity=0,
            )

        metadata_path.write_text(
            json.dumps(_build_metadata(file_name), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        media_root = Path(settings.MEDIA_ROOT)
        with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(db_dump_path, arcname=BACKUP_DB_FILENAME)
            archive.write(metadata_path, arcname=BACKUP_METADATA_FILENAME)

            if media_root.exists():
                for media_file in media_root.rglob('*'):
                    if media_file.is_file():
                        arcname = Path(BACKUP_MEDIA_DIRNAME) / media_file.relative_to(media_root)
                        archive.write(media_file, arcname=str(arcname))

    created_by = None
    if user is not None and getattr(user, 'is_authenticated', False):
        created_by = user

    return SiteBackup.objects.create(
        file_name=file_name,
        size_bytes=archive_path.stat().st_size,
        created_by=created_by,
    )


def import_site_backup(uploaded_file, *, user=None) -> SiteBackup:
    if uploaded_file is None:
        raise ValueError('هیچ فایل بکاپی ارسال نشده است.')

    file_name = _sanitize_import_name(getattr(uploaded_file, 'name', ''))
    archive_path = SiteBackup.backup_directory() / file_name

    with archive_path.open('wb') as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    try:
        with zipfile.ZipFile(archive_path, 'r') as archive:
            file_names = [name for name in archive.namelist() if not name.endswith('/')]
            has_database_dump = any(Path(name).name == BACKUP_DB_FILENAME for name in file_names)
            if not has_database_dump:
                raise ValueError('فایل بکاپ معتبر نیست: فایل database.json در آرشیو وجود ندارد.')
    except zipfile.BadZipFile as exc:
        if archive_path.exists():
            archive_path.unlink()
        raise ValueError('فایل انتخاب‌شده یک ZIP معتبر نیست.') from exc
    except Exception:
        if archive_path.exists():
            archive_path.unlink()
        raise

    created_by = None
    if user is not None and getattr(user, 'is_authenticated', False):
        created_by = user

    try:
        return SiteBackup.objects.create(
            file_name=file_name,
            size_bytes=archive_path.stat().st_size,
            created_by=created_by,
        )
    except Exception:
        if archive_path.exists():
            archive_path.unlink()
        raise


def _safe_extract_zip(archive: zipfile.ZipFile, extract_root: Path) -> None:
    root_resolved = extract_root.resolve()
    for member in archive.infolist():
        member_name = (member.filename or '').replace('\\', '/')
        if member_name.startswith('/') or '..' in Path(member_name).parts:
            raise ValueError('فایل بکاپ نامعتبر است: مسیر ناامن داخل آرشیو یافت شد.')
        target_path = (extract_root / member_name).resolve()
        if target_path != root_resolved and root_resolved not in target_path.parents:
            raise ValueError('فایل بکاپ نامعتبر است: مسیر خارج از محدوده استخراج شناسایی شد.')
    archive.extractall(extract_root)


def restore_site_backup(backup: SiteBackup) -> None:
    archive_path = backup.file_path
    if not archive_path.exists():
        raise FileNotFoundError(f'فایل بکاپ پیدا نشد: {archive_path}')

    with tempfile.TemporaryDirectory(prefix='site-restore-') as temp_dir:
        temp_root = Path(temp_dir)
        extract_root = temp_root / 'extracted'
        extract_root.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(archive_path, 'r') as archive:
            _safe_extract_zip(archive, extract_root)

        db_dump_path = extract_root / BACKUP_DB_FILENAME
        if not db_dump_path.exists():
            raise ValueError('فایل بکاپ معتبر نیست: فایل database.json در آرشیو پیدا نشد.')

        call_command('migrate', interactive=False, verbosity=0)
        call_command('flush', interactive=False, verbosity=0, inhibit_post_migrate=True)
        call_command('loaddata', str(db_dump_path), verbosity=0)

        restored_media_root = extract_root / BACKUP_MEDIA_DIRNAME
        media_root = Path(settings.MEDIA_ROOT)
        media_root.parent.mkdir(parents=True, exist_ok=True)

        if media_root.exists():
            shutil.rmtree(media_root)

        if restored_media_root.exists():
            shutil.copytree(restored_media_root, media_root)
        else:
            media_root.mkdir(parents=True, exist_ok=True)
