"""The fixed, reviewed SEO-18/19 release; never a runtime source of page copy."""

import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import CommandError


CONTENT_DIR = Path(__file__).with_name('content')
LOCALES = ('zh', 'ru', 'en')
COPY_FIELDS = ('description', 'body')
SPEC_FIELDS = ('length', 'ring_gauge', 'vitola', 'vitola_cn')
IDENTITY_FIELDS = ('brand', 'english_name', 'release_type', 'release_name')


def _read(name):
    return json.loads((CONTENT_DIR / name).read_text(encoding='utf-8'))


def _unique(entries, key):
    result = {entry[key]: entry for entry in entries}
    if len(result) != len(entries):
        raise CommandError(f'清单 {key} 重复；整批停止。')
    return result


def read_release():
    """Validate the entire release before examining or mutating any database row."""
    scope = _read('seo18-scope.json')
    a, b, brands = (_read(name) for name in (
        'seo18-products-a.json', 'seo18-products-b.json', 'seo19-brands.json'))
    if any(document.get('schema_version') != 1 for document in (scope, a, b, brands)):
        raise CommandError('不支持的资料清单版本。')
    products = _unique(a['products'] + b['products'], 'id')
    brand_copy = _unique(brands['brands'], 'slug')
    product_scope = _unique(scope['products'], 'id')
    brand_scope = _unique(scope['brands'], 'slug')
    if (len(product_scope) != 60 or len(brand_scope) != 20
            or set(products) != set(product_scope) or set(brand_copy) != set(brand_scope)):
        raise CommandError('清单必须完整覆盖固定 60 商品和 20 品牌。')
    for key, entry in products.items():
        if entry['english_name'] != product_scope[key]['english_name']:
            raise CommandError(f'商品 {key} 清单身份不一致。')
        slug = entry['brand_slug']
        if slug not in brand_scope or brand_scope[slug]['english_name'] != product_scope[key]['brand']:
            raise CommandError(f'商品 {key} 品牌关联不一致。')
        specs = entry['verified_specs']
        if set(specs) != {'length', 'ring_gauge', 'vitola'}:
            raise CommandError(f'商品 {key} 规格字段不完整。')
        for field in ('length', 'ring_gauge'):
            value = specs[field]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
                raise CommandError(f'商品 {key} 规格无效。')
        if not isinstance(specs['vitola'], str) or len(specs['vitola']) > 100:
            raise CommandError(f'商品 {key} 茄型无效。')
    for slug, entry in brand_copy.items():
        if entry['english_name'] != brand_scope[slug]['english_name']:
            raise CommandError(f'品牌 {slug} 清单身份不一致。')
    for entry in [*products.values(), *brand_copy.values()]:
        if entry['decision'] not in ('update', 'preserve'):
            raise CommandError('存在尚未解决的资料身份/来源阻塞；整批停止。')
        if set(entry['translations']) != set(LOCALES):
            raise CommandError('资料必须完整包含中俄英三语。')
        if not entry['sources']:
            raise CommandError('每个型号/品牌都必须记录来源。')
        for source in entry['sources']:
            url = urlsplit(source['url'])
            if (url.scheme != 'https' or not url.hostname or url.username or url.password
                    or not source['title'] or not source['facts']):
                raise CommandError('资料来源必须是有标题及事实说明的 HTTPS 链接。')
        for values in entry['translations'].values():
            if (set(values) != set(COPY_FIELDS)
                    or not all(isinstance(values[field], str) and values[field].strip() for field in COPY_FIELDS)
                    or len(values['description']) > 400):
                raise CommandError('译文只允许完整的正文和最多 400 字符摘要。')
            if entry['decision'] == 'update':
                links = set(re.findall(r'\[[^\]]+\]\((https://[^)]+)\)', values['body']))
                if not links or not links <= {source['url'] for source in entry['sources']}:
                    raise CommandError('新正文必须引用清单中已核对的来源。')
    corrections = scope['spec_corrections']
    if not set(corrections) <= {str(pk) for pk in products}:
        raise CommandError('规格修正超出本次商品范围。')
    for pk, entry in products.items():
        old = product_scope[pk]['expected_specs']
        correction = corrections.get(str(pk), {})
        if not set(correction) <= set(SPEC_FIELDS):
            raise CommandError('不允许修改规格之外的型号字段。')
        desired = {**old, **correction}
        if any(desired[field] != entry['verified_specs'][field] for field in ('length', 'ring_gauge', 'vitola')):
            raise CommandError(f'商品 {pk} 已核实规格与批准修正不一致。')
    return scope, products, brand_copy
