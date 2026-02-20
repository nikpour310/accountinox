from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import models
from django.test import Client


_MARKER_CHARS = "".join(chr(code) for code in (0x00C3, 0x00D8, 0x00D9, 0x00D0, 0x00D1, 0x00C2))
_MARKER_GROUPS = (
    "".join(chr(code) for code in (0x00C3, 0x00A2, 0x00E2, 0x201A, 0x00AC)),
    "".join(chr(code) for code in (0x00C3, 0x00AF, 0x00C2, 0x00BB, 0x00C2, 0x00BF)),
    chr(0xFFFD),
)

MOJIBAKE_PATTERNS = (
    re.compile(f"[{re.escape(_MARKER_CHARS)}]"),
    re.compile("|".join(re.escape(group) for group in _MARKER_GROUPS)),
)

SOURCE_EXTENSIONS = {".py", ".html", ".css", ".js", ".txt", ".xml"}
SOURCE_DIRS = ("apps", "templates", "config")


def _looks_mojibake(value: str) -> bool:
    return any(pattern.search(value) for pattern in MOJIBAKE_PATTERNS)


class Command(BaseCommand):
    help = "Detect likely mojibake in sources, DB text fields, key responses, and logs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with a non-zero status when suspicious text is detected.",
        )
        parser.add_argument(
            "--db-limit",
            type=int,
            default=200,
            help="Max rows to inspect per model for DB text fields (default: 200).",
        )

    def handle(self, *args, **options):
        findings: list[str] = []

        findings.extend(self._scan_sources())
        findings.extend(self._scan_logs())
        findings.extend(self._scan_db(db_limit=options["db_limit"]))
        findings.extend(self._scan_responses())

        if findings:
            self.stdout.write(self.style.WARNING("Possible mojibake findings:"))
            for finding in findings:
                self.stdout.write(f"- {finding}")
            if options["strict"]:
                raise CommandError(f"{len(findings)} mojibake issue(s) detected.")
            self.stdout.write(
                self.style.WARNING(
                    "Finished with warnings. Re-run with --strict to fail on findings."
                )
            )
            return

        self.stdout.write(self.style.SUCCESS("No mojibake patterns detected."))

    def _iter_source_files(self) -> Iterable[Path]:
        root = Path(settings.BASE_DIR)
        for dirname in SOURCE_DIRS:
            base = root / dirname
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS:
                    yield path
        manage_py = root / "manage.py"
        if manage_py.exists():
            yield manage_py

    def _scan_sources(self) -> list[str]:
        root = Path(settings.BASE_DIR)
        findings: list[str] = []
        for path in self._iter_source_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                findings.append(f"{path.relative_to(root)} cannot decode as UTF-8: {exc}")
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if _looks_mojibake(line):
                    findings.append(
                        f"{path.relative_to(root)}:{line_no} suspicious sequence in source text"
                    )
                    break
        return findings

    def _scan_logs(self) -> list[str]:
        findings: list[str] = []
        logs_dir = Path(settings.BASE_DIR) / "logs"
        if not logs_dir.exists():
            return findings
        for name in ("django_error.log", "django_info.log"):
            path = logs_dir / name
            if not path.exists():
                continue
            raw = path.read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                findings.append(f"logs/{name} is not valid UTF-8: {exc}")
                continue
            if _looks_mojibake(text):
                findings.append(f"logs/{name} contains suspicious mojibake sequences")
        return findings

    def _scan_db(self, db_limit: int) -> list[str]:
        findings: list[str] = []
        project_app_labels = {"core", "shop", "blog", "support", "accounts"}
        text_field_types = (models.CharField, models.TextField)

        for model in apps.get_models():
            if model._meta.app_label not in project_app_labels:
                continue
            text_fields = [
                field.name
                for field in model._meta.concrete_fields
                if isinstance(field, text_field_types)
            ]
            if not text_fields:
                continue
            try:
                queryset = model._default_manager.only(*text_fields)[: max(1, int(db_limit))]
                for obj in queryset:
                    for field_name in text_fields:
                        value = getattr(obj, field_name, "")
                        if not value:
                            continue
                        if _looks_mojibake(str(value)):
                            findings.append(
                                f"{model._meta.label} id={obj.pk} field={field_name} has suspicious text"
                            )
                            break
            except Exception:
                # Skip models unavailable in current DB state (e.g., unapplied migrations).
                continue
        return findings

    def _scan_responses(self) -> list[str]:
        findings: list[str] = []
        client = Client()

        urls = ["/", "/shop/", "/blog/", "/robots.txt", "/sitemap.xml"]

        try:
            from apps.shop.models import Product

            product = Product.objects.filter(is_active=True).only("slug").first()
            if product:
                urls.append(f"/shop/product/{product.slug}/")
        except Exception:
            pass

        try:
            from apps.blog.models import Post

            post = Post.objects.filter(published=True).only("slug").first()
            if post:
                urls.append(f"/blog/{post.slug}/")
        except Exception:
            pass

        for url in urls:
            try:
                response = client.get(url)
            except Exception as exc:
                findings.append(f"{url} could not be rendered during response scan: {exc}")
                continue
            if response.status_code >= 400:
                findings.append(f"{url} returned HTTP {response.status_code} during response scan")
                continue

            content_type = response.get("Content-Type", "")
            if url == "/robots.txt" and "charset=utf-8" not in content_type.lower():
                findings.append("robots.txt response is missing charset=utf-8 content type")

            try:
                text = response.content.decode("utf-8")
            except UnicodeDecodeError as exc:
                findings.append(f"{url} response is not valid UTF-8: {exc}")
                continue

            if _looks_mojibake(text):
                findings.append(f"{url} response contains suspicious mojibake sequences")

        return findings
