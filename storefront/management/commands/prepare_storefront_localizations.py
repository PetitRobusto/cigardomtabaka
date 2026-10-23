"""Prepare factual storefront translations for the reviewed image-catalog products."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from cigars.models import Brand, Cigar
from storefront.languages import HOME_COPY, LOCALES, specification_summary
from storefront.models import StoreTranslation


MANIFEST_RELATIVE_PATH = Path("docs/data/storefront-images-20261023.json")
EXPECTED_PRODUCT_COUNT = 60


def _manifest_identities(path: Path) -> dict[int, dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CommandError(f"无法读取商城图片商品清单：{exc}") from exc
    assets = payload.get("assets") if isinstance(payload, dict) else None
    if not isinstance(assets, list) or not assets:
        raise CommandError("商城图片商品清单必须包含非空 assets 数组。")

    identities = {}
    for index, asset in enumerate(assets):
        label = f"assets[{index}]"
        if not isinstance(asset, dict) or asset.get("status") != "approved":
            raise CommandError(f"{label} 必须是 status=approved 的对象。")
        cigar_id = asset.get("cigar_id")
        if not isinstance(cigar_id, int) or isinstance(cigar_id, bool) or cigar_id <= 0:
            raise CommandError(f"{label}.cigar_id 必须是正整数。")
        values = {}
        for field in ("brand", "english_name", "release_type", "release_name"):
            value = asset.get(field, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise CommandError(f"{label}.{field} 必须是字符串。")
            values[field] = value
        if not values["brand"].strip() or not values["english_name"].strip():
            raise CommandError(f"{label} 缺少 brand 或 english_name 身份字段。")
        previous = identities.setdefault(cigar_id, values)
        if previous != values:
            raise CommandError(f"商品 id={cigar_id} 在图片清单中的身份字段不一致。")

    if len(identities) != EXPECTED_PRODUCT_COUNT:
        raise CommandError(
            f"商品清单应包含 {EXPECTED_PRODUCT_COUNT} 个不同商品，实际为 {len(identities)} 个。"
        )
    return identities


def _verified_products(path: Path) -> tuple[list[Cigar], dict[str, Brand]]:
    identities = _manifest_identities(path)
    rows = {
        cigar.pk: cigar
        for cigar in Cigar.objects.filter(pk__in=identities, deleted_at__isnull=True)
    }
    mismatches = []
    for cigar_id, expected in identities.items():
        cigar = rows.get(cigar_id)
        actual = {
            "brand": cigar.brand if cigar else None,
            "english_name": cigar.english_name if cigar else None,
            "release_type": (cigar.release_type or "") if cigar else None,
            "release_name": (cigar.release_name or "") if cigar else None,
        }
        if actual != expected:
            mismatches.append(f"id={cigar_id}: 清单={expected!r} 数据库={actual!r}")
    if mismatches:
        raise CommandError("商品身份核对失败，未写入任何翻译：\n" + "\n".join(mismatches))

    brand_names = {cigar.brand for cigar in rows.values()}
    brands = {brand.english_name: brand for brand in Brand.objects.filter(english_name__in=brand_names)}
    missing_brands = sorted(brand_names - set(brands))
    if missing_brands:
        raise CommandError("缺少正式品牌记录，未写入任何翻译：" + ", ".join(missing_brands))
    return [rows[cigar_id] for cigar_id in sorted(rows)], brands


def _product_translation(cigar: Cigar, locale: str) -> dict[str, str]:
    title = (cigar.name or cigar.english_name) if locale == "zh" else cigar.english_name
    summary = specification_summary(
        name=title,
        vitola=cigar.vitola or "",
        length=cigar.length,
        ring_gauge=cigar.ring_gauge,
        locale=locale,
    )
    return {"title": title, "description": summary or title, "body": summary or title}


def _brand_translation(brand: Brand, locale: str) -> dict[str, str]:
    title = (brand.name or brand.english_name) if locale == "zh" else brand.english_name
    return {"title": title, "description": title, "body": ""}


def _is_exact_home_copy(row: StoreTranslation, locale: str) -> bool:
    return all((getattr(row, field) or "") == HOME_COPY[locale][field]
               for field in ("title", "description", "body")) and not row.aliases and not row.hours


class Command(BaseCommand):
    help = "基于核对过的60款商品事实准备商城三语规格信息；默认dry-run，不生成营销文案。"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="写入核对过的翻译；需 DEBUG 且数据库不是 cigars.db。")

    def _guard_apply(self):
        database_name = str(connection.settings_dict.get("NAME", "") or "")
        normalized_name = database_name.split("?", 1)[0]
        if not settings.DEBUG:
            raise CommandError("--apply 只允许在 DEBUG=True 环境运行。")
        if not normalized_name or Path(normalized_name).name.casefold() == "cigars.db":
            raise CommandError("--apply 拒绝写入 cigars.db 或无法确认的数据库。")

    def handle(self, *args, **options):
        applying = options["apply"]
        if applying:
            self._guard_apply()
        manifest_path = Path(settings.BASE_DIR) / MANIFEST_RELATIVE_PATH
        cigars, brands = _verified_products(manifest_path)

        plan = []
        preserved = 0
        home_to_publish = []
        for locale in LOCALES:
            home = StoreTranslation.objects.filter(kind="home", key="home", locale=locale).first()
            if home is None:
                plan.append(("home_create", locale, None, HOME_COPY[locale]))
            elif not home.published and _is_exact_home_copy(home, locale):
                plan.append(("home_publish", locale, home, None))
                home_to_publish.append(home)
            else:
                preserved += 1

        for brand in brands.values():
            for locale in LOCALES:
                if StoreTranslation.objects.filter(kind="brand", key=brand.slug, locale=locale).exists():
                    preserved += 1
                    continue
                plan.append(("brand_create", locale, brand, _brand_translation(brand, locale)))

        for cigar in cigars:
            for locale in LOCALES:
                if StoreTranslation.objects.filter(kind="product", key=str(cigar.pk), locale=locale).exists():
                    preserved += 1
                    continue
                plan.append(("product_create", locale, cigar, _product_translation(cigar, locale)))

        created = sum(action.endswith("_create") for action, *_ in plan)
        if not applying:
            self.stdout.write(
                f"dry-run：核对 {len(cigars)} 款商品、{len(brands)} 个品牌；"
                f"将创建 {created} 条，保留 {preserved} 条现有内容，"
                f"启用 {len(home_to_publish)} 条与 HOME_COPY 完全一致的首页草稿。"
            )
            return

        actual_created = 0
        actual_preserved = preserved
        published_homes = 0
        with transaction.atomic():
            for action, locale, obj, values in plan:
                if action == "home_publish":
                    # Re-read under the write transaction; preserve concurrent edits.
                    row = StoreTranslation.objects.select_for_update().get(pk=obj.pk)
                    if not row.published and _is_exact_home_copy(row, locale):
                        row.published = True
                        row.save(update_fields=["published", "updated_at"])
                        published_homes += 1
                    else:
                        actual_preserved += 1
                    continue
                kind = action.removesuffix("_create")
                key = "home" if kind == "home" else obj.slug if kind == "brand" else str(obj.pk)
                defaults = {**values, "published": True}
                row, was_created = StoreTranslation.objects.get_or_create(
                    kind=kind, key=key, locale=locale, defaults=defaults,
                )
                if was_created:
                    row.full_clean()
                    actual_created += 1
                else:
                    actual_preserved += 1
        self.stdout.write(
            f"已完成：新建 {actual_created} 条，保留 {actual_preserved} 条现有内容，"
            f"启用 {published_homes} 条匹配首页草稿。"
        )
