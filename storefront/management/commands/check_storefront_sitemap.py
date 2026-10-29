"""Read-only release gate for the live, dynamically generated sitemap."""

from urllib.parse import urlsplit
from xml.etree import ElementTree

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from storefront.catalog import build_pages
from storefront.images import product_image_urls
from storefront.models import RefreshState


SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
IMAGE_NS = "{http://www.google.com/schemas/sitemap-image/1.1}"


class Command(BaseCommand):
    help = "只读核对实时 sitemap 与当前可索引页面、展示图片完全一致。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--require-path", action="append", default=[], metavar="PATH",
            help="要求该已发布页面出现在 sitemap；可重复指定，供新商品上线验收使用。",
        )

    def handle(self, *args, **options):
        state_before = RefreshState.objects.filter(pk=1).values("revision", "processed_revision").first()
        pages = build_pages()
        expected = {path for path, payload in pages.items() if payload.get("indexable")}

        required = set(options["require_path"])
        invalid_required = sorted(path for path in required if path not in expected)
        if invalid_required:
            raise CommandError(
                "要求的路径当前未发布或不可索引（可能缺少翻译、已下架或不是规范路径）："
                + ", ".join(invalid_required)
            )

        origin = settings.STOREFRONT_ORIGIN.rstrip("/")
        parsed_origin = urlsplit(origin)
        response = Client().get(
            "/sitemap-storefront.xml", HTTP_HOST=parsed_origin.netloc,
            secure=parsed_origin.scheme == "https",
        )
        if response.status_code != 200 or "xml" not in response.get("Content-Type", "").lower():
            raise CommandError(
                f"实时 sitemap 返回异常：HTTP {response.status_code}，"
                f"Content-Type={response.get('Content-Type', '')!r}。"
            )
        try:
            root = ElementTree.fromstring(response.content)
            if root.tag != SITEMAP_NS + "urlset":
                raise ValueError("根元素不是 sitemap urlset")
            entries = root.findall(f"{SITEMAP_NS}url")
            locations = [node.findtext(f"{SITEMAP_NS}loc") for node in entries]
            if any(not location for location in locations):
                raise ValueError("sitemap 包含空 URL")
        except (ElementTree.ParseError, ValueError) as error:
            raise CommandError(f"实时 sitemap XML 无效：{error}") from error

        if len(set(locations)) != len(locations):
            raise CommandError("实时 sitemap 含重复 URL。")

        actual = set()
        for location in locations:
            parsed = urlsplit(location)
            if (parsed.scheme != parsed_origin.scheme or parsed.netloc != parsed_origin.netloc
                    or parsed.fragment or not parsed.path.startswith("/")
                    or location != origin + parsed.path + ("?" + parsed.query if parsed.query else "")):
                raise CommandError(f"实时 sitemap 含非规范或非本站 URL：{location}")
            actual.add(parsed.path + ("?" + parsed.query if parsed.query else ""))

        missing = sorted(expected - actual)
        unwanted = sorted(actual - expected)
        if missing or unwanted:
            details = []
            if missing:
                details.append(f"缺少 {len(missing)} 个可索引页面，样例 {missing[:10]}")
            if unwanted:
                details.append(f"含 {len(unwanted)} 个不应收录页面，样例 {unwanted[:10]}")
            raise CommandError("sitemap 与当前可索引页面不一致：" + "；".join(details))

        image_count = 0
        for node, location in zip(entries, locations, strict=True):
            path = location.removeprefix(origin)
            expected_images = set(product_image_urls(pages[path], origin))
            images = []
            for image in node.findall(f"{IMAGE_NS}image"):
                image_locations = image.findall(f"{IMAGE_NS}loc")
                if len(image_locations) != 1 or not image_locations[0].text:
                    raise CommandError(f"sitemap 图片缺少唯一有效 loc：{path}")
                images.append(image_locations[0].text)
            if len(images) != len(set(images)):
                raise CommandError(f"sitemap 含重复图片：{path}")
            missing_images = sorted(expected_images - set(images))
            unwanted_images = sorted(set(images) - expected_images)
            if missing_images or unwanted_images:
                raise CommandError(
                    f"sitemap 图片与当前展示集合不一致：{path}；"
                    f"缺少 {missing_images[:5]}；不应包含 {unwanted_images[:5]}"
                )
            image_count += len(images)

        state_after = RefreshState.objects.filter(pk=1).values("revision", "processed_revision").first()
        if state_before != state_after or (state_after and state_after["revision"] != state_after["processed_revision"]):
            raise CommandError("Sitemap 验收期间商城内容发生变化或仍待校验，请重新渲染并验收。")

        self.stdout.write(f"Sitemap 验收通过：{len(actual)} 个规范可索引 URL、{image_count} 个图片关联，集合完全一致。")
