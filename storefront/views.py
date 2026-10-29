"""Read-only HTTP endpoints for the public storefront."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.cache import get_conditional_response
from django.views.decorators.http import require_safe

from price_tracker.models import ExchangeRate
from .catalog import BROWSING_PARAMETERS, allowed_payload, browse_page, build_pages, public_dependencies, public_page_paths, resolve_path, search_products, semantic_hash
from .models import StorePage
from .images import product_image_urls


def _enabled():
    return bool(getattr(settings, "STOREFRONT_ENABLED", False))


def _not_found():
    raise Http404


@require_safe
def page(request):
    """Serve a prerendered public page only while its dependencies remain public."""
    if not _enabled():
        _not_found()
    requested = request.path
    pages = build_pages(requested_path=requested)
    canonical = resolve_path(requested, pages)
    if canonical != requested:
        target = canonical
        if request.META.get("QUERY_STRING"):
            target += "?" + request.META["QUERY_STRING"]
        response = redirect(target, permanent=True)
        response["Cache-Control"] = "no-store"
        return response

    try:
        page_number = max(1, int(request.GET.get("page", "1")))
    except (TypeError, ValueError):
        page_number = 1
    browsing = any(request.GET.get(key) for key in BROWSING_PARAMETERS)
    page_path = canonical if browsing or page_number == 1 else f"{canonical}?page={page_number}"
    live_payload = pages.get(page_path)
    if live_payload is None:
        _not_found()
    if browsing and live_payload["kind"] != "product":
        # Match the JSON endpoint's filtered pagination validity while serving
        # the base canonical artifact; client navigation fills in the results.
        browse_page(live_payload, request.GET, pages)
    stored = StorePage.objects.filter(path=page_path, active=True).first()
    if not stored or not stored.html or not stored.rendered_hash or not stored.rendered_payload:
        return HttpResponse("Store page is being prepared.", status=503, content_type="text/plain; charset=utf-8",
                            headers={"Retry-After": "30", "Cache-Control": "no-store"})
    if not allowed_payload(stored.rendered_payload, public_dependencies()):
        return HttpResponse("Store page is being refreshed.", status=503, content_type="text/plain; charset=utf-8",
                            headers={"Retry-After": "30", "Cache-Control": "no-store"})
    etag_hash = hashlib.sha256((stored.rendered_hash + stored.html).encode("utf-8")).hexdigest()
    etag = '"' + etag_hash + '"'
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponse(status=304)
    else:
        response = HttpResponse(stored.html, content_type="text/html; charset=utf-8")
    response["ETag"] = etag
    response["Cache-Control"] = "no-cache"
    if not stored.rendered_payload.get("indexable") or browsing:
        response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@require_safe
def page_data(request):
    if not _enabled():
        _not_found()
    requested = request.GET.get("path", "/")
    pages = build_pages(requested_path=requested)
    canonical = resolve_path(requested, pages)
    try:
        page_number = max(1, int(request.GET.get("page", "1")))
    except (TypeError, ValueError):
        page_number = 1
    page_path = canonical if page_number == 1 else f"{canonical}?page={page_number}"
    browsing = any(request.GET.get(key) for key in BROWSING_PARAMETERS)
    payload = pages.get(canonical if browsing else page_path)
    if not payload:
        _not_found()
    if browsing and payload["kind"] != "product":
        payload = browse_page(payload, request.GET, pages)
    response = JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-cache"
    response["ETag"] = '"' + semantic_hash(payload) + '"'
    if browsing or not payload.get("indexable"):
        response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _rate_timestamp(rate):
    return getattr(rate, "source_updated_at", None)


@require_safe
def rates(request):
    if not _enabled():
        _not_found()
    now = timezone.now()
    latest = {}
    for currency in ("RUB", "USD"):
        row = ExchangeRate.objects.filter(currency=currency).order_by("-date", "-pk").first()
        timestamp = _rate_timestamp(row) if row else None
        if row and timestamp and now - timedelta(hours=48) <= timestamp <= now:
            try:
                value = Decimal(str(row.rate))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if value.is_finite() and value > 0:
                latest[currency] = (value, timestamp)
    rub = latest.get("RUB")
    usd = latest.get("USD")
    expires_at = min(item[1] for item in latest.values()) + timedelta(hours=48) if latest else None
    body = {
        "cny_per_rub": str(rub[0]) if rub else None,
        "usd_per_rub": str(rub[0] / usd[0]) if rub and usd else None,
        "source_updated_at": rub[1].isoformat() if rub else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expires_in_seconds": max(0, int((expires_at - now).total_seconds())) if expires_at else 0,
    }
    response = JsonResponse(body)
    response["Cache-Control"] = "no-cache"
    response["ETag"] = '"' + semantic_hash(body) + '"'
    return response


@require_safe
def search(request):
    if not _enabled():
        _not_found()
    locale = request.GET.get("locale", "zh")
    try:
        limit = int(request.GET.get("limit", 20))
    except (TypeError, ValueError):
        return JsonResponse({"error": "limit must be an integer"}, status=400)
    if limit < 1 or limit > 100:
        return JsonResponse({"error": "limit must be between 1 and 100"}, status=400)
    products = search_products(request.GET.get("q", ""), locale=locale, limit=limit)
    response = JsonResponse({"products": products}, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_safe
def sitemap(request):
    if not _enabled():
        _not_found()
    dependencies = public_dependencies()
    paths = public_page_paths(dependencies)
    entries = []
    origin = settings.STOREFRONT_ORIGIN.rstrip("/")
    rows = StorePage.objects.filter(active=True, rendered_hash__gt="", html__gt="").values_list(
        "path", "rendered_payload", "rendered_changed_at",
    ).order_by("path")
    for path, payload, changed_at in rows.iterator(chunk_size=200):
        if (path not in paths or not allowed_payload(payload, dependencies)
                or not payload.get("indexable")):
            continue
        entries.append((path, changed_at.date().isoformat() if changed_at else None,
                        product_image_urls(payload, origin)))
    # Revalidate live eligibility before consulting the cache or returning 304.
    # No signal/TTL gap can keep revoked pages in a cached sitemap.
    digest = semantic_hash({"version": 2, "origin": origin, "entries": entries})
    etag = '"' + digest + '"'
    response = get_conditional_response(request, etag=etag)
    if response is None:
        key = "storefront:sitemap:" + digest
        content = cache.get(key)
        if content is None:
            root = Element("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9",
                                      "xmlns:image": "http://www.google.com/schemas/sitemap-image/1.1"})
            for path, lastmod, images in entries:
                node = SubElement(root, "url")
                SubElement(node, "loc").text = origin + path
                if lastmod:
                    SubElement(node, "lastmod").text = lastmod
                for image in images:
                    SubElement(SubElement(node, "image:image"), "image:loc").text = image
            content = tostring(root, encoding="utf-8", xml_declaration=True)
            cache.set(key, content, timeout=300)
        response = HttpResponse(content, content_type="application/xml; charset=utf-8")
    response["ETag"] = etag
    response["Cache-Control"] = "no-cache"
    return response
