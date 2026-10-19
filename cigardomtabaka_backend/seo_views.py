"""Public SEO responses; all business and token access stays in existing views."""
import hashlib
import json
import re
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import render

from cigars.models import Brand, Cigar
from .seo_catalog import CONTENT, FRONTEND, build_directory, cigar_path, content_digest, live_fingerprint, read_definitions


PRIVATE_PATHS = {
    '/login', '/inventory', '/inventory/purchases', '/sales', '/sales/receipts', '/sales/customers',
    '/accounting', '/accounting/day1', '/accounting/reports/monthly', '/accounting/reports/contributions',
    '/reports/monthly', '/reports/contributions', '/prices', '/prices/alerts', '/privnote', '/help',
}


def _response(body, *, status=200, public=False, content_type='text/html; charset=utf-8'):
    response = HttpResponse(body, status=status, content_type=content_type)
    response['X-Robots-Tag'] = 'index, follow' if public else 'noindex, nofollow'
    response['Cache-Control'] = 'no-cache' if public else 'private, no-store'
    return response


def _page(path):
    return next((p for p in read_definitions() if p['path'] == path), None)


def _rendered(page):
    """Return only an intact, matching build. Never serve stale facts after deletion."""
    directory = build_directory()
    try:
        manifest = json.loads((directory / 'manifest.json').read_text())
        if manifest.get('schemaVersion') != 1 or manifest.get('contentDigest') != content_digest():
            return None
        if manifest.get('definitionsDigest') != hashlib.sha256((FRONTEND / 'seo' / 'pages.json').read_bytes()).hexdigest():
            return None
        entry = manifest['pages'].get(page['path'])
        if not entry or not re.fullmatch(r'[a-f0-9]{64}\.html', entry['file']):
            return None
        if entry.get('fingerprint') != live_fingerprint(page):
            return None
        body = (directory / entry['file']).read_bytes()
        return body if hashlib.sha256(body).hexdigest() == entry['sha256'] else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def spa_entry(request):
    original = request.path
    path = original.rstrip('/') or '/'
    if path in ('/ru', '/en'):
        path += '/'
    page = _page(path)
    public = page is not None
    title = CONTENT['name']
    description = ''
    valid = path in PRIVATE_PATHS or bool(re.fullmatch(r'/p/[^/]+|/prices/cigar/\d+(?:/[^/]+)?', path))
    # Resolve entities before consulting the static build, including soft deletions.
    if match := re.fullmatch(r'/brand/([^/]+)', path):
        brand = Brand.objects.filter(slug=match[1]).first()
        valid = brand is not None
        public = valid
        if brand:
            title = f'{brand.name or brand.english_name} {brand.english_name} 雪茄目录 · {CONTENT["name"]}'
            description = f'{brand.name or brand.english_name} {brand.english_name} 雪茄型号与规格资料。{CONTENT["locales"]["zh-CN"]["notice"]}'
    elif match := re.fullmatch(r'/cigar/(\d+)(?:/[^/]+)?', path):
        cigar = Cigar.objects.filter(pk=int(match[1]), deleted_at__isnull=True).first()
        valid = cigar is not None
        public = valid
        if cigar:
            canonical = cigar_path(cigar)
            if path != canonical and request.method in ('GET', 'HEAD'):
                suffix = '?' + request.META['QUERY_STRING'] if request.META.get('QUERY_STRING') else ''
                return HttpResponsePermanentRedirect(canonical + suffix)
            title = f'{cigar.brand} {cigar.name or cigar.english_name} {cigar.english_name} 雪茄规格 · {CONTENT["name"]}'
            description = f'{cigar.brand} {cigar.english_name} 型号资料。{CONTENT["locales"]["zh-CN"]["notice"]}'
    elif page:
        valid = True
        if page.get('brandSlug'):
            valid = Brand.objects.filter(slug=page['brandSlug']).exists()
        public = valid

    if valid and request.method in ('GET', 'HEAD'):
        host = request.get_host().split(':')[0].lower()
        if host == 'www.cigardomtabaka.com':
            return HttpResponsePermanentRedirect(CONTENT['origin'] + path + ('?' + request.META['QUERY_STRING'] if request.META.get('QUERY_STRING') else ''))
        if original != path:
            return HttpResponsePermanentRedirect(path + ('?' + request.META['QUERY_STRING'] if request.META.get('QUERY_STRING') else ''))

    if public and page and request.method in ('GET', 'HEAD'):
        body = _rendered(page)
        if body is not None:
            response = _response(body, public=True)
            response['X-CDT-Rendering'] = 'prerendered'
            return response

    if not valid:
        title = '页面不存在 · CigarDomTabaka'
        page = None
        public = False
    elif page:
        title, description = page['title'], page['description']
    response = render(request, 'spa_index.html', {
        'debug': settings.DEBUG, 'site_title': title, 'site_description': description,
        'status_code': 200 if valid else 404,
        'site_lang': page['locale'] if page else 'zh-CN', 'seo_public': public,
        'canonical_url': CONTENT['origin'] + path if public else '',
        'seo_alternates': [{'lang': lang, 'url': CONTENT['origin'] + url} for lang, url in (page or {}).get('alternates', {}).items()],
        'seo_default': CONTENT['origin'] + page['alternates']['zh-CN'] if page and 'zh-CN' in page['alternates'] else '',
    }, status=200 if valid else 404)
    response['X-Robots-Tag'] = 'index, follow' if public else 'noindex, nofollow'
    response['Cache-Control'] = 'no-cache' if public else 'private, no-store'
    response['X-CDT-Rendering'] = 'spa'
    return response


def robots(request):
    return HttpResponse(f'User-agent: *\nAllow: /\n\nSitemap: {CONTENT["origin"]}/sitemap.xml\n', content_type='text/plain; charset=utf-8')


def sitemap(request):
    urls = []
    for page in read_definitions():
        if page.get('brandSlug') and not Brand.objects.filter(slug=page['brandSlug']).exists():
            continue
        if page.get('cigarId'):
            cigar = Cigar.objects.filter(pk=page['cigarId'], deleted_at__isnull=True).first()
            if not cigar or cigar_path(cigar) != page['path']:
                continue
        urls.append(f'<url><loc>{escape(CONTENT["origin"] + page["path"])}</loc></url>')
    return HttpResponse('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(urls) + '</urlset>', content_type='application/xml; charset=utf-8')


class PrivateIndexingMiddleware:
    """Hide existing private API/admin resources without changing their access rules."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if re.match(r'^/(?:api|admin|privnote|p)(?:/|$)', request.path):
            response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
