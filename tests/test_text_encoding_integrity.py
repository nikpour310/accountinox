import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.blog.models import Post
from apps.shop.models import Category, Product


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


def test_logging_file_handlers_use_utf8_encoding():
    handlers = settings.LOGGING.get("handlers", {})
    for handler_name in ("file_error", "file_info"):
        handler = handlers.get(handler_name, {})
        assert handler.get("encoding") == "utf-8", f"{handler_name} is missing UTF-8 encoding"


@pytest.mark.django_db
def test_key_responses_are_utf8_and_without_mojibake(client):
    category = Category.objects.create(name="Encoding Category", slug="encoding-category")
    product = Product.objects.create(
        category=category,
        title="Encoding Product",
        slug="encoding-product",
        price="1000",
        is_active=True,
        is_available=True,
    )
    post = Post.objects.create(
        title="Encoding Blog Post",
        slug="encoding-blog-post",
        content="Encoding blog content",
        published=True,
    )

    urls = [
        reverse("core:landing"),
        reverse("shop:product_list"),
        reverse("shop:product_detail", args=[product.slug]),
        reverse("blog:post_list"),
        reverse("blog:post_detail", args=[post.slug]),
        reverse("robots_txt"),
        reverse("sitemap"),
    ]

    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        if url == reverse("robots_txt"):
            assert "charset=utf-8" in response["Content-Type"].lower()
        text = response.content.decode("utf-8")
        assert not any(pattern.search(text) for pattern in MOJIBAKE_PATTERNS), url
