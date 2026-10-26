"""Small, static HTTP error responses shared by Django route failures."""

from __future__ import annotations

from html import escape
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse


ERROR_COPY = {
    "zh": {
        "html_lang": "zh-CN",
        "title": "页面不存在",
        "heading": "页面不存在",
        "message": "你访问的页面可能已移动或不存在。",
        "home": "返回首页",
        "catalog": "浏览商品",
        "home_path": "/",
        "catalog_path": "/catalog",
    },
    "ru": {
        "html_lang": "ru-RU",
        "title": "Страница не найдена",
        "heading": "Страница не найдена",
        "message": "Возможно, страница была перемещена или удалена.",
        "home": "На главную",
        "catalog": "Каталог товаров",
        "home_path": "/ru/",
        "catalog_path": "/ru/catalog",
    },
    "en": {
        "html_lang": "en",
        "title": "Page not found",
        "heading": "Page not found",
        "message": "The page may have moved or no longer exists.",
        "home": "Back to home",
        "catalog": "Browse products",
        "home_path": "/en/",
        "catalog_path": "/en/catalog",
    },
}


def _locale(path: str) -> str:
    """Choose locale only from its exact first URL segment."""
    first_segment = path.split("/", 2)[1] if path.startswith("/") else path.split("/", 1)[0]
    return first_segment if first_segment in ("ru", "en") else "zh"


def _is_api_path(path: str) -> bool:
    normalized = path.lstrip("/")
    return (
        normalized == "api"
        or normalized.startswith("api/")
        or normalized == "privnote/api"
        or normalized.startswith("privnote/api/")
    )


def _artifact_path(locale: str) -> Path:
    filename = f"404-{locale}.html"
    roots = [Path(settings.STATIC_ROOT) / "frontend" / "errors"]
    if settings.DEBUG:
        roots.insert(0, Path(settings.BASE_DIR) / "static" / "frontend" / "errors")
    else:
        roots.append(Path(settings.BASE_DIR) / "static" / "frontend" / "errors")
    for root in roots:
        candidate = root / filename
        if candidate.is_file():
            return candidate
    return roots[0] / filename


def _fallback_html(locale: str) -> str:
    copy = ERROR_COPY[locale]
    # All interpolated values are fixed application copy, still escape them so
    # the fallback stays safe if copy is edited later.
    title, heading, message, home, catalog = (
        escape(copy[key], quote=True)
        for key in ("title", "heading", "message", "home", "catalog")
    )
    lang = escape(copy["html_lang"], quote=True)
    home_path = escape(copy["home_path"], quote=True)
    catalog_path = escape(copy["catalog_path"], quote=True)
    return (
        "<!doctype html><html lang=\"" + lang + "\"><head>"
        "<meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex, nofollow\"><title>" + title + "</title></head>"
        "<body><main><h1>" + heading + "</h1><p>" + message + "</p><nav>"
        "<a href=\"" + home_path + "\">" + home + "</a> "
        "<a href=\"" + catalog_path + "\">" + catalog + "</a>"
        "</nav></main></body></html>"
    )


def not_found(request, exception=None):
    """Return a true, non-cacheable 404; API namespaces keep JSON semantics."""
    headers = {
        "X-Robots-Tag": "noindex, nofollow",
        "Cache-Control": "no-store",
    }
    if _is_api_path(request.path):
        return JsonResponse({"error": "not_found"}, status=404, headers=headers)

    locale = _locale(request.path)
    artifact = _artifact_path(locale)
    try:
        content = artifact.read_bytes()
    except OSError:
        content = _fallback_html(locale).encode("utf-8")
    return HttpResponse(
        content,
        status=404,
        content_type="text/html; charset=utf-8",
        headers=headers,
    )
