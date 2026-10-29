"""Read-only mobile browser measurements; requires Playwright and Chromium locally.

Each scenario uses a fresh browser context and a disabled HTTP cache. Yandex
downloads are blocked, matching the SEO-22 first-party baseline. This measures
navigation/loader timing and browser metrics, not PageSpeed scores or field CWV.
"""
import argparse
import csv
import json
import os
import platform
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


PATHS = ('/', '/ru/brand/cohiba', '/ru/cigar/103/cohiba-magicos')
INIT = r"""(() => {
  const audit = window.seoMeasure = {started:false, ready:0, exit:0,
    lcp:0, cls:0, overlaps:0, earlyFocus:0, startupFrames:0};
  try {new PerformanceObserver(list => list.getEntries().forEach(e => {
    if (!e.hadRecentInput) audit.cls += e.value;
  })).observe({type:'layout-shift',buffered:true});} catch {}
  try {new PerformanceObserver(list => list.getEntries().forEach(e => {
    audit.lcp = e.startTime;
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


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        'origin': args.origin.rstrip('/'), 'release_sha': args.release_sha,
        'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'measurement_location': args.location, 'viewport': {'width': 390, 'height': 844},
        'device_scale_factor': 2, 'latency_ms': 150, 'download_bytes_per_second': 200000,
        'upload_bytes_per_second': 93750, 'cpu_slowdown': 4,
        'browser_cache': 'disabled', 'yandex_downloads': 'blocked', 'runs': [],
        'runner': {'hostname': platform.node(), 'platform': platform.platform(),
                   'processor': platform.processor(), 'logical_cpu_count': os.cpu_count(),
                   'region_verified': False},
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.chromium)
        report['chromium_version'] = browser.version
        for repeat in range(1, args.repeats + 1):
            for path in PATHS:
                for confirmed in (False, True):
                    result = {'path': path, 'confirmed': confirmed, 'repeat': repeat, 'errors': []}
                    context = browser.new_context(viewport=report['viewport'], device_scale_factor=2,
                                                  is_mobile=True, has_touch=True)
                    if confirmed:
                        context.add_init_script("try {localStorage.setItem('cdt.customer.age-confirmed-at',String(Date.now()));} catch {}")
                    context.add_init_script(INIT)
                    context.route(re.compile(r'https?://[^/]*yandex[^/]*/', re.I), lambda route: route.abort())
                    page = context.new_page()
                    requests = []
                    page.on('request', lambda request: requests.append(request.url))
                    page.on('pageerror', lambda error: result['errors'].append(str(error)))
                    cdp = context.new_cdp_session(page)
                    cdp.send('Network.enable')
                    cdp.send('Network.setCacheDisabled', {'cacheDisabled': True})
                    cdp.send('Network.emulateNetworkConditions', {
                        'offline': False, 'latency': 150, 'downloadThroughput': 200000,
                        'uploadThroughput': 93750,
                    })
                    cdp.send('Emulation.setCPUThrottlingRate', {'rate': 4})
                    try:
                        response = page.goto(report['origin'] + path, wait_until='domcontentloaded', timeout=45000)
                        result['http_status'] = response.status if response else None
                        page.wait_for_function('window.seoMeasure?.exit > 0', timeout=45000)
                        page.wait_for_timeout(1000)
                        result.update(page.evaluate(r"""() => ({...window.seoMeasure,
                          gateHidden:document.querySelector('[data-age-gate]')?.hidden,
                          resourceBytes:performance.getEntriesByType('resource').reduce((n,e)=>n+e.encodedBodySize,0),
                          ttfb:performance.getEntriesByType('navigation')[0]?.responseStart,
                          responseEnd:performance.getEntriesByType('navigation')[0]?.responseEnd,
                          domContentLoaded:performance.getEntriesByType('navigation')[0]?.domContentLoadedEventEnd,
                          loadEvent:performance.getEntriesByType('navigation')[0]?.loadEventEnd,
                          initialMapSrc:document.querySelector('#store-contact iframe')?.getAttribute('src'),
                          images:[...document.querySelectorAll('.store-home-hero img, .site-brand img, [data-gallery-main]')]
                            .map(img=>({src:img.currentSrc,naturalWidth:img.naturalWidth,width:img.getBoundingClientRect().width,
                              complete:img.complete,encodedBytes:performance.getEntriesByName(img.currentSrc).reduce((n,e)=>n+e.encodedBodySize,0)}))
                        })"""))
                        result['initialMapRequests'] = sum('yandex' in url.lower() for url in requests)
                        result['ratesRequests'] = sum('/api/storefront/rates/' in url for url in requests)
                        result['handoff_ms'] = result['exit'] - result['ready']
                        result['passed'] = (result['http_status'] == 200 and result['gateHidden'] == confirmed
                                            and result['ready'] > 0 and result['startupFrames'] > 0
                                            and not result['overlaps'] and not result['earlyFocus']
                                            and not result['initialMapRequests'] and not result['initialMapSrc']
                                            and not result['errors'])
                        # Trigger the lazy map after recording the untouched first-view request set.
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        try:
                            page.wait_for_function("document.querySelector('#store-contact iframe')?.getAttribute('src')", timeout=15000)
                            result['mapTriggeredAfterScroll'] = True
                        except Exception:
                            result['mapTriggeredAfterScroll'] = False
                        result['mapSrcAfterScroll'] = page.locator('#store-contact iframe').get_attribute('src') if page.locator('#store-contact iframe').count() else None
                        result['mapRequestsAfterScroll'] = sum('yandex' in url.lower() for url in requests)
                    except Exception as error:
                        result.update(passed=False, exception=f'{type(error).__name__}: {error}')
                    finally:
                        context.close()
                    report['runs'].append(result)
                    (args.output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
                    print(json.dumps({k: result.get(k) for k in ('path','confirmed','repeat','passed','ready','exit','lcp','cls','exception')}), flush=True)
        browser.close()
    report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    (args.output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    columns = ('path','confirmed','repeat','http_status','ttfb','responseEnd','domContentLoaded','loadEvent',
               'ready','exit','handoff_ms','lcp','cls',
               'overlaps','earlyFocus','startupFrames','initialMapRequests','mapTriggeredAfterScroll',
               'mapRequestsAfterScroll','ratesRequests','resourceBytes','passed')
    with (args.output / 'measurements.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(report['runs'])
    return 0 if all(row['passed'] for row in report['runs']) else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='https://cigardomtabaka.com')
    parser.add_argument('--release-sha', required=True, help='Read-only verified production SHA before and after measuring')
    parser.add_argument('--location', required=True, help='Known runner location, or explicitly unverified')
    parser.add_argument('--chromium', default='/snap/bin/chromium')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('Use at least three repeats per scenario')
    raise SystemExit(run(args))
