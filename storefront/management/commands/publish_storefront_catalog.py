"""Publish the reviewed catalog without importing development business data."""

import io
import json
from pathlib import Path
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from cigars.models import CigarImage
from storefront.languages import HOME_COPY, LOCALES
from storefront.management.commands.apply_storefront_images import (
    Command as ImageCommand, _normalize_assets, _read_manifest,
)
from storefront.management.commands.prepare_storefront_localizations import (
    MANIFEST_RELATIVE_PATH, _brand_translation, _product_translation, _verified_products,
)
from storefront.models import ProductListing, StoreTranslation


class Command(BaseCommand):
    help = '发布已审核清单的商城图片、翻译和缺失上架记录；默认只读预览，不写价格或库存。'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--confirm-production', action='store_true')

    def _guard_apply(self, confirmed):
        name = str(connection.settings_dict.get('NAME') or '')
        path = Path(name).resolve()
        if (not confirmed or settings.DEBUG or connection.vendor != 'sqlite'
                or path.name != 'cigars.db' or not path.is_file()):
            raise CommandError('--apply 需要 --confirm-production、DEBUG=False 和真实 SQLite cigars.db。')

    def handle(self, *args, **options):
        applying = options['apply']
        if applying:
            self._guard_apply(options['confirm_production'])
        manifest = Path(settings.BASE_DIR) / MANIFEST_RELATIVE_PATH
        # One transaction includes validation and every content write. An image
        # failure must not leave newly published translations or listings behind.
        with transaction.atomic():
            cigars, brands = _verified_products(manifest)
            raw_assets = _read_manifest(manifest)
            for asset in raw_assets:
                for kind in ('detail', 'list'):
                    image = asset.get(kind)
                    checksum = image.get('sha256') if isinstance(image, dict) else None
                    if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', checksum):
                        raise CommandError('生产发布的每张图片必须有完整 SHA-256。')
            entries = _normalize_assets(raw_assets, settings.MEDIA_ROOT)
            # Reuse the existing full path ownership/release/duplicate checks;
            # its development-only --apply gate remains unchanged.
            ImageCommand(stdout=io.StringIO()).handle(manifest=str(manifest), apply=False)

            translations = []
            for locale in LOCALES:
                translations.append(('home', 'home', locale, HOME_COPY[locale]))
                translations.extend(('brand', brand.slug, locale, _brand_translation(brand, locale))
                                    for brand in brands.values())
                translations.extend(('product', str(cigar.pk), locale, _product_translation(cigar, locale))
                                    for cigar in cigars)
            existing_translations = set(StoreTranslation.objects.values_list('kind', 'key', 'locale'))
            existing_listings = set(ProductListing.objects.filter(cigar_id__in=[c.pk for c in cigars])
                                    .values_list('cigar_id', flat=True))
            new_translations = [row for row in translations if row[:3] not in existing_translations]
            new_listings = [cigar for cigar in cigars if cigar.pk not in existing_listings]
            counts = {
                'mode': 'apply' if applying else 'dry-run',
                'products': len(cigars), 'brands': len(brands), 'images': len(entries),
                'images_create': len(entries) - CigarImage.objects.filter(image__in=[e['image'] for e in entries]).count(),
                'translations_create': len(new_translations),
                'translations_preserve': len(translations) - len(new_translations),
                'listings_create': len(new_listings), 'listings_preserve': len(existing_listings),
            }
            if applying:
                for kind, key, locale, values in new_translations:
                    row = StoreTranslation(kind=kind, key=key, locale=locale, published=True, **values)
                    row.full_clean()
                    row.save()
                for cigar in new_listings:
                    ProductListing.objects.create(cigar=cigar, published=True)
                ImageCommand._apply(entries)
        self.stdout.write(json.dumps(counts, ensure_ascii=False, sort_keys=True))
