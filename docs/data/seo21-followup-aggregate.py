#!/usr/bin/env python3
"""Run a privacy-preserving read-only SEO-21 log aggregation over SSH.

The remote Python program is sent on SSH stdin. It snapshots log file sizes
once, parses only complete lines after the fixed lower bound, and returns only
anonymous counts plus matches to the existing public sitemap URL set.
"""

from __future__ import annotations

import csv
import datetime as dt
import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "docs" / "data"
LOWER = "2026-10-27T16:10:42Z"
HOST = "root@103.110.65.50"
SITEMAP_URL = "https://cigardomtabaka.com/sitemap-storefront.xml"

parser = argparse.ArgumentParser()
parser.add_argument("--replay-metadata", type=Path, help="Replay exact byte lengths and time bound from an earlier aggregate JSON")
args = parser.parse_args()

previous_csv = ROOT / "docs" / "seo-21-crawl-coverage.csv"
previous_urls = None
if previous_csv.exists():
    with previous_csv.open(newline="", encoding="utf-8") as f:
        previous_urls = [r["public_url"] for r in csv.DictReader(f)]

sitemap_fetched_at = dt.datetime.now(dt.timezone.utc)
request = urllib.request.Request(SITEMAP_URL, headers={"User-Agent": "SEO21-followup-readonly/1.0"})
with urllib.request.urlopen(request, timeout=30) as response:
    sitemap_status = response.status
    sitemap_bytes = response.read()
root = ET.fromstring(sitemap_bytes)
sitemap_ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
if root.tag != sitemap_ns + 'urlset':
    raise SystemExit('Expected the public page sitemap urlset')
public_urls = [node.text.strip() for node in root.findall(f'{sitemap_ns}url/{sitemap_ns}loc')
               if node.text and node.text.strip()]
if not public_urls or len(public_urls) != len(set(public_urls)):
    raise SystemExit(f"Live sitemap was empty or had duplicate URLs: count={len(public_urls)} unique={len(set(public_urls))}")
previous_set = set(previous_urls) if previous_urls is not None else None
live_set = set(public_urls)
sitemap_check = {
    "url": SITEMAP_URL,
    "fetched_at_utc": sitemap_fetched_at.isoformat().replace("+00:00", "Z"),
    "http_status": sitemap_status,
    "content_sha256": hashlib.sha256(sitemap_bytes).hexdigest(),
    "url_count": len(public_urls),
    "duplicate_url_count": 0,
    "matches_previous_audit_set": (live_set == previous_set) if previous_set is not None else None,
    "previous_audit_url_count": len(previous_set) if previous_set is not None else None,
    "only_in_live_sitemap_count": len(live_set - previous_set) if previous_set is not None else None,
    "only_in_previous_audit_count": len(previous_set - live_set) if previous_set is not None else None,
}
snapshot_spec = None
if args.replay_metadata:
    prior = json.loads(args.replay_metadata.read_text(encoding="utf-8"))
    snapshot_spec = {"snapshot_started_utc": prior["snapshot_started_utc"],
                     "snapshot_completed_utc": prior.get("snapshot_completed_utc"),
                     "log_files": prior["log_files"]}

REMOTE = r'''#!/usr/bin/env python3
import datetime as dt, gzip, glob, ipaddress, json, os, re, socket, sys, time
from collections import Counter, defaultdict
from urllib.parse import urlsplit, parse_qsl, urlencode

LOWER = dt.datetime.fromisoformat("2026-10-27T16:10:42+00:00")
SITEMAP_URLS = __PUBLIC_URLS__
SNAPSHOT_SPEC = __SNAPSHOT_SPEC__
LINE_RE = re.compile(rb'^([^ ]+) [^ ]+ [^ ]+ \[([^]]+)\] "([^"]*)" (\d{3}|-) [^ ]+ "[^"]*" "([^"]*)"')
TIME_FMT = "%d/%b/%Y:%H:%M:%S %z"
CORE = ["/ru/", "/ru/brand/cohiba", "/ru/cigar/102/cohiba-genios",
        "/ru/cigar/103/cohiba-magicos", "/ru/cigar/97/cohiba-siglo-ii",
        "/ru/cigar/98/cohiba-siglo-iii"]

def utc(t):
    return t.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z") if t else None

def key_for_target(target):
    u = urlsplit(target)
    pairs = sorted(parse_qsl(u.query, keep_blank_values=True))
    return (u.path or "/") + (("?" + urlencode(pairs, doseq=True)) if pairs else "")

def private_path(path):
    return bool(re.search(r"(?i)(privnote|/p/|token|secret|admin|login)", path))

def get_nets():
    import urllib.request
    req = urllib.request.Request("https://developers.google.com/static/crawling/ipranges/common-crawlers.json",
                                 headers={"User-Agent": "SEO21-followup-readonly/1.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        obj = json.load(response)
    nets = [ipaddress.ip_network(p.get("ipv4Prefix", p.get("ipv6Prefix"))) for p in obj["prefixes"]]
    return nets, obj.get("creationTime")

def yandex_reverse_forward(ips):
    found = {}
    def check(ip):
        try:
            name = socket.gethostbyaddr(ip)[0].rstrip(".").lower()
            if not any(name == suffix or name.endswith("." + suffix) for suffix in ("yandex.ru", "yandex.net", "yandex.com")):
                return ip, False
            answers = {entry[4][0] for entry in socket.getaddrinfo(name, None)}
            return ip, ip in answers
        except Exception:
            return ip, None
    # DNS only runs if Yandex UA claims occur; cap the work to avoid a long audit.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(check, ip): ip for ip in ips}
        deadline = time.monotonic() + 25
        try:
            for future in concurrent.futures.as_completed(futures, timeout=25):
                try:
                    ip, result = future.result(timeout=max(0.01, deadline-time.monotonic()))
                    found[ip] = result
                except Exception:
                    found[futures[future]] = None
        except concurrent.futures.TimeoutError:
            pass
        for future, ip in futures.items():
            found.setdefault(ip, None)
    return found

# Freeze file membership and byte lengths before reading, or replay a saved manifest.
snapshot_started = (dt.datetime.fromisoformat(SNAPSHOT_SPEC["snapshot_started_utc"].replace("Z", "+00:00"))
                    if SNAPSHOT_SPEC else dt.datetime.now(dt.timezone.utc))
snapshots = []
if SNAPSHOT_SPEC:
    for item in SNAPSHOT_SPEC["log_files"]:
        name = os.path.basename(item["file"])
        path = os.path.join("/var/log/nginx", name)
        size = int(item["snapshot_bytes"])
        st = os.stat(path)
        if st.st_size < size:
            raise RuntimeError("saved snapshot byte range is no longer available")
        current_mtime = dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat().replace("+00:00", "Z")
        if name != "access.log" and current_mtime != item["mtime_utc"]:
            raise RuntimeError("saved rotated log file mtime changed; cannot claim exact snapshot replay")
        snapshots.append((path, size, st.st_mtime))
else:
    paths = sorted(glob.glob("/var/log/nginx/access.log*"))
    for path in paths:
        try:
            st = os.stat(path)
            snapshots.append((path, st.st_size, st.st_mtime))
        except OSError:
            continue

# Common crawler ranges are the sole Googlebot authenticity criterion.
nets, ranges_creation = get_nets()
records = []
malformed = 0
line_count = 0
truncated_files = 0
event_count = 0
event_first = None
event_last = None
for path, size, mtime in snapshots:
    try:
        with open(path, "rb") as handle:
            raw = handle.read(size)
        if path.endswith(".gz"):
            raw = gzip.decompress(raw)
        cut = raw.rfind(b"\n")
        if cut < 0:
            truncated_files += 1
            continue
        if cut + 1 < len(raw):
            truncated_files += 1
        raw = raw[:cut+1]
        for line in raw.splitlines():
            line_count += 1
            match = LINE_RE.match(line)
            if not match:
                malformed += 1
                continue
            ip_b, time_b, request_b, status_b, ua_b = match.groups()
            try:
                stamp = dt.datetime.strptime(time_b.decode("ascii"), TIME_FMT).astimezone(dt.timezone.utc)
            except Exception:
                malformed += 1
                continue
            if stamp <= LOWER or stamp > snapshot_started:
                continue
            request = request_b.decode("latin1", "replace").split()
            if len(request) < 2:
                malformed += 1
                continue
            method, target = request[0], request[1]
            u = urlsplit(target)
            path_only = u.path or "/"
            # Never retain or emit secret-like paths; they are not needed for any output.
            if private_path(path_only):
                continue
            event_count += 1
            event_first = min(event_first, stamp) if event_first else stamp
            event_last = max(event_last, stamp) if event_last else stamp
            ip = ip_b.decode("ascii", "ignore")
            ua = ua_b.decode("latin1", "ignore").lower()
            status = int(status_b) if status_b.isdigit() else 0
            try:
                ip_obj = ipaddress.ip_address(ip)
                in_common = any(ip_obj in net for net in nets)
            except Exception:
                in_common = False
            category = None
            if "googlebot-image" in ua:
                category = "image" if in_common else "image_unverified"
            elif "googlebot-video" in ua:
                category = "video" if in_common else "video_unverified"
            elif "googlebot-news" in ua:
                category = "news" if in_common else "news_unverified"
            elif "googlebot" in ua:
                category = "web" if in_common else "web_unverified"
            elif "yandex" in ua:
                category = "yandex_claim"
            if category:
                records.append((stamp, ip, path_only, key_for_target(target), status, category, method))
    except Exception:
        malformed += 1

yandex_ips = {r[1] for r in records if r[5] == "yandex_claim"}
yandex_validation = yandex_reverse_forward(yandex_ips) if yandex_ips else {}
# Verify Yandex claim identity after reverse-host suffix boundary and forward match.
verified = []
for record in records:
    if record[5] == "yandex_claim":
        result = yandex_validation.get(record[1])
        if result is True:
            verified.append(record[:5] + ("yandex", record[6]))
        else:
            bucket = "yandex_unknown" if result is None else "yandex_unverified"
            verified.append(record[:5] + (bucket, record[6]))
    else:
        verified.append(record)

authentic = [r for r in verified if r[5] in ('web', 'image', 'video', 'news', 'yandex')]
start = min((r[0] for r in authentic), default=None)
end = max((r[0] for r in authentic), default=None)
overall = Counter()
status = defaultdict(Counter)
daily = Counter()
route_family_status = defaultdict(Counter)
coverage = {key_for_target(urlsplit(url).path + ("?" + urlsplit(url).query if urlsplit(url).query else "")):
            {"count": 0, "last": None, "status": Counter()} for url in SITEMAP_URLS}
core = {path: {"count": 0, "last": None, "status": Counter()} for path in CORE}
core_query = {path: {"count": 0, "last": None, "status": Counter()} for path in CORE}
controls = defaultdict(Counter)
resources = defaultdict(Counter)
other_categories = Counter()
query_keys = Counter()

for stamp, ip, path_only, urlkey, code, category, method in verified:
    overall[category] += 1
    status[category][str(code)] += 1
    daily[(stamp.date().isoformat(), category)] += 1
    if category == "web":
        parts = [part for part in path_only.split("/") if part]
        if urlkey in coverage:
            route_family = "current_sitemap_url"
        elif re.match(r"^/cigar/[0-9]+/[^/]+/?$", path_only):
            route_family = "cigar_id_slug_outside_current_sitemap"
        elif re.match(r"^/cigar/[0-9]+/?$", path_only):
            route_family = "cigar_id_no_slug_outside_current_sitemap"
        elif re.match(r"^/(?:ru|en)/cigar/[0-9]+/[^/]+/?$", path_only):
            route_family = "localized_cigar_id_slug_outside_current_sitemap"
        elif "/brand/" in path_only:
            route_family = "brand_path_outside_current_sitemap"
        elif "/catalog" in path_only:
            route_family = "catalog_path_outside_current_sitemap"
        elif re.search(r"(?i)\.(?:avif|webp|png|jpe?g|gif|svg|ico|js|mjs|css|woff2?|ttf|otf)$", path_only):
            route_family = "static_resource"
        else:
            route_family = "other_public_path"
        route_family_status[route_family][str(code)] += 1
        if urlkey in coverage:
            cell = coverage[urlkey]
            cell["count"] += 1
            cell["last"] = max(cell["last"], utc(stamp)) if cell["last"] else utc(stamp)
            cell["status"][str(code)] += 1
        if path_only in core:
            if urlkey == path_only:
                cell = core[path_only]
                cell["count"] += 1
                cell["last"] = max(cell["last"], utc(stamp)) if cell["last"] else utc(stamp)
                cell["status"][str(code)] += 1
            else:
                qcell = core_query[path_only]
                qcell["count"] += 1
                qcell["last"] = max(qcell["last"], utc(stamp)) if qcell["last"] else utc(stamp)
                qcell["status"][str(code)] += 1
        if path_only in ("/robots.txt", "/sitemap-storefront.xml"):
            controls[path_only][str(code)] += 1
        elif path_only.startswith("/sitemap") and path_only.endswith(".xml"):
            controls["other_sitemap_paths"][str(code)] += 1
        elif re.search(r"(?i)\.(?:avif|webp|png|jpe?g|gif|svg|ico)(?:$|\?)", path_only):
            resources["image"][str(code)] += 1
        elif re.search(r"(?i)\.(?:js|mjs)(?:$|\?)", path_only):
            resources["javascript"][str(code)] += 1
        elif re.search(r"(?i)\.css(?:$|\?)", path_only):
            resources["css"][str(code)] += 1
        elif re.search(r"(?i)\.(?:woff2?|ttf|otf)(?:$|\?)", path_only):
            resources["font"][str(code)] += 1
        elif path_only.startswith("/api/"):
            resources["api"][str(code)] += 1
        else:
            resources["other_web_path"][str(code)] += 1
    if category in ("web", "image", "video", "news", "yandex"):
        q = urlsplit(urlkey).query
        for key, _ in parse_qsl(q, keep_blank_values=True):
            query_keys[key] += 1

coverage_rows = []
for url in SITEMAP_URLS:
    u = urlsplit(url)
    urlkey = key_for_target(u.path + (("?" + u.query) if u.query else ""))
    cell = coverage[urlkey]
    path = u.path or "/"
    locale = path.split("/")[1] if path.startswith("/") and path.split("/")[1] in ("zh", "en", "ru") else "zh"
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] in ("zh", "en", "ru"):
        parts = parts[1:]
    kind = "home" if not parts else ("brand" if "brand" in parts else "catalog" if "catalog" in parts else "product" if "cigar" in parts else "other")
    coverage_rows.append({"public_url": url, "locale": locale, "kind": kind,
                          "verified_googlebot_web_fetches": cell["count"],
                          "last_verified_googlebot_web_fetch_utc": cell["last"],
                          "status_codes": dict(sorted(cell["status"].items()))})

result = {
  "snapshot_mode": "replayed_saved_byte_manifest" if SNAPSHOT_SPEC else "fresh_byte_snapshot",
  "window_start_exclusive_utc": utc(LOWER),
  "snapshot_started_utc": utc(snapshot_started),
  "snapshot_completed_utc": SNAPSHOT_SPEC.get("snapshot_completed_utc") if SNAPSHOT_SPEC else utc(dt.datetime.now(dt.timezone.utc)),
  "analysis_recomputed_utc": utc(dt.datetime.now(dt.timezone.utc)),
  "first_verified_crawler_event_utc": utc(start), "last_verified_crawler_event_utc": utc(end),
  "parsed_nonprivate_window_log_event_count": event_count,
  "parsed_window_event_time_bounds_utc": {"first": utc(event_first), "last": utc(event_last)},
  "official_google_ranges_creation_time": ranges_creation,
  "log_files": [{"file": os.path.basename(p), "snapshot_bytes": size,
                 "mtime_utc": dt.datetime.fromtimestamp(mtime, dt.timezone.utc).isoformat().replace("+00:00", "Z")}
                for p, size, mtime in snapshots],
  "complete_log_lines": line_count, "malformed_lines_or_file_errors": malformed,
  "truncated_files_or_partial_tail": truncated_files,
  "crawler_requests_by_category": dict(sorted(overall.items())),
  "status_by_category": {k: dict(sorted(v.items())) for k, v in sorted(status.items())},
  "daily_verified_requests": [{"date_utc": d, "category": c, "requests": n}
                              for (d,c),n in sorted(daily.items())],
  "core_pages": {p: {"fetches": x["count"], "last_fetch_utc": x["last"],
                       "status_codes": dict(sorted(x["status"].items()))} for p,x in core.items()},
  "core_page_query_variants": {p: {"fetches": x["count"], "last_fetch_utc": x["last"],
                                   "status_codes": dict(sorted(x["status"].items()))} for p,x in core_query.items()},
  "sitemap_public_url_count": len(SITEMAP_URLS),
  "sitemap_urls_with_verified_web_fetch": sum(1 for x in coverage.values() if x["count"]),
  "sitemap_url_web_fetch_total": sum(x["count"] for x in coverage.values()),
  "sitemap_coverage": coverage_rows,
  "robots_sitemap_statuses_verified_web": {k: dict(sorted(v.items())) for k,v in sorted(controls.items())},
  "resource_statuses_verified_web": {k: dict(sorted(v.items())) for k,v in sorted(resources.items())},
  "verified_web_route_family_statuses": {k: dict(sorted(v.items())) for k,v in sorted(route_family_status.items())},
  "query_key_counts_verified_crawlers": dict(sorted(query_keys.items())),
  "yandex_ua_claim_unique_ip_count": len(yandex_ips),
  "yandex_validation_outcomes": {"verified_reverse_forward_boundary": sum(1 for x in yandex_validation.values() if x is True),
                                  "unverified": sum(1 for x in yandex_validation.values() if x is False),
                                  "unknown": sum(1 for x in yandex_validation.values() if x is None)},
}
print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
'''

remote_code = REMOTE.replace("__PUBLIC_URLS__", repr(public_urls)).replace("__SNAPSHOT_SPEC__", repr(snapshot_spec))
proc = subprocess.run(["ssh", "-o", "BatchMode=yes", HOST, "python3", "-"], input=remote_code,
                      text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
if proc.returncode:
    print("SSH aggregation failed; stderr omitted from artifacts:", file=sys.stderr)
    print(proc.stderr[-1000:], file=sys.stderr)
    raise SystemExit(proc.returncode)
try:
    result = json.loads(proc.stdout)
except Exception as exc:
    print(f"Remote output was not valid aggregate JSON: {exc}", file=sys.stderr)
    raise SystemExit(2)

result["live_sitemap_check"] = sitemap_check

tag = "20261029"
DATA.mkdir(parents=True, exist_ok=True)
json_path = DATA / f"seo21-followup-{tag}.json"
csv_path = DATA / f"seo21-followup-coverage-{tag}.csv"
json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
with csv_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["public_url", "locale", "kind", "verified_googlebot_web_fetches",
                                          "last_verified_googlebot_web_fetch_utc", "status_codes"], lineterminator="\n")
    writer.writeheader()
    for row in result["sitemap_coverage"]:
        writer.writerow({**row, "status_codes": ";".join(f"{k}:{v}" for k,v in row["status_codes"].items())})
print(json.dumps({"snapshot_started_utc": result["snapshot_started_utc"],
                  "snapshot_completed_utc": result["snapshot_completed_utc"],
                  "analysis_recomputed_utc": result["analysis_recomputed_utc"],
                  "first_verified_crawler_event_utc": result["first_verified_crawler_event_utc"],
                  "last_verified_crawler_event_utc": result["last_verified_crawler_event_utc"],
                  "crawler_requests_by_category": result["crawler_requests_by_category"],
                  "live_sitemap_check": result["live_sitemap_check"],
                  "sitemap_urls_with_verified_web_fetch": result["sitemap_urls_with_verified_web_fetch"],
                  "sitemap_url_web_fetch_total": result["sitemap_url_web_fetch_total"],
                  "json": str(json_path), "csv": str(csv_path)}, ensure_ascii=False, indent=2))
