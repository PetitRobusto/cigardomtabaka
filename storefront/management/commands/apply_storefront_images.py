"""Import reviewed storefront images without changing product facts."""
import hashlib
import json
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from cigars.models import Cigar, CigarImage


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_manifest(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CommandError(f"无法读取图片清单：{exc}") from exc
    assets = payload.get("product_assets", payload.get("assets")) if isinstance(payload, dict) else None
    if not isinstance(assets, list) or not assets:
        raise CommandError("图片清单必须包含非空 product_assets 或 assets 数组。")
    return assets


def _media_file(media_root, image, label):
    if not isinstance(image, dict):
        raise CommandError(f"{label} 必须是包含 media_path 的对象。")
    relative = image.get("media_path")
    if not isinstance(relative, str) or not relative.strip():
        raise CommandError(f"{label}.media_path 缺失。")
    portable = PurePosixPath(relative)
    if ("\\" in relative or portable.is_absolute() or portable.as_posix() != relative
            or any(part in {"", ".", ".."} for part in relative.split("/"))):
        raise CommandError(f"{label}.media_path 必须是规范的 MEDIA_ROOT 相对路径：{relative}")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise CommandError(f"{label}.media_path 必须是相对 MEDIA_ROOT 的路径。")
    root = Path(media_root).resolve()
    try:
        resolved = (root / candidate).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CommandError(f"{label} 文件不存在或路径无效：{relative}") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise CommandError(f"{label} 必须是 MEDIA_ROOT 内的文件：{relative}")
    expected_hash = image.get("sha256")
    if expected_hash is not None:
        if not isinstance(expected_hash, str) or _sha256(resolved) != expected_hash.lower():
            raise CommandError(f"{label} SHA-256 不匹配：{relative}")
    return relative, resolved


def _normalize_assets(raw_assets, media_root):
    normalized = []
    seen_paths = set()
    seen_slots = set()
    for index, asset in enumerate(raw_assets):
        label = f"assets[{index}]"
        if not isinstance(asset, dict) or asset.get("status") != "approved":
            raise CommandError(f"{label} 必须是 status=approved 的对象。")
        evidence = asset.get("source_evidence") or {}
        if not isinstance(evidence, dict):
            raise CommandError(f"{label}.source_evidence 必须是对象。")
        brand = asset.get("brand") or evidence.get("brand")
        english_name = asset.get("english_name") or evidence.get("english_name")
        cigar_id = asset.get("cigar_id")
        if (not isinstance(cigar_id, int) or isinstance(cigar_id, bool)
                or not isinstance(brand, str) or not brand.strip()
                or not isinstance(english_name, str) or not english_name.strip()):
            raise CommandError(f"{label} 必须包含 cigar_id、brand 和 english_name 身份。")
        if (("brand" in evidence and evidence["brand"] != brand)
                or ("english_name" in evidence and evidence["english_name"] != english_name)):
            raise CommandError(f"{label} 的 source_evidence 商品身份与条目不一致。")
        release_type = asset.get("release_type", evidence.get("release_type"))
        release_name = asset.get("release_name", evidence.get("release_name"))
        for field in ("release_type", "release_name"):
            if field in asset and field in evidence and asset[field] != evidence[field]:
                raise CommandError(f"{label} 的 source_evidence {field} 与条目不一致。")
        kind = asset.get("image_type")
        box_size = asset.get("box_size")
        if kind == "single":
            if box_size not in (None, 1):
                raise CommandError(f"{label} 单支图片的 box_size 必须为空或 1。")
            box_size = None
            model_type = CigarImage.ImageType.CIGAR
        elif kind == "box":
            if not isinstance(box_size, int) or isinstance(box_size, bool) or box_size <= 0:
                raise CommandError(f"{label} 盒装图片必须包含正数 box_size。")
            model_type = CigarImage.ImageType.PACKAGING
        else:
            raise CommandError(f"{label}.image_type 只允许 single 或 box。")
        if evidence:
            if (evidence.get("cigar_id", cigar_id) != cigar_id
                    or evidence.get("image_type", kind) != kind
                    or evidence.get("box_size", asset.get("box_size")) != asset.get("box_size")):
                raise CommandError(f"{label} 的 source_evidence 身份或图片类型与条目不一致。")
        detail_path, detail_file = _media_file(media_root, asset.get("detail"), f"{label}.detail")
        list_path, list_file = _media_file(media_root, asset.get("list"), f"{label}.list")
        if detail_path == list_path:
            raise CommandError(f"{label} detail 和 list 必须使用不同文件路径。")
        slot = (cigar_id, kind, box_size)
        if slot in seen_slots or detail_path in seen_paths or list_path in seen_paths:
            raise CommandError(f"{label} 与清单中的图片槽位或路径重复。")
        seen_slots.add(slot)
        seen_paths.update((detail_path, list_path))
        normalized.append({
            "cigar_id": cigar_id,
            "brand": brand,
            "english_name": english_name,
            "release_type": release_type,
            "release_name": release_name,
            "kind": kind,
            "box_size": box_size,
            "model_type": model_type,
            "image": detail_path,
            "thumbnail": list_path,
            "image_file": detail_file,
            "thumbnail_file": list_file,
        })
    return normalized


class Command(BaseCommand):
    help = "将已审核商城图片幂等导入 CigarImage；默认只预览。"

    def add_arguments(self, parser):
        parser.add_argument("manifest", help="已审核 delivery manifest 或 project assets 清单 JSON 路径")
        parser.add_argument("--apply", action="store_true", help="写入图片记录；默认 dry-run")

    def handle(self, *args, **options):
        entries = _normalize_assets(_read_manifest(options["manifest"]), settings.MEDIA_ROOT)
        matched = []
        for entry in entries:
            cigar = Cigar.objects.filter(pk=entry["cigar_id"], deleted_at__isnull=True).first()
            if (cigar is None or cigar.brand != entry["brand"]
                    or cigar.english_name != entry["english_name"]
                    or (entry["release_type"] is not None and cigar.release_type != entry["release_type"])
                    or (entry["release_name"] is not None and cigar.release_name != entry["release_name"])):
                raise CommandError(
                    "商品身份未能唯一核对："
                    f"{entry['brand']} / {entry['english_name']}（清单 id={entry['cigar_id']}）。"
                )
            matched.append(cigar)

        paths = [path for entry in entries for path in (entry["image"], entry["thumbnail"])]
        existing_by_path = {}
        for row in CigarImage.objects.filter(image__in=paths):
            if row.image in existing_by_path:
                raise CommandError(f"数据库中图片路径重复，拒绝导入：{row.image}")
            existing_by_path[row.image] = row
        for entry in entries:
            for path in (entry["image"], entry["thumbnail"]):
                existing = existing_by_path.get(path)
                if existing and existing.cigar_id != entry["cigar_id"]:
                    raise CommandError(f"图片路径已属于另一商品，拒绝改绑：{path}")

        if options["apply"]:
            database_name = str(connection.settings_dict["NAME"])
            if not settings.DEBUG:
                raise CommandError("DEBUG=False 时拒绝执行图片写入。")
            if Path(database_name).name == "cigars.db":
                raise CommandError("拒绝向正式数据库 cigars.db 写入图片记录。")
            self._apply(entries)
            self.stdout.write(self.style.SUCCESS(f"已幂等导入 {len(entries)} 张商城图片。"))
        else:
            self.stdout.write(f"dry-run：身份、图片文件和路径均已核验；将导入 {len(entries)} 张图片。")

    @staticmethod
    def _apply(entries):
        target_ids = {entry["cigar_id"] for entry in entries}
        primary_by_cigar = {}
        for entry in entries:
            # Single cigar photography is the product primary; box photos remain available as alternatives.
            if entry["kind"] == "single":
                primary_by_cigar[entry["cigar_id"]] = entry["image"]
            else:
                primary_by_cigar.setdefault(entry["cigar_id"], entry["image"])
        with transaction.atomic():
            CigarImage.objects.filter(cigar_id__in=target_ids, is_primary=True).update(is_primary=False)
            for entry in entries:
                is_primary = primary_by_cigar.get(entry["cigar_id"]) == entry["image"]
                CigarImage.objects.update_or_create(
                    image=entry["image"],
                    defaults={
                        "cigar_id": entry["cigar_id"],
                        "thumbnail": entry["thumbnail"],
                        "image_type": entry["model_type"],
                        "box_size": entry["box_size"],
                        "order": -200 if entry["kind"] == "single" else -190,
                        "is_primary": is_primary,
                    },
                )
