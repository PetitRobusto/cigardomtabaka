"""Read-only storefront HTTP acceptance checks; no Django settings or credentials."""

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
import json
import re
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree


# This checker runs without Django. Keep this explicit public URL contract in
# sync with storefront.catalog; staff/secret URLs must never enter a sitemap.
PUBLIC_PATH = re.compile(r"/(?:ru/|en/)?(?:catalog|brand/[^/?#%]+|cigar/[1-9][0-9]*/[^/?#%]+)?")
PRIVATE_PATHS = (
    "/admin/", "/api/", "/login", "/library", "/inventory", "/sales",
    "/accounting", "/reports", "/help", "/prices", "/privnote", "/p/seo-audit",
)
# Internal business paths intentionally aren't advertised in the public file.
ROBOTS_DISALLOWED_PATHS = ("/admin/", "/api/", "/p/seo-audit")


def public_indexable_url(url, origin):
    parsed = urlsplit(url)
    if not url.startswith(origin + "/") or parsed.fragment or not PUBLIC_PATH.fullmatch(parsed.path):
        return False
    # Only catalog/brand pagination is indexable. Repeated home pages, product
    # query variants, filters and page=1 must not enter the sitemap.
    return not parsed.query or (
        (parsed.path.endswith('/catalog') or '/brand/' in parsed.path)
        and re.fullmatch(r"page=(?:[2-9]|[1-9][0-9]+)", parsed.query) is not None
    )


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class Response:
    status: int
    headers: dict
    body: str


def fetch(url, timeout=15):
    request = Request(url, headers={"User-Agent": "CigarDomTabaka-SEO-Audit/1.0"})
    try:
        response = build_opener(NoRedirect).open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError("Response exceeds the 5 MB audit limit")
        headers = {key.lower(): value for key, value in response.headers.items()}
        robot_headers = response.headers.get_all("X-Robots-Tag", [])
        if robot_headers:
            headers["x-robots-tag"] = ", ".join(robot_headers)
        return Response(response.code, headers, body.decode("utf-8", errors="replace"))


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.h1 = ""
        self.lang = ""
        self.capture = None
        self.links = []
        self.metas = []
        self.scripts = []
        self.store_data = []
        self.capture_store_data = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "html":
            self.lang = attrs.get("lang", "")
        if tag in ("title", "h1"):
            self.capture = tag
        if tag == "link":
            self.links.append(attrs)
        if tag == "meta":
            self.metas.append(attrs)
        if tag == "script":
            self.scripts.append(attrs)
            if attrs.get('id') == 'store-data':
                self.store_data.append('')
                self.capture_store_data = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self.capture_store_data = False
        if tag == self.capture:
            self.capture = None

    def handle_data(self, value):
        if self.capture_store_data:
            self.store_data[-1] += value
        if self.capture:
            setattr(self, self.capture, getattr(self, self.capture) + value)


def origin_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Expected an HTTP(S) origin without credentials, path, query or fragment")
    return value.rstrip("/")


def audit(origin, *, www_origin=None, extra_paths=(), representative_pages=False,
          request=fetch, retries=0, retry_delay=2, sleep=time.sleep):
    origin = origin_url(origin)
    if www_origin:
        www_origin = origin_url(www_origin)
        if www_origin == origin:
            raise ValueError("www origin must differ from the canonical origin")
    paths = list(dict.fromkeys(["/", "/ru/", "/en/", *extra_paths]))
    if not isinstance(retries, int) or not 0 <= retries <= 3 or not 0 <= retry_delay <= 10:
        raise ValueError("Use 0–3 retries and a retry delay of 0–10 seconds")
    for path in paths:
        if not path.startswith("/") or urlsplit(urljoin(origin, path)).netloc != urlsplit(origin).netloc or urlsplit(path).fragment:
            raise ValueError("Page paths must stay on the selected origin and have no fragment")
    issues, checked, resource_urls, retried = [], [], [], []

    def problem(url, code, detail):
        issues.append({"url": url, "code": code, "detail": detail})

    def get(url):
        checked.append(url)
        for attempt in range(retries + 1):
            try:
                response = request(url)
                if response.status not in (429, 502, 503, 504) or attempt == retries:
                    return response
                reason = f"HTTP {response.status}"
            except ValueError as error:
                problem(url, "request_failed", str(error))
                return None
            except OSError as error:
                if attempt == retries:
                    problem(url, "request_failed", str(error))
                    return None
                reason = type(error).__name__
            retried.append({"url": url, "retry": attempt + 1, "reason": reason})
            sleep(retry_delay)

    sitemap_url = origin + "/sitemap-storefront.xml"
    sitemap_response = get(sitemap_url)
    locations, sitemap_count = [], 0
    if sitemap_response:
        try:
            root = ElementTree.fromstring(sitemap_response.body)
            namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
            locations = [node.text for node in root.findall(f"{namespace}url/{namespace}loc")]
            sitemap_count = len(locations)
            if (sitemap_response.status != 200 or "xml" not in sitemap_response.headers.get("content-type", "").lower()
                    or root.tag != namespace + "urlset" or not locations
                    or len(set(locations)) != len(locations)
                    or any(not value or not value.startswith(origin + "/") for value in locations)):
                raise ValueError("Expected a nonempty XML urlset of unique canonical-origin URLs")
            for location in locations:
                if not public_indexable_url(location, origin):
                    problem(sitemap_url, "sitemap_nonpublic_url", location)
        except (ElementTree.ParseError, ValueError) as error:
            problem(sitemap_url, "invalid_sitemap", str(error))
            locations = []

    if representative_pages:
        # Draw from this release's public set: a withdrawn hard-coded sample must
        # not break every later deployment, and private URLs are never fetched.
        available = sorted(url[len(origin):] for url in locations if public_indexable_url(url, origin))
        for prefix in ("/", "/ru/", "/en/"):
            paths.append(prefix + "catalog")
            for kind in ("brand/", "cigar/"):
                candidates = [path for path in available if path.startswith(prefix + kind) and not urlsplit(path).query]
                if candidates:
                    paths.append(candidates[0])
                else:
                    problem(sitemap_url, "representative_page_missing", prefix + kind)
        paths = list(dict.fromkeys(paths))
    if locations:
        for path in paths:
            if origin + path not in locations:
                problem(sitemap_url, "sitemap_page_missing", path)

    for path in paths:
        url = origin + path
        response = get(url)
        if response is None:
            continue
        if response.status != 200:
            problem(url, "page_status", f"Expected 200, received {response.status}")
            continue
        doc = Document()
        doc.feed(response.body)
        locale = 'ru' if path.startswith('/ru/') else 'en' if path.startswith('/en/') else 'zh'
        plain_path = urlsplit(path).path
        kind = 'product' if '/cigar/' in plain_path else 'brand' if '/brand/' in plain_path else 'home'
        catalog_view = plain_path.endswith('/catalog')
        try:
            data = json.loads(doc.store_data[0]) if len(doc.store_data) == 1 else None
            page = data.get('page') if isinstance(data, dict) else None
            prerendered = (isinstance(page, dict) and page.get('path') == path
                          and page.get('locale') == locale and page.get('kind') == kind
                          and (page.get('view') == 'catalog') == catalog_view
                          and page.get('indexable') is True)
        except (ValueError, TypeError):
            prerendered = False
        checks = {
            "html_content_type": "text/html" in response.headers.get("content-type", "").lower(),
            "title_missing": bool(doc.title.strip()),
            "h1_missing": bool(doc.h1.strip()),
            "description_missing": any(m.get("name") == "description" and m.get("content", "").strip() for m in doc.metas),
            "canonical_mismatch": [link.get("href") for link in doc.links if link.get("rel") == "canonical"] == [url],
            "prerender_missing": prerendered,
            "language_mismatch": doc.lang.lower() == ("ru-ru" if path.startswith("/ru/") else "en" if path.startswith("/en/") else "zh-cn"),
            "unexpected_noindex": not any(token in (response.headers.get("x-robots-tag", "") + " " + " ".join(
                m.get("content", "") for m in doc.metas if m.get("name", "").lower() in ("robots", "googlebot", "yandex")
            )).lower() for token in ("noindex", "none")),
        }
        for code, passed in checks.items():
            if not passed:
                problem(url, code, "Public indexable page acceptance check failed")
        if path == "/":
            resources = [(link.get("href"), "image/") for link in doc.links if link.get("rel") == "icon"]
            resources += [(script.get("src"), "javascript") for script in doc.scripts
                          if "startup-loader.js" in script.get("src", "")]
            if not resources or not any(kind == "image/" for _, kind in resources):
                problem(url, "favicon_missing", "Homepage must declare its favicon")
            if not any(kind == "javascript" for _, kind in resources):
                problem(url, "startup_script_missing", "Homepage must reference its startup script")
            for href, kind in resources:
                resource_url = urljoin(url, href or "")
                if urlsplit(resource_url).netloc != urlsplit(origin).netloc or urlsplit(resource_url).scheme != urlsplit(origin).scheme:
                    problem(url, "external_resource", "Audit only fetches same-origin static resources")
                    continue
                resource = get(resource_url)
                resource_urls.append(resource_url)
                if resource and (resource.status != 200 or kind not in resource.headers.get("content-type", "").lower()):
                    problem(resource_url, "resource_response", "Expected a successful image or JavaScript response, not an HTML fallback")

    robots_url = origin + "/robots.txt"
    robots = get(robots_url)
    if robots:
        lines = robots.body.splitlines()
        parser = RobotFileParser()
        parser.parse(lines)
        if (robots.status != 200 or "text/plain" not in robots.headers.get("content-type", "").lower()
                or sitemap_url not in (parser.site_maps() or [])):
            problem(robots_url, "robots_sitemap_missing", "robots.txt must advertise the canonical sitemap")
        for agent in ("Googlebot", "YandexBot"):
            if any(not parser.can_fetch(agent, origin + path) for path in paths):
                problem(robots_url, "robots_blocks_pages", agent)
            if any(parser.can_fetch(agent, origin + path) for path in ROBOTS_DISALLOWED_PATHS):
                problem(robots_url, "robots_allows_private_paths", agent)
            if any(not parser.can_fetch(agent, url) for url in resource_urls):
                problem(robots_url, "robots_blocks_resources", agent)
        if not parser.can_fetch("Googlebot", origin + "/login"):
            problem(robots_url, "robots_blocks_login_noindex", "Crawlers must be able to read the login page noindex")
    login_url = origin + "/login"
    login = get(login_url)
    if login:
        directives = {value.strip().lower() for value in login.headers.get("x-robots-tag", "").split(",")}
        if login.status != 200 or not directives.intersection({"noindex", "none"}):
            problem(login_url, "login_indexable", "Login must return 200 with X-Robots-Tag: noindex")
    for prefix in (("/", "/ru/", "/en/") if representative_pages else ("/",)):
        missing_url = origin + prefix + "__seo_audit_missing_page__"
        missing = get(missing_url)
        if missing and missing.status != 404:
            problem(missing_url, "soft_404", f"Expected 404, received {missing.status}")
        if missing and representative_pages:
            doc = Document()
            doc.feed(missing.body)
            expected_lang = {"/": "zh-cn", "/ru/": "ru-ru", "/en/": "en"}[prefix]
            if ("text/html" not in missing.headers.get("content-type", "").lower()
                    or doc.lang.lower() != expected_lang or not doc.title.strip() or not doc.h1.strip()):
                problem(missing_url, "localized_404_missing", "Expected a complete localized HTML error page")
            if any(link.get("rel") == "canonical" for link in doc.links):
                problem(missing_url, "404_canonical", "Error pages must not claim a canonical product URL")
    if representative_pages:
        missing_api_url = origin + "/api/storefront/page/?path=%2F__seo_audit_missing_page__"
        missing_api = get(missing_api_url)
        if missing_api:
            try:
                data = json.loads(missing_api.body)
            except ValueError:
                data = None
            if (missing_api.status != 404 or "application/json" not in missing_api.headers.get("content-type", "").lower()
                    or data != {"error": "not_found"}):
                problem(missing_api_url, "api_404_contract", "Expected HTTP 404 and JSON not_found")
    if www_origin:
        response = get(www_origin + "/")
        if response and (response.status not in (301, 308) or response.headers.get("location") != origin + "/"):
            problem(www_origin + "/", "www_redirect", "Expected a direct permanent redirect to the canonical origin")
    return {"origin": origin, "ready": not issues, "checked_urls": checked,
            "sitemap_url_count": sitemap_count, "issues": issues, "retries": retried}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", help="Canonical origin, e.g. https://cigardomtabaka.com")
    parser.add_argument("--www-origin", help="Optional www origin to verify a direct permanent redirect")
    parser.add_argument("--path", action="append", default=[], help="Additional indexable brand/product/page-2 path")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--representative-pages", action="store_true", help="Check three-language catalog, brand, product and 404 samples")
    parser.add_argument("--retries", type=int, default=0, help="Retry only network failures and transient HTTP responses (0–3)")
    parser.add_argument("--retry-delay", type=float, default=2)
    args = parser.parse_args()
    if not 0 < args.timeout <= 30:
        parser.error("timeout must be positive and at most 30 seconds")
    try:
        report = audit(args.origin, www_origin=args.www_origin, extra_paths=args.path,
                       representative_pages=args.representative_pages, retries=args.retries, retry_delay=args.retry_delay,
                       request=lambda url: fetch(url, timeout=args.timeout))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
