import re
from pathlib import Path


MOJIBAKE_PATTERNS = (
    re.compile(r"[ØÙÚÛÐÑÃÂ]"),
    re.compile(r"â€|â€™|â€œ|â€�|â€“|â€”|ï»¿"),
)

TARGET_EXTENSIONS = {".py", ".html", ".css", ".js", ".txt", ".xml"}
TARGET_DIRS = ("apps", "templates", "config")


def _iter_target_files(project_root: Path):
    for dirname in TARGET_DIRS:
        base = project_root / dirname
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in TARGET_EXTENSIONS:
                yield path

    manage_file = project_root / "manage.py"
    if manage_file.exists():
        yield manage_file


def test_no_mojibake_sequences_in_source_text():
    project_root = Path(__file__).resolve().parents[1]
    offenders = []

    for path in _iter_target_files(project_root):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in MOJIBAKE_PATTERNS):
                offenders.append(f"{path.relative_to(project_root)}:{line_no}: {line.strip()[:120]}")
                if len(offenders) >= 30:
                    break
        if len(offenders) >= 30:
            break

    assert not offenders, "Possible mojibake text detected:\n" + "\n".join(offenders)
