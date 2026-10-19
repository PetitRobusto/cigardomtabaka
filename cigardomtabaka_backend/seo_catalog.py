"""Public-only build input and canonical metadata shared by export and serving."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from django.conf import settings


FRONTEND = Path(__file__).resolve().parent.parent / 'frontend'
CONTENT_PATH = FRONTEND / 'site-content.json'
CONTENT = json.loads(CONTENT_PATH.read_text(encoding='utf-8'))
LOCALES = ('zh-CN', 'ru', 'en')


def cigar_slug(cigar):
    """Match frontend generateCigarSlugFromParts; never use this for brand logos."""
    parts = [cigar.brand, cigar.english_name, cigar.release_type, cigar.release_name]
    value = unicodedata.normalize('NFD', ' '.join(p for p in parts if p).lower())
    value = ''.join(c for c in value if not '\u0300' <= c <= '\u036f')
    value = re.sub(r'[^\w\s-]', '', value, flags=re.ASCII)
    value = re.sub(r'-+', '-', re.sub(r'\s+', '-', value)).strip('-')
    return value[:100].rstrip('-') or 'cigar'


def cigar_path(cigar):
    return f'/cigar/{cigar.pk}/{cigar_slug(cigar)}'


def prefix(locale):
    return '' if locale == 'zh-CN' else f'/{locale}'


def content_digest():
    return hashlib.sha256(CONTENT_PATH.read_bytes()).hexdigest()


def definition(path, locale, kind, title, description, **extra):
    return dict(path=path, locale=locale, kind=kind, title=f'{title} · {CONTENT["name"]}',
                description=description, **extra)


def page_definitions(brands, cigars):
    pages = []
    for locale in LOCALES:
        copy = CONTENT['locales'][locale]
        base = prefix(locale)
        pages.append(definition(base + '/' if base else '/', locale, 'home', copy['home'], copy['description']))
        pages.append(definition(base + '/contacts', locale, 'contacts', copy['contacts'], copy['contactDescription']))
        for slug, editorial in CONTENT['brands'].items():
            if locale not in editorial or slug not in brands:
                continue
            brand = brands[slug]['brand']
            label = f'{brand["name"]} {brand["english_name"]}' if locale == 'zh-CN' else brand['english_name']
            title = f'{label} 雪茄系列与型号资料' if locale == 'zh-CN' else (
                f'Сигары {label} в Москве — серии и форматы' if locale == 'ru' else f'{label} cigars in Moscow — models and formats')
            pages.append(definition(base + f'/brand/{slug}', locale, 'brand', title, editorial[locale], brandSlug=slug))
    for item in cigars.values():
        cigar = item['data']['cigar']
        pages.append(definition(item['path'], 'zh-CN', 'cigar',
                                f'{cigar["brand"]} {cigar["name"] or cigar["english_name"]} {cigar["english_name"]} 雪茄规格',
                                item['note'], cigarId=cigar['id']))
    for page in pages:
        group = [p for p in pages if p['kind'] == page['kind']
                 and p.get('brandSlug') == page.get('brandSlug')
                 and p.get('cigarId') == page.get('cigarId')]
        page['alternates'] = {p['locale']: p['path'] for p in group}
    return pages


def _public_payload(path, origin=None):
    if origin:
        import requests
        if origin.rstrip('/') != CONTENT['origin']:
            raise ValueError('Only the configured public site origin may be used.')
        response = requests.get(CONTENT['origin'] + path, timeout=(3, 20), allow_redirects=False)
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('Public catalogue endpoint must return 200 without redirects.')
        return response.json()
    from django.test import RequestFactory
    from cigars.views import api_brand_list, api_brand_detail, api_cigar_detail
    request = RequestFactory().get(path)
    if path == '/api/brands/':
        response = api_brand_list(request)
    elif path.startswith('/api/brands/'):
        response = api_brand_detail(request, path.split('/')[3])
    else:
        response = api_cigar_detail(request, int(path.split('/')[3]))
    return json.loads(response.content)


def page_payload(snapshot, page):
    if page['kind'] == 'contacts':
        return None
    if page['kind'] == 'home':
        return snapshot['catalog']
    if page['kind'] == 'brand':
        return snapshot['brands'][page['brandSlug']]
    return snapshot['cigars'][str(page['cigarId'])]['data']


def payload_fingerprint(payload):
    facts = {'content': content_digest(), 'payload': payload}
    return hashlib.sha256(json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build_catalog(origin=None):
    from types import SimpleNamespace
    catalog = _public_payload('/api/brands/', origin)
    brands = {slug: _public_payload(f'/api/brands/{slug}/', origin) for slug in CONTENT['brands']}
    cigars = {}
    for target in CONTENT['models']:
        brand = next(value for value in brands.values() if value['brand']['english_name'] == target['brand'])
        matches = [c for section in brand['sections'] for c in section['cigars']
                   if c['english_name'] == target['english_name'] and not c['release_type']]
        if len(matches) != 1:
            raise ValueError(f'Expected one public catalogue model: {target["brand"]} {target["english_name"]}')
        data = _public_payload(f'/api/cigars/{matches[0]["id"]}/', origin)
        cigar = data['cigar']
        if cigar['brand'] != target['brand'] or cigar['english_name'] != target['english_name'] or cigar['release_type'] or cigar['release_name']:
            raise ValueError('Public model identity does not match the configured target.')
        entity = SimpleNamespace(pk=cigar['id'], **cigar)
        cigars[str(cigar['id'])] = dict(path=cigar_path(entity), note=target['note'], data=data)
    snapshot = dict(schemaVersion=1, contentDigest=content_digest(), catalog=catalog, brands=brands, cigars=cigars)
    snapshot['fingerprints'] = {p['path']: payload_fingerprint(page_payload(snapshot, p)) for p in page_definitions(brands, cigars)}
    _check_public(snapshot)
    return snapshot


def _check_public(value):
    forbidden = {'price', 'price_cny', 'price_ref', 'cost', 'cost_cny', 'unit_cost_cny',
                 'balance', 'password', 'token', 'customer', 'customers', 'stock', 'in_stock'}
    if isinstance(value, dict):
        if forbidden.intersection(value):
            raise ValueError('Private or commercial fields cannot be exported into public HTML.')
        for nested in value.values():
            _check_public(nested)
    elif isinstance(value, list):
        for nested in value:
            _check_public(nested)


def live_fingerprint(page):
    """Compare the exact public payload, not unrelated database rows or timestamps."""
    if page['kind'] == 'contacts':
        return payload_fingerprint(None)
    if page['kind'] == 'home':
        path = '/api/brands/'
    elif page.get('brandSlug'):
        path = f'/api/brands/{page["brandSlug"]}/'
    else:
        path = f'/api/cigars/{page["cigarId"]}/'
    return payload_fingerprint(_public_payload(path))


def read_definitions():
    path = FRONTEND / 'seo' / 'pages.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []


def build_directory():
    return Path(getattr(settings, 'SEO_BUILD_DIR', settings.BASE_DIR / '.seo-rendered'))
