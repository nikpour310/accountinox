import json
import re

import pytest
from django.urls import reverse

from apps.blog.models import Post
from apps.shop.models import Category, Product, Service


def _extract_jsonld_payloads(html: str) -> list[str]:
    return re.findall(
        r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _canonical_links(html: str) -> list[str]:
    return re.findall(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )


@pytest.fixture
def seo_seed(db):
    service = Service.objects.create(name="SEO Service", slug="seo-service", active=True, order=1)
    category = Category.objects.create(name="SEO Category", slug="seo-category")
    product = Product.objects.create(
        category=category,
        service=service,
        title="SEO Product",
        slug="seo-product",
        price="120000",
        is_active=True,
        is_available=True,
    )
    post = Post.objects.create(
        title="SEO Post",
        slug="seo-post",
        content="SEO post content",
        published=True,
    )
    return {"service": service, "product": product, "post": post}


@pytest.mark.django_db
def test_public_pages_have_consistent_metadata_contract(client, seo_seed):
    urls = [
        reverse("core:landing"),
        reverse("shop:product_list"),
        reverse("shop:service_list"),
        reverse("shop:service_detail", args=[seo_seed["service"].slug]),
        reverse("shop:product_detail", args=[seo_seed["product"].slug]),
        reverse("blog:post_list"),
        reverse("blog:post_detail", args=[seo_seed["post"].slug]),
    ]

    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        html = response.content.decode("utf-8")

        assert len(re.findall(r"<title\b", html, flags=re.IGNORECASE)) == 1, url
        assert (
            len(re.findall(r'<meta\s+name=["\']description["\']', html, flags=re.IGNORECASE))
            == 1
        ), url
        assert (
            len(re.findall(r'<meta\s+name=["\']robots["\']', html, flags=re.IGNORECASE))
            == 1
        ), url

        canonicals = _canonical_links(html)
        assert len(canonicals) == 1, url
        assert canonicals[0].startswith(("http://", "https://")), url

        assert 'property="og:locale" content="fa_IR"' in html, url
        for twitter_key in (
            "twitter:card",
            "twitter:title",
            "twitter:description",
            "twitter:url",
            "twitter:image",
        ):
            assert f'name="{twitter_key}"' in html, f"{url} missing {twitter_key}"

        payloads = _extract_jsonld_payloads(html)
        assert payloads, f"{url} missing JSON-LD"
        for payload in payloads:
            json.loads(payload.strip())


@pytest.mark.django_db
def test_landing_has_single_h1(client):
    response = client.get(reverse("core:landing"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert len(re.findall(r"<h1\b", html, flags=re.IGNORECASE)) == 1
