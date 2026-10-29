#!/usr/bin/env python3
"""Controlled local browser A/B for the storefront logo SVG preload.

The script captures one set of production storefront HTML and resources, then
serves byte-identical baseline HTML and a candidate that adds only the tested
preload tag. A local read-only HTTP mirror serves cached production responses;
Chromium performs normal requests through CDP network/CPU throttling. No
Playwright route.fulfill is used. Run only after the task owner gives the
measurement signal.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import http.server
import json
import os
import platform
import re
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


PATHS = ("/", "/ru/brand/cohiba", "/ru/cigar/103/cohiba-magicos")
PRELOAD = '<link rel="preload" as="image" href="/static/frontend/logo-opening-motion-v2.svg" type="image/svg+xml">'
LOGO_PATH = "/static/frontend/logo-opening-motion-v2.svg"
AGE_KEY = "cdt.customer.age-confirmed-at"
VIEWPORT = {"width": 390, "height": 844}
THROTTLE = {"latency": 150, "downloadThroughput": 200_000, "uploadThroughput": 93_750}
CPU_RATE = 4

INIT = r"""(() => {
  const audit = window.seoMeasure = {started:false, ready:0, exit:0,
    lcp:0, cls:0, overlaps:0, earlyFocus:0, startupFrames:0,
    logoVisibleFrames:0, logoImageLoadedFrames:0, logoFirstVisible:0, logoFirstVisibleSrc:null};
  try {new PerformanceObserver(list => list.getEntries().forEach(e => {
    if (!e.hadRecentInput) audit.cls += e.value;
  })).observe({type:'layout-shift',buffered:true});} catch {}
  try {new PerformanceObserver(list => list.getEntries().forEach(e => {
    audit.lcp = Math.max(audit.lcp, e.startTime);
  })).observe({type:'largest-contentful-paint',buffered:true});} catch {}
  const inspect = () => {
    const html = document.documentElement;
    if (!html) return;
    if (html.dataset.cdtAppReady === 'true' && !audit.ready) audit.ready = performance.now();
    if (html.dataset.cdtStarting === 'true') audit.started = true;
    if (audit.started && !html.dataset.cdtStarting && !audit.exit) audit.exit = performance.now();
  };
  new MutationObserver(inspect).observe(document,{subtree:true,childList:true,attributes:true});
  const frame = () => {
    inspect();
    const loader = document.getElementById('startup-loader');
    if (loader && !loader.hidden && document.documentElement.dataset.cdtStarting === 'true') {
      audit.startupFrames++;
      const logo = loader.querySelector('.cdt-startup__logo');
      const logoStyle = logo && getComputedStyle(logo);
      if (logo && logo.complete && logo.naturalWidth > 0 && logoStyle && logoStyle.display !== 'none' && logoStyle.visibility !== 'hidden'
          && Number(logoStyle.opacity) > 0 && logo.getBoundingClientRect().width > 0
          && logo.getBoundingClientRect().height > 0) {
        audit.logoVisibleFrames++;
        audit.logoImageLoadedFrames++;
        if (!audit.logoFirstVisible) { audit.logoFirstVisible = performance.now(); audit.logoFirstVisibleSrc = logo.currentSrc; }
      }
      const gate = document.querySelector('[data-age-gate]');
      const root = document.getElementById('store-root');
      if (gate && !gate.hidden && getComputedStyle(gate).display !== 'none'
          && getComputedStyle(gate).visibility !== 'hidden'
          && root && Number(getComputedStyle(root).opacity) > 0) audit.overlaps++;
      if (document.activeElement?.closest('[data-age-gate]')) audit.earlyFocus++;
    }
    if (!audit.exit) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
})()"""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_public(url: str) -> tuple[int, list[tuple[str, str]], bytes]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SEO22-preload-controlled-measure/1.0", "Accept-Encoding": "gzip"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, list(response.headers.items()), response.read()
    except urllib.error.HTTPError as response:
        return response.code, list(response.headers.items()), response.read()


def body_encoding(headers: list[tuple[str, str]]) -> str | None:
    return next((value.lower() for name, value in headers if name.lower() == "content-encoding"), None)


def decoded_body(headers: list[tuple[str, str]], body: bytes) -> bytes:
    return gzip.decompress(body) if body_encoding(headers) == "gzip" else body


def insert_preload(html: bytes) -> bytes:
    text = html.decode("utf-8")
    if PRELOAD in text or LOGO_PATH in text.split("</head>", 1)[0]:
        raise ValueError("Production head already references the tested SVG preload; A/B baseline is not clean")
    stylesheets = list(re.finditer(r"<link\b(?=[^>]*\brel=[\"']stylesheet[\"'])[^>]*>", text, re.I))
    if not stylesheets:
        raise ValueError("Could not find a stylesheet link for the preload insertion point")
    insertion = stylesheets[-1].end()
    candidate = (text[:insertion] + PRELOAD + text[insertion:]).encode("utf-8")
    if candidate.replace(PRELOAD.encode(), b"", 1) != html:
        raise AssertionError("Candidate must differ from the original HTML by exactly the preload tag")
    return candidate


def production_route_pattern(origin: str) -> re.Pattern[str]:
    host = urllib.parse.urlsplit(origin).hostname
    if not host:
        raise ValueError(f"Invalid origin: {origin}")
    escaped = re.escape(host.removeprefix("www."))
    return re.compile(rf"https?://(?:www\.)?{escaped}(?::\d+)?/.*", re.I)


def controlled_route_handler(origin: str, local_origin: str, blocked_external: list[dict[str, str]],
                             route_rewrites: list[dict[str, Any]]):
    pattern = production_route_pattern(origin)
    local_host = urllib.parse.urlsplit(local_origin).netloc

    def handle(route: Any) -> None:
        request_url = route.request.url
        parts = urllib.parse.urlsplit(request_url)
        if pattern.fullmatch(request_url):
            target = local_origin + parts.path + (("?" + parts.query) if parts.query else "")
            route_rewrites.append({"from_host": parts.hostname or "", "from_path": parts.path,
                                   "to_host": local_host, "to_path": parts.path,
                                   "query_present": bool(parts.query),
                                   "query_sha256": digest(parts.query.encode()) if parts.query else None})
            route.continue_(url=target)
        elif parts.netloc == local_host or not parts.scheme.startswith("http"):
            route.continue_()
        else:
            blocked_external.append({"host": parts.hostname or "", "path": parts.path})
            route.abort()
    return handle


class MirrorState:
    def __init__(self, origin: str, cache_dir: Path):
        self.origin = origin.rstrip("/")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.frozen = False
        self.active_variant = "baseline"
        self.pages: dict[str, dict[str, tuple[int, list[tuple[str, str]], bytes]]] = {"baseline": {}, "candidate": {}}
        self.cache_misses: list[str] = []
        self.proxy_fetches: list[dict[str, Any]] = []
        self.cache_index: dict[str, tuple[int, list[tuple[str, str]], bytes]] = {}

    @staticmethod
    def cache_key(method: str, target: str) -> str:
        return f"{method.upper()} {target}"

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / digest(key.encode("utf-8"))

    def get_cached(self, method: str, target: str) -> tuple[int, list[tuple[str, str]], bytes] | None:
        key = self.cache_key(method, target)
        with self.lock:
            if key in self.cache_index:
                return self.cache_index[key]
            stem = self._cache_path(key)
            meta_path = stem.with_suffix(".json")
            body_path = stem.with_suffix(".body")
            if meta_path.exists() and body_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                entry = (int(meta["status"]), [tuple(x) for x in meta["headers"]], body_path.read_bytes())
                self.cache_index[key] = entry
                self.proxy_fetches.append({"path": urllib.parse.urlsplit(target).path,
                                           "status": entry[0], "wire_bytes": len(entry[2]),
                                           "wire_sha256": digest(entry[2]),
                                           "content_encoding": body_encoding(entry[1]),
                                           "content_type": next((v for k, v in entry[1] if k.lower() == "content-type"), None),
                                           "reused_existing_cache": True})
                return entry
            if self.frozen:
                self.cache_misses.append(target)
                return None
            url = self.origin + target
            status, headers, body = fetch_public(url)
            # Freeze each upstream representation once so both arms use identical bytes/headers.
            meta_path.write_text(json.dumps({"status": status, "headers": headers}, ensure_ascii=False), encoding="utf-8")
            body_path.write_bytes(body)
            entry = (status, headers, body)
            self.cache_index[key] = entry
            self.proxy_fetches.append({"path": urllib.parse.urlsplit(target).path,
                                       "status": status, "wire_bytes": len(body), "wire_sha256": digest(body),
                                       "content_encoding": body_encoding(headers),
                                       "content_type": next((v for k, v in headers if k.lower() == "content-type"), None)})
            return entry


class MirrorHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: MirrorState

    def do_GET(self) -> None:  # noqa: N802
        target = self.path if self.path.startswith("/") else "/"
        route_path = urllib.parse.urlsplit(target).path or "/"
        if route_path in self.state.pages["baseline"]:
            status, headers, body = self.state.pages[self.state.active_variant][route_path]
        else:
            entry = self.state.get_cached("GET", target)
            if entry is None:
                status, headers, body = 503, [("Content-Type", "text/plain; charset=utf-8")], b"mirror cache miss"
            else:
                status, headers, body = entry
        self.send_response(status)
        excluded = {"connection", "transfer-encoding", "content-length", "keep-alive", "proxy-authenticate",
                    "proxy-authorization", "te", "trailers", "upgrade", "set-cookie"}
        for name, value in headers:
            if name.lower() not in excluded:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Chromium may cancel a resource after the document is ready.
        self.close_connection = True

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def log_message(self, *_args: Any) -> None:
        return


def median_summary(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    metrics = ("ready", "exit", "handoff_ms", "lcp", "cls", "logoFirstStartMs", "logoTransferBytes")
    for path in PATHS:
        for confirmed in (False, True):
            for variant in ("baseline", "candidate"):
                selected = [r for r in runs if r["path"] == path and r["confirmed"] == confirmed and r["variant"] == variant]
                summary: dict[str, Any] = {"path": path, "confirmed": confirmed, "variant": variant, "samples": len(selected)}
                for metric in metrics:
                    values = [r.get(metric) for r in selected if isinstance(r.get(metric), (float, int))]
                    summary[f"median_{metric}"] = statistics.median(values) if values else None
                summary["logo_request_count_total"] = sum(r.get("logoRequestCount", 0) for r in selected)
                summary["logo_duplicate_requests_total"] = sum(r.get("logo_duplicate_requests", 0) for r in selected)
                summary["cache_misses_total"] = sum(r.get("cache_misses", 0) for r in selected)
                summaries.append(summary)
    return summaries


def run(args: argparse.Namespace) -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = args.cache_dir or Path("/tmp") / f"seo22-preload-mirror-{run_id}"

    captured_at = now_utc()
    raw_html: dict[str, tuple[int, list[tuple[str, str]], bytes]] = {}
    html_metadata = []
    html_meta_by_path: dict[str, dict[str, Any]] = {}
    for path in PATHS:
        status, headers, body = fetch_public(args.origin.rstrip("/") + path)
        if status != 200:
            raise RuntimeError(f"Could not capture production HTML for {path}: HTTP {status}")
        raw_html[path] = (status, headers, body)
        meta = {"path": path, "status": status, "captured_production_wire_bytes": len(body),
                "captured_production_wire_sha256": digest(body), "content_encoding": body_encoding(headers),
                "decoded_sha256": digest(decoded_body(headers, body))}
        html_metadata.append(meta)
        html_meta_by_path[path] = meta

    state = MirrorState(args.origin, cache_dir)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MirrorHandler)
    MirrorHandler.state = state
    host, port = server.server_address
    local_origin = f"http://{host}:{port}"
    for path, (status, headers, wire_body) in raw_html.items():
        plain = decoded_body(headers, wire_body)
        candidate_plain = insert_preload(plain)
        if candidate_plain.replace(PRELOAD.encode(), b"", 1) != plain:
            raise AssertionError(f"Candidate HTML differs beyond the preload tag for {path}")
        if body_encoding(headers) == "gzip":
            baseline_wire = gzip.compress(plain, compresslevel=6, mtime=0)
            candidate_wire = gzip.compress(candidate_plain, compresslevel=6, mtime=0)
        else:
            baseline_wire, candidate_wire = plain, candidate_plain
        html_meta_by_path[path].update({"baseline_control_wire_bytes": len(baseline_wire),
                                        "baseline_control_wire_sha256": digest(baseline_wire),
                                        "candidate_control_wire_bytes": len(candidate_wire),
                                        "candidate_control_wire_sha256": digest(candidate_wire),
                                        "decoded_candidate_sha256": digest(candidate_plain)})
        state.pages["baseline"][path] = (status, headers, baseline_wire)
        state.pages["candidate"][path] = (status, headers, candidate_wire)

    server_thread = threading.Thread(target=server.serve_forever, name="seo22-preload-mirror", daemon=True)
    server_thread.start()
    errors: list[str] = []
    runs: list[dict[str, Any]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=args.chromium)
            chromium_version = browser.version

            # Discovery fills a shared immutable upstream cache. Contexts are discarded before
            # measurement, so browser caches stay cold; all measured responses then come from
            # this local cache through Chromium's real network throttle.
            for variant in ("baseline", "candidate"):
                state.active_variant = variant
                for path in PATHS:
                    for confirmed in (False, True):
                        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=2,
                                                      is_mobile=True, has_touch=True)
                        if confirmed:
                            context.add_init_script(f"localStorage.setItem({json.dumps(AGE_KEY)},String(Date.now()))")
                        discovery_blocked_external: list[dict[str, str]] = []
                        discovery_route_rewrites: list[dict[str, Any]] = []
                        context.route("**/*", controlled_route_handler(args.origin, local_origin, discovery_blocked_external,
                                                                         discovery_route_rewrites))
                        context.add_init_script(INIT)
                        page = context.new_page()
                        try:
                            page.goto(local_origin + path, wait_until="domcontentloaded", timeout=45000)
                            page.wait_for_function("window.seoMeasure?.exit > 0", timeout=45000)
                            try:
                                page.wait_for_load_state("networkidle", timeout=7000)
                            except Exception:
                                pass
                            page.wait_for_timeout(1000)
                        except Exception as error:
                            errors.append(f"cache discovery {variant} {path} confirmed={confirmed}: {type(error).__name__}: {error}")
                        finally:
                            context.close()

            logo_entry = state.get_cached("GET", LOGO_PATH)
            logo_cache_ok = bool(logo_entry and logo_entry[0] == 200 and
                                 any("image/svg+xml" in v.lower() for k, v in logo_entry[1] if k.lower() == "content-type"))
            if not logo_cache_ok:
                raise RuntimeError("The target logo SVG was not captured as HTTP 200 image/svg+xml")
            state.frozen = True

            scenario_index = 0
            repeat_values = (1,) if args.smoke else range(1, 4)
            confirmed_values = (False,) if args.smoke else (False, True)
            for repeat in repeat_values:
                for path in PATHS:
                    for confirmed in confirmed_values:
                        scenario_index += 1
                        order = ("baseline", "candidate") if (repeat + scenario_index) % 2 else ("candidate", "baseline")
                        for variant in order:
                            state.active_variant = variant
                            result: dict[str, Any] = {
                                "run_id": run_id, "path": path, "confirmed": confirmed,
                                "repeat": repeat, "variant": variant, "errors": [], "console_errors": [],
                                "screenshot": None,
                            }
                            misses_before = len(state.cache_misses)
                            context = browser.new_context(viewport=VIEWPORT, device_scale_factor=2,
                                                          is_mobile=True, has_touch=True)
                            if confirmed:
                                context.add_init_script(f"localStorage.setItem({json.dumps(AGE_KEY)},String(Date.now()))")
                            context.add_init_script(INIT)
                            blocked_external: list[dict[str, str]] = []
                            route_rewrites: list[dict[str, Any]] = []
                            context.route("**/*", controlled_route_handler(args.origin, local_origin, blocked_external,
                                                                           route_rewrites))
                            page = context.new_page()
                            requests: list[str] = []
                            response_audit: list[dict[str, Any]] = []
                            page.on("request", lambda request: requests.append(request.url))
                            page.on("response", lambda response: response_audit.append({
                                "path": urllib.parse.urlsplit(response.url).path, "status": response.status,
                                "content_encoding": response.headers.get("content-encoding"),
                                "content_type": response.headers.get("content-type"),
                                "content_length": response.headers.get("content-length"),
                            }) if re.search(r"\.(?:css|js|svg)(?:\?|$)", response.url, re.I) else None)
                            page.on("pageerror", lambda error: result["errors"].append(str(error)))
                            page.on("console", lambda msg: result["console_errors"].append(msg.text) if msg.type == "error" else None)
                            cdp = context.new_cdp_session(page)
                            cdp.send("Network.enable")
                            cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                            cdp.send("Network.emulateNetworkConditions", {
                                "offline": False, "latency": THROTTLE["latency"],
                                "downloadThroughput": THROTTLE["downloadThroughput"],
                                "uploadThroughput": THROTTLE["uploadThroughput"],
                            })
                            cdp.send("Emulation.setCPUThrottlingRate", {"rate": CPU_RATE})
                            try:
                                started = time.monotonic()
                                response = page.goto(local_origin + path, wait_until="domcontentloaded", timeout=60000)
                                result["http_status"] = response.status if response else None
                                page.wait_for_function("window.seoMeasure?.exit > 0", timeout=60000)
                                page.wait_for_timeout(1500)
                                sample = page.evaluate(r"""() => {
                                  const audit = window.seoMeasure || {};
                                  const logo = performance.getEntriesByType('resource')
                                    .filter(e => new URL(e.name).pathname.endsWith('/logo-opening-motion-v2.svg'))
                                    .map(e => ({name:e.name, initiatorType:e.initiatorType, startTime:e.startTime,
                                      fetchStart:e.fetchStart, responseStart:e.responseStart, responseEnd:e.responseEnd,
                                      duration:e.duration, transferSize:e.transferSize,
                                      encodedBodySize:e.encodedBodySize, decodedBodySize:e.decodedBodySize}));
                                  const navigation = performance.getEntriesByType('navigation')[0];
                                  return {...audit,
                                    gateHidden:document.querySelector('[data-age-gate]')?.hidden,
                                    gateConfirmPresent:!!document.querySelector('[data-age-confirm]'),
                                    activeElement:document.activeElement?.tagName || null,
                                    logoVisibleNow:(() => {const img=document.querySelector('#startup-loader .cdt-startup__logo');
                                      if (!img) return null; const s=getComputedStyle(img), r=img.getBoundingClientRect();
                                      return {visible:s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)>0&&r.width>0&&r.height>0,
                                        complete:img.complete,naturalWidth:img.naturalWidth,currentSrc:img.currentSrc};})(),
                                    navigationStart:navigation?.startTime,
                                    ttfb:navigation?.responseStart,
                                    responseEnd:navigation?.responseEnd,
                                    logoEntries:logo,
                                    logoRequestCount:logo.length,
                                    logoFirstStartMs:logo.length ? Math.min(...logo.map(e=>e.startTime)) : null,
                                    logoTransferBytes:logo.reduce((n,e)=>n+e.transferSize,0),
                                    initialMapSrc:document.querySelector('#store-contact iframe')?.getAttribute('src') || null,
                                    resourceBytes:performance.getEntriesByType('resource').reduce((n,e)=>n+e.encodedBodySize,0)
                                  };
                                }""")
                                result.update(sample)
                                result["effective_page_url"] = page.url
                                result["navigation_response_url"] = response.url if response else None
                                result["navigation_response_content_encoding"] = response.headers.get("content-encoding") if response else None
                                result["response_audit"] = response_audit
                                result["blocked_external_requests"] = blocked_external
                                result["first_party_route_rewrites"] = route_rewrites
                                if not confirmed and result.get("gateHidden") is False:
                                    page.locator('[data-age-confirm]').click(timeout=5000)
                                    page.wait_for_function("document.querySelector('[data-age-gate]')?.hidden === true", timeout=5000)
                                    result["age_confirmation_click_hid_gate"] = True
                                    result["age_confirmation_storage_set"] = page.evaluate(f"localStorage.getItem({json.dumps(AGE_KEY)}) !== null")
                                else:
                                    result["age_confirmation_click_hid_gate"] = None
                                    result["age_confirmation_storage_set"] = None
                                result["wall_ms"] = (time.monotonic() - started) * 1000
                                result["handoff_ms"] = result["exit"] - result["ready"] if result.get("exit") and result.get("ready") else None
                                result["logo_duplicate_requests"] = max(0, result.get("logoRequestCount", 0) - 1)
                                result["logo_request_initiators"] = [e["initiatorType"] for e in result.get("logoEntries", [])]
                                result["initialMapRequests"] = sum("yandex" in url.lower() for url in requests)
                                result["cache_misses"] = len(state.cache_misses) - misses_before
                                result["passed"] = (
                                    result["http_status"] == 200
                                    and result.get("gateHidden") == confirmed
                                    and bool(result.get("ready")) and bool(result.get("exit"))
                                    and result.get("startupFrames", 0) > 0
                                    and result.get("logoVisibleFrames", 0) > 0
                                    and result.get("logoImageLoadedFrames", 0) > 0
                                    and result.get("logoRequestCount", 0) == 1
                                    and result.get("logo_duplicate_requests", 0) == 0
                                    and result.get("logoTransferBytes", 0) > 0
                                    and all(e.get("transferSize", 0) > 0 and e.get("encodedBodySize", 0) > 0
                                            for e in result.get("logoEntries", []))
                                    and result.get("overlaps", 0) == 0
                                    and result.get("earlyFocus", 0) == 0
                                    and result.get("initialMapRequests", 0) == 0
                                    and not result.get("initialMapSrc")
                                    and result.get("cache_misses", 0) == 0
                                    and not result["errors"]
                                    and not any(re.search(r"cors|hydration|did not match|server html", message, re.I)
                                                for message in result["console_errors"])
                                    and (confirmed or (result.get("age_confirmation_click_hid_gate") is True and result.get("age_confirmation_storage_set") is True))
                                )
                                if not result["passed"]:
                                    shot = output_dir / f"failure-{repeat}-{variant}-{path.strip('/').replace('/', '_') or 'home'}-confirmed-{int(confirmed)}.png"
                                    page.screenshot(path=str(shot), full_page=True)
                                    result["screenshot"] = shot.name
                            except Exception as error:
                                result.update(passed=False, exception=f"{type(error).__name__}: {error}")
                                shot = output_dir / f"failure-{repeat}-{variant}-{path.strip('/').replace('/', '_') or 'home'}-confirmed-{int(confirmed)}.png"
                                try:
                                    page.screenshot(path=str(shot), full_page=True, timeout=10000)
                                    result["screenshot"] = shot.name
                                except Exception:
                                    pass
                            finally:
                                context.close()
                            runs.append(result)
                            print(json.dumps({k: result.get(k) for k in ("repeat", "path", "confirmed", "variant", "passed", "ready", "exit", "lcp", "cls", "logoRequestCount", "initialMapRequests", "exception")}, ensure_ascii=False), flush=True)
                            report = {
                                "run_id": run_id,
                                "captured_at_utc": captured_at,
                                "measurement_location": args.location,
                                "release_sha": args.release_sha,
                                "origin": args.origin.rstrip("/"),
                                "mirror_origin": local_origin,
                                "html_snapshots": html_metadata,
                                "html_candidate_delta": "after applying the same gzip encoding (level 6, mtime 0) to both arms, baseline is captured production decoded HTML and candidate differs by exactly one preload link immediately after the last stylesheet link",
                                "captured_production_html_wire_hashes": "recorded separately in html_snapshots; baseline/candidate browser responses are recompressed identically for controlled comparison",
                                "preload_markup": PRELOAD,
                                "static_asset_source": "same production origin; raw response bodies and Content-Encoding headers cached once and served locally during all measured runs",
                                "absolute_origin_replay": "Playwright route.continue rewrites first-party production-origin requests to the local mirror; all other external requests are aborted; no route.fulfill",
                                "gzip_handling": "captured production HTML wire hash retained separately; both decoded HTML variants are gzip-compressed with level 6 and mtime 0; shared production CSS/JS raw gzip bytes and Content-Encoding are preserved",
                                "browser_cache": "disabled in every measured context; separate contexts; local mirror cache frozen before A/B",
                                "throttle": {"viewport": VIEWPORT, "device_scale_factor": 2, **THROTTLE, "cpu_slowdown": CPU_RATE},
                                "order": "paired/interleaved by scenario and repeat; one page/context at a time",
                                "chromium_version": chromium_version,
                                "mirror_cache_misses": len(state.cache_misses),
                                "upstream_cache_fetch_count": len(state.proxy_fetches),
                                "upstream_cached_resources": state.proxy_fetches,
                                "cache_discovery_errors": errors,
                        "runner": {"hostname": platform.node(), "platform": platform.platform(),
                                   "processor": platform.processor(), "logical_cpu_count": os.cpu_count()},
                        "smoke_only_unconfirmed": args.smoke,
                        "runs": runs,
                                "summary_medians": median_summary(runs),
                            }
                            (output_dir / "seo22-preload-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    columns = (
        "repeat", "path", "confirmed", "variant", "http_status", "ready", "exit", "handoff_ms",
        "lcp", "cls", "logoRequestCount", "logo_duplicate_requests", "logoFirstStartMs",
        "logoTransferBytes", "logo_request_initiators", "initialMapRequests", "initialMapSrc",
        "overlaps", "earlyFocus", "startupFrames", "logoVisibleFrames", "logoImageLoadedFrames", "logoFirstVisible", "logoFirstVisibleSrc", "logoVisibleNow",
        "gateHidden", "activeElement", "age_confirmation_click_hid_gate", "age_confirmation_storage_set", "resourceBytes",
        "wall_ms", "cache_misses", "passed", "exception", "screenshot",
    )
    with (output_dir / "seo22-preload-runs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in runs:
            writer.writerow({**row, "logo_request_initiators": ";".join(row.get("logo_request_initiators", []))})

    expected = len(PATHS) * (1 if args.smoke else 2) * (1 if args.smoke else 3) * 2
    passed = len(runs) == expected and all(row.get("passed") for row in runs)
    print(json.dumps({"run_id": run_id, "runs": len(runs), "expected_runs": expected,
                      "passed": passed, "output_dir": str(output_dir),
                      "cache_misses": len(state.cache_misses), "cache_discovery_errors": errors}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="https://cigardomtabaka.com")
    parser.add_argument("--release-sha", required=True, help="Read-only verified production commit SHA")
    parser.add_argument("--location", required=True, help="Runner location, or explicitly say unverified")
    parser.add_argument("--chromium", default="/snap/bin/chromium")
    parser.add_argument("--output-dir", type=Path, default=Path("docs/data/seo22-preload-20261029"))
    parser.add_argument("--cache-dir", type=Path, help="Temporary response cache; defaults to /tmp")
    parser.add_argument("--smoke", action="store_true", help="Run one unconfirmed first-visit pair on each page (6 samples)")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
