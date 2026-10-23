"""Read-only content readiness audit; never render, publish, or repair records."""
import json
import re
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from storefront.catalog import build_pages
from storefront.models import StoreSettings


PLACEHOLDER = re.compile(r"test[\s_-]*preview|测试预览|合成占位|тестов[а-яё]*\s+предпросмотр", re.IGNORECASE)
RULES = {
    "no_pages": ("error", "没有可公开页面；先核实并发布首页及对应内容。"),
    "missing_home": ("error", "中文首页 / 尚未公开；核实首页内容并发布，旧目录页面不能代替商城首页。"),
    "placeholder_content": ("error", "替换测试占位文案，核实后再发布；不要自动生成商品事实。"),
    "missing_metadata": ("error", "补齐页面标题和搜索摘要。"),
    "missing_home_body": ("error", "补齐首页正文并核实发布。"),
    "missing_body": ("warning", "核查商品正文是否足以解释商品；旧目录不要仅为字数补文案。"),
    "minimal_product_body": ("warning", "正文仅重复名称或摘要，请人工检查是否缺少有价值的商品资料。"),
    "empty_brand": ("warning", "品牌列表为空；确认保留资料页的价值，不自动删除历史 URL。"),
    "orphan_product": ("warning", "商品未出现在首页、目录或品牌列表；核查是否需要资料归档入口。"),
    "translation_fallback": ("warning", "页面使用翻译回退内容，可浏览但不收录；如需收录，应核实并发布目标语言内容。"),
    "store_details_unverified": ("warning", "门店资料尚未核实；核实后在后台确认。"),
    "missing_store_details": ("warning", "核实并补充门店地址、电话、地图、营业时间或实拍；不得编造。"),
}


def audit_pages(pages, *, details_verified, sample_limit=5):
    findings = defaultdict(list)

    def add(code, path, fields=()):
        findings[code].append({"path": path, "fields": list(fields)})

    if not pages:
        add("no_pages", "/")
    else:
        home = pages.get("/") or {}
        if home.get("kind") != "home" or home.get("locale") != "zh" or home.get("view") == "catalog":
            add("missing_home", "/")
    if not details_verified:
        add("store_details_unverified", "/")
    linked_products = {
        product["path"]
        for page in pages.values()
        if page.get("kind") in {"home", "brand"} and not page.get("filters") and page.get("indexable", True)
        for product in page.get("products", [])
        if product.get("path")
    }
    checked_sites = set()
    locales = {}
    for path, page in sorted(pages.items()):
        locale = page.get("locale")
        totals = locales.setdefault(locale, {"page_count": 0, "indexable_page_count": 0, "fallback_page_count": 0})
        totals["page_count"] += 1
        totals["indexable_page_count"] += bool(page.get("indexable", True))
        fallback = page.get("translation_complete") is False
        totals["fallback_page_count"] += fallback
        if fallback and not page.get("indexable", True):
            add("translation_fallback", path, ["translation_complete", "indexable"])
        # Page 2+ repeats reviewed content; report each underlying page only once.
        if page.get("pagination", {}).get("page", 1) > 1:
            continue
        text = {field: str(page.get(field) or "") for field in ("title", "seo_title", "description", "body")}
        placeholder_fields = [field for field, value in text.items() if PLACEHOLDER.search(value)]
        if placeholder_fields:
            add("placeholder_content", path, placeholder_fields)
        missing = [field for field in ("title", "description") if not text[field].strip()]
        if missing:
            add("missing_metadata", path, missing)
        if not text["body"].strip() and page.get("kind") != "brand" and page.get("view") != "catalog":
            code = "missing_home_body" if page.get("kind") == "home" else "missing_body"
            add(code, path, ["body"])
        elif page.get("kind") == "product" and not placeholder_fields:
            product = page.get("product") or {}
            body = text["body"].strip()
            # A heuristic for editorial review, never an indexability decision.
            if body in {str(product.get("name") or "").strip(), text["description"].strip()}:
                add("minimal_product_body", path, ["body"])
        if page.get("kind") == "brand" and not page.get("total_products", len(page.get("products", []))):
            add("empty_brand", path)
        if page.get("kind") == "product" and page.get("indexable", True) and path not in linked_products:
            add("orphan_product", path)
        if locale not in checked_sites:
            checked_sites.add(locale)
            site = page.get("site") or {}
            if PLACEHOLDER.search(str(site.get("name") or "")):
                add("placeholder_content", path, ["site.name"])
            fields = [key for key in ("address", "phone", "map_url", "hours", "photo") if not site.get(key)]
            if fields:
                add("missing_store_details", path, ["site." + key for key in fields])
    issues = []
    for code in sorted(findings):
        severity, action = RULES[code]
        matches = findings[code]
        issues.append({"code": code, "severity": severity, "count": len(matches),
                       "action": action, "samples": matches[:sample_limit]})
    counts = {level: sum(issue["count"] for issue in issues if issue["severity"] == level)
              for level in ("error", "warning")}
    return {"schema_version": 1, "page_count": len(pages),
            "indexable_page_count": sum(total["indexable_page_count"] for total in locales.values()),
            "locales": dict(sorted(locales.items())), "ready": counts["error"] == 0,
            "counts": counts, "issues": issues}


class Command(BaseCommand):
    help = "只读检查商城 SEO 内容准备情况；不生成内容、不渲染、不发布、不修改数据。"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="输出稳定结构的 JSON 报告。")
        parser.add_argument("--strict", action="store_true", help="发现明确内容阻塞项时以非零状态退出；警告不阻塞。")
        parser.add_argument("--sample-limit", type=int, default=5, help="每类问题最多显示的样例数（默认 5）。")

    def handle(self, *args, **options):
        if options["sample_limit"] < 1:
            raise CommandError("--sample-limit 必须大于 0。")
        report = audit_pages(build_pages(),
                             details_verified=StoreSettings.objects.filter(pk=1, details_verified=True).exists(),
                             sample_limit=options["sample_limit"])
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            counts = report["counts"]
            self.stdout.write(f"检查 {report['page_count']} 页，其中 {report['indexable_page_count']} 页允许收录："
                              f"{counts['error']} 个阻塞项，{counts['warning']} 个待核查项。")
            for locale, totals in report["locales"].items():
                self.stdout.write(f"  {locale}: {totals['page_count']} 页，允许收录 {totals['indexable_page_count']} 页，"
                                  f"翻译回退 {totals['fallback_page_count']} 页。")
            for issue in report["issues"]:
                self.stdout.write(f"[{issue['severity']}] {issue['code']} ({issue['count']}): {issue['action']}")
                for sample in issue["samples"]:
                    suffix = f" ({', '.join(sample['fields'])})" if sample["fields"] else ""
                    self.stdout.write(f"  {sample['path']}{suffix}")
            self.stdout.write("仅检查当前内容读模型；不代表生产已启用、渲染成功或搜索引擎已收录。")
        if options["strict"] and not report["ready"]:
            raise CommandError("SEO 内容存在明确阻塞项，请核查报告。")
