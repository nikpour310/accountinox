import os
import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()
from django.conf import settings
from PIL import Image

# Configuration
MIN_SIZE_BYTES = 50 * 1024  # only consider images larger than 50KB
SEARCH_DIRS = [
    Path(settings.MEDIA_ROOT),
    proj_root / 'static',
    proj_root / 'staticfiles',
]
EXTS = ('.jpg', '.jpeg', '.png')

results = []
converted_count = 0
skipped = 0
errors = 0

print('Scanning for images to convert (lossless WebP) ...')
for base in SEARCH_DIRS:
    if not base or not base.exists():
        continue
    for root, dirs, files in os.walk(base):
        for fname in files:
            lower = fname.lower()
            if not lower.endswith(EXTS):
                continue
            full = Path(root) / fname
            try:
                size = full.stat().st_size
            except Exception:
                continue
            if size < MIN_SIZE_BYTES:
                skipped += 1
                continue
            out_path = full.with_suffix('.webp')
            if out_path.exists():
                # already converted
                skipped += 1
                continue
            try:
                im = Image.open(full)
                # Convert to RGB if needed (WebP supports RGB/RGBA)
                if im.mode in ('P', 'L'):
                    im = im.convert('RGBA')
                # Save lossless WebP
                im.save(out_path, format='WEBP', lossless=True, quality=100, method=6)
                new_size = out_path.stat().st_size
                saved = size - new_size
                results.append((str(full.relative_to(proj_root)), size, str(out_path.relative_to(proj_root)), new_size, saved))
                converted_count += 1
            except Exception as e:
                print('Error converting', full, e)
                errors += 1

# Report
print('\nConversion complete')
print('Converted files:', converted_count)
print('Skipped (small or already converted):', skipped)
print('Errors:', errors)

if results:
    total_before = sum(r[1] for r in results)
    total_after = sum(r[3] for r in results)
    total_saved = sum(r[4] for r in results)
    print('\nTop conversions:')
    for src, before, dst, after, saved in sorted(results, key=lambda x: x[4], reverse=True)[:20]:
        print(f"{src} -> {dst}: {round(before/1024,1)}KB -> {round(after/1024,1)}KB, saved {round(saved/1024,1)}KB")
    print('\nTotals:')
    print('  Before: ', round(total_before/1024,1), 'KB')
    print('  After:  ', round(total_after/1024,1), 'KB')
    print('  Saved:  ', round(total_saved/1024,1), 'KB')
else:
    print('No conversions performed (no matching images found above threshold).')
