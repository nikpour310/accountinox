import xml.etree.ElementTree as ET

import pytest
from django.urls import reverse

from apps.blog.models import Post
from apps.shop.models import Category, Product, Service


def _sitemap_locs(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    return [element.text or "" for element in root.findall(".//{*}loc")]


@pytest.fixture
def sitemap_seed(db):
    service = Service.objects.create(name="Indexable Service", slug="indexable-service", active=True)
    category = Category.objects.create(name="Indexable Category", slug="indexable-category")
    product = Product.objects.create(
        category=category,
        service=service,
        title="Indexable Product",
        slug="indexable-product",
        price="90000",
        is_active=True,
        is_available=True,
    )
    post = Post.objects.create(
        title="Indexable Blog Post",
        slug="indexable-blog-post",
        content="Indexable blog content",
        published=True,
    )
    return {"service": service, "product": product, "post": post}


@pytest.mark.django_db
def test_sitemap_includes_indexable_pages_only(client, sitemap_seed):
    response = client.get(reverse("sitemap"))
    assert response.status_code == 200
    xml_text = response.content.decode("utf-8")
    locs = _sitemap_locs(xml_text)

    assert any(loc.endswith(reverse("core:landing")) for loc in locs)
    assert any(loc.endswith(reverse("shop:product_list")) for loc in locs)
    assert any(loc.endswith(reverse("shop:service_list")) for loc in locs)
    assert any(
        loc.endswith(reverse("shop:service_detail", args=[sitemap_seed["service"].slug])) for loc in locs
    )
    assert any(
        loc.endswith(reverse("shop:product_detail", args=[sitemap_seed["product"].slug])) for loc in locs
    )
    assert any(loc.endswith(reverse("blog:post_list")) for loc in locs)
    assert any(loc.endswith(reverse("blog:post_detail", args=[sitemap_seed["post"].slug])) for loc in locs)

    assert all("/support/" not in loc for loc in locs)
    assert all(reverse("support:chat") not in loc for loc in locs)


@pytest.mark.django_db
def test_support_is_noindex_disallowed_and_absent_from_sitemap(client):
    support_response = client.get(reverse("support:chat"))
    assert support_response.status_code == 200
    support_html = support_response.content.decode("utf-8")
    assert '<meta name="robots" content="noindex,nofollow">' in support_html

    robots_response = client.get(reverse("robots_txt"))
    assert robots_response.status_code == 200
    assert "charset=utf-8" in robots_response["Content-Type"].lower()
    robots_text = robots_response.content.decode("utf-8")
    assert "Disallow: /support/" in robots_text

    sitemap_response = client.get(reverse("sitemap"))
    assert sitemap_response.status_code == 200
    sitemap_text = sitemap_response.content.decode("utf-8")
    assert reverse("support:chat") not in sitemap_text
