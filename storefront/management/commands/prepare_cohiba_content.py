"""Prepare the owner's four confirmed box prices and reviewed trilingual copy."""

import json
import hashlib
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from cigars.models import Brand, Cigar, CigarPrice
from storefront.management.commands.prepare_storefront_localizations import (
    _brand_translation, _product_translation,
)
from storefront.models import ProductListing, StoreTranslation


CONTENT_PATH = Path(__file__).resolve().parents[2] / "cohiba_content.json"
LEGACY_COPY_FIELDS = ("title", "description", "body", "aliases")
COPY_FIELDS = (*LEGACY_COPY_FIELDS, "seo_title")
# Scope of the owner's approval, including exact packaging. Never infer prices.
APPROVED = {
    102: ("Genios", 140, 52, 10, "130000.00"),
    103: ("Magicos", 115, 52, 10, "108000.00"),
    97: ("Siglo II", 129, 42, 25, "112000.00"),
    98: ("Siglo III", 155, 42, 25, "158000.00"),
}


def normalize_copy(values):
    """Accept reviewed four-field manifests while making the override explicit."""
    if (not isinstance(values, dict)
            or set(values) not in (set(LEGACY_COPY_FIELDS), set(COPY_FIELDS))
            or not all(isinstance(values[field], str) and values[field].strip() for field in LEGACY_COPY_FIELDS)):
        raise CommandError("翻译缺少标题、摘要、正文或别名。")
    seo_title = values.setdefault("seo_title", "")
    if not isinstance(seo_title, str) or len(seo_title) > 180:
        raise CommandError("搜索标题必须是最多 180 个字符的字符串，可留空。")
    return values


def read_content():
    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    products = content["products"]
    if len(products) != 4 or {p["id"] for p in products} != set(APPROVED):
        raise CommandError("清单必须恰好包含获准的四款商品。")
    brand = content["brand"]
    if (brand["english_name"], brand["slug"]) != ("Cohiba", "cohiba"):
        raise CommandError("清单品牌不匹配。")
    for product in products:
        actual = tuple(product[k] for k in (
            "english_name", "length", "ring_gauge", "box_size", "retail_price_rub",
        ))
        if actual != APPROVED[product["id"]] or product["release_type"] or product["release_name"]:
            raise CommandError(f"清单 id={product['id']} 不符合已确认的型号、尺寸、盒规或价格。")
    for entry in [brand, *products]:
        if set(entry["translations"]) != {"ru", "zh", "en"}:
            raise CommandError("清单必须包含完整的俄语、中文和英文内容。")
        for values in entry["translations"].values():
            normalize_copy(values)
    return content


class Command(BaseCommand):
    help = "预览高希霸资料与确认盒价；--content-only 跳过价格，--apply 仅写开发库。"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--content-only", action="store_true", help="只更新资料，不读取或写入定价。")
        parser.add_argument("--include-supporting", action="store_true", help="同时核对 BHK 52/56 品牌页依赖资料，需 --content-only。")
        parser.add_argument("--publish-supporting", action="store_true", help="发布已核对的 BHK 资料，仅用于开发预览。")

    def _guard_apply(self):
        name = str(connection.settings_dict.get("NAME") or "")
        if not settings.DEBUG or connection.vendor != "sqlite" or not name:
            raise CommandError("--apply 仅允许 DEBUG=True 的明确 SQLite 开发数据库。")
        # Django's isolated SQLite test database is safe; other SQLite URIs are
        # rejected rather than treating their query strings as filesystem paths.
        if name == ":memory:" or re.fullmatch(r"file:memorydb_[A-Za-z0-9_]+\?mode=memory&cache=shared", name):
            return
        if name.startswith("file:"):
            raise CommandError("--apply 拒绝无法核对真实路径的 SQLite URI。")
        path = Path(name)
        resolved = path.resolve()
        production = Path(settings.BASE_DIR) / "cigars.db"
        if (path.name.casefold() == "cigars.db" or resolved.name.casefold() == "cigars.db"
                or not resolved.is_file()
                or (production.exists() and resolved.samefile(production))):
            raise CommandError("--apply 拒绝生产 cigars.db、其链接或不存在的数据库。")

    def _translation(self, kind, key, locale, values, baseline):
        row = StoreTranslation.objects.select_for_update().filter(kind=kind, key=key, locale=locale).first()
        before = {field: getattr(row, field) for field in COPY_FIELDS} if row else None
        if row and before == values:
            return row, False, {"kind": kind, "key": key, "locale": locale, "action": "unchanged", "published": row.published}
        previous_hashes = json.loads(CONTENT_PATH.with_name('cohiba_content_previous_hashes.json').read_text())
        versions = [before] if before is not None else []
        # A legacy hash says nothing about seo_title: accept it only when this
        # newly added field is empty, never to overwrite an editor's custom title.
        if before is not None and not before['seo_title']:
            versions.append({field: before[field] for field in LEGACY_COPY_FIELDS})
        previous_reviewed = any(
            hashlib.sha256(json.dumps(version, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            in previous_hashes.get(f'{kind}/{key}/{locale}', []) for version in versions
        )
        if row and (row.hours or (not previous_reviewed and (row.seo_title or row.aliases or any(getattr(row, field) != baseline[field]
                                                   for field in ("title", "description", "body"))))):
            raise CommandError(f"{kind}/{key}/{locale} 已有自定义内容；整批停止，不覆盖。")
        if row is None:
            row = StoreTranslation(kind=kind, key=key, locale=locale, published=False)
        for field, value in values.items():
            setattr(row, field, value)
        row.full_clean()
        return row, True, {
            "kind": kind, "key": key, "locale": locale,
            "action": "update" if row.pk else "create_draft", "published": row.published,
            "before": before, "after": values,
        }

    def handle(self, *args, **options):
        applying = options["apply"]
        if options['include_supporting'] and not options['content_only']:
            raise CommandError('--include-supporting 必须同时使用 --content-only。')
        if options['publish_supporting'] and not options['include_supporting']:
            raise CommandError('--publish-supporting 必须同时使用 --include-supporting。')
        if applying:
            self._guard_apply()
        try:
            content = read_content()
            with transaction.atomic():
                brand = Brand.objects.select_for_update().filter(english_name="Cohiba", slug="cohiba").first()
                if brand is None:
                    raise CommandError("缺少 Cohiba/cohiba 正式品牌记录。")
                updates, translations, prices = [], [], []
                for locale, values in content["brand"]["translations"].items():
                    row, changed, report = self._translation("brand", brand.slug, locale, values, _brand_translation(brand, locale))
                    translations.append(report)
                    if changed:
                        updates.append((row, COPY_FIELDS))

                for entry in content["products"]:
                    cigar = Cigar.objects.select_for_update().filter(pk=entry["id"], deleted_at__isnull=True).first()
                    if (cigar is None or cigar.brand != "Cohiba"
                            or any(getattr(cigar, field) != entry[field] for field in ("english_name", "length", "ring_gauge"))
                            or (cigar.release_type or "") != entry["release_type"]
                            or (cigar.release_name or "") != entry["release_name"]):
                        raise CommandError(f"商品 id={entry['id']} 身份或尺寸不符；整批停止。")
                    for locale, values in entry["translations"].items():
                        row, changed, report = self._translation("product", str(cigar.pk), locale, values, _product_translation(cigar, locale))
                        translations.append(report)
                        if changed:
                            updates.append((row, COPY_FIELDS))

                    if options['content_only']:
                        continue
                    price = CigarPrice.objects.select_for_update().filter(cigar=cigar, box_size=entry["box_size"]).first()
                    target = Decimal(entry["retail_price_rub"])
                    before = str(price.retail_price_rub) if price and price.retail_price_rub is not None else None
                    action = "unchanged"
                    if price is None:
                        if (cigar.pk, entry["box_size"]) != (102, 10):
                            raise CommandError(f"id={cigar.pk} 缺少 {entry['box_size']} 支盒定价；不得虚构人民币批发价。")
                        # Explicit owner confirmation in this task, not FX or cost.
                        price = CigarPrice(cigar=cigar, box_size=10, wholesale_price=11000,
                                           retail_price=None, retail_price_rub=target,
                                           is_active=True, can_preorder=False)
                        action = "create"
                    elif price.retail_price_rub is None:
                        price.retail_price_rub = target
                        action = "update"
                    elif price.retail_price_rub != target:
                        raise CommandError(f"id={cigar.pk}/{entry['box_size']} 支盒已有不同 RUB 价格；整批停止。")
                    if action != "unchanged":
                        price.full_clean()
                        updates.append((price, ("retail_price_rub",)))
                    listing = ProductListing.objects.filter(cigar=cigar).first()
                    prices.append({
                        "id": cigar.pk, "english_name": cigar.english_name,
                        "box_size": price.box_size, "action": action,
                        "before_rub_per_box": before, "after_rub_per_box": str(target),
                        "created_wholesale_cny_per_box": 11000 if action == "create" else None,
                        "price_active": price.is_active,
                        "listing_published": bool(listing and listing.published),
                        "listing_withdrawn": bool(listing and listing.withdrawn),
                    })

                if options['include_supporting']:
                    supporting = json.loads(CONTENT_PATH.with_name('cohiba_supporting_content.json').read_text())['products']
                    expected = {105: ('BHK 52', 119, 52), 107: ('BHK 56', 166, 56)}
                    if len(supporting) != 2 or {item['id'] for item in supporting} != set(expected):
                        raise CommandError('BHK 资料清单范围不符。')
                    for entry in supporting:
                        if tuple(entry[k] for k in ('english_name', 'length', 'ring_gauge')) != expected[entry['id']]:
                            raise CommandError('BHK 资料规格与核实来源不符。')
                        cigar = Cigar.objects.select_for_update().filter(pk=entry['id'], deleted_at__isnull=True).first()
                        if (not cigar or cigar.brand != 'Cohiba' or cigar.release_type or cigar.release_name
                                or any(getattr(cigar, field) != entry[field] for field in ('english_name', 'length', 'ring_gauge'))):
                            raise CommandError(f"BHK 商品 id={entry['id']} 身份不符；整批停止。")
                        if set(entry['translations']) != {'zh', 'ru', 'en'}:
                            raise CommandError('BHK 资料须包含三语。')
                        for locale, values in entry['translations'].items():
                            normalize_copy(values)
                            row, changed, report = self._translation('product', str(cigar.pk), locale, values, _product_translation(cigar, locale))
                            if options['publish_supporting'] and not row.published:
                                row.published = True
                                changed = True
                                report['action'] = 'publish_reviewed'
                                report['published'] = True
                            row.full_clean()
                            translations.append(report)
                            if changed:
                                updates.append((row, (*COPY_FIELDS, 'published')))

                # All identities, content and financial conflicts have been checked
                # before the first write. Signals enqueue refresh only on commit.
                if applying:
                    for row, fields in updates:
                        if row.pk:
                            row.save(update_fields=[*fields, "updated_at"])
                        else:
                            row.save()
        except (ValidationError, OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(f"高希霸内容校验失败，未写入：{exc}") from exc
        self.stdout.write(json.dumps({
            "mode": "apply" if applying else "dry-run", "changed_rows": len(updates),
            "content_only": options['content_only'],
            "translations": translations, "prices": prices,
            "note": "库存与商品上架状态保持原值；仅 --publish-supporting 可发布 BHK 资料，开发写入不等于生产已上线。",
        }, ensure_ascii=False, indent=2))
