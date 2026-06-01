#!/usr/bin/env python3
"""Download TimeCigar mini cigar images via CDP. Parses AJAX HTML in browser JS."""
import asyncio, json, os, base64, urllib.request, sys, re
import websockets
from pathlib import Path
from urllib.parse import unquote
import unicodedata

MEDIA_ROOT = os.path.expanduser("~/moscow_cigar/media/cigars")
CDP_PORT = 9222

BRAND_IDS = {2:"Cohiba", 18:"Guantanamera", 30:"Montecristo", 32:"Partagás", 40:"Romeo y Julieta", 45:"Trinidad"}

def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[-\s]+', '-', re.sub(r'[^\w\s-]', '', s.lower()).strip())

async def cdp_call(ws, method, params=None):
    cdp_call._id = getattr(cdp_call, '_id', 0) + 1
    await ws.send(json.dumps({"id": cdp_call._id, "method": method, "params": params or {}}))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == cdp_call._id:
            return resp

def get_cdp():
    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json").read())
    for t in targets:
        if t["type"] == "page":
            return t["webSocketDebuggerUrl"]

async def scrape_brand_js(ws, brand_id):
    """Run JS in browser to fetch + parse AJAX product list pages."""
    js = f"""
    (async () => {{
        const all = [];
        for (let pg = 1; pg <= 10; pg++) {{
            const resp = await fetch('/pages/product/ajax_load_product_list?id=34&brand={brand_id}&page=' + pg + '&price_sort=lowest');
            const html = await resp.text();
            if (!html.includes('product_card_item')) break;
            
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const cards = doc.querySelectorAll('.product_card_item');
            if (cards.length === 0) break;
            
            cards.forEach(card => {{
                const link = card.querySelector('a[data-alink]');
                if (!link) return;
                const href = link.getAttribute('href');
                const pid = new URLSearchParams(href.split('?')[1]).get('product_id');
                const name = link.textContent.trim();
                const imgs = [...card.querySelectorAll('img[src*="product_profile"]')].map(i => i.src);
                all.push({{product_id: pid, name, images: imgs}});
            }});
        }}
        return JSON.stringify(all);
    }})()
    """
    resp = await cdp_call(ws, "Runtime.evaluate", {
        "expression": js, "returnByValue": True,
        "awaitPromise": True, "timeout": 60000
    })
    raw = resp.get("result", {}).get("result", {}).get("value", "[]")
    return json.loads(raw)

async def download_batch(ws, urls):
    js = f"""
    (async () => {{
        const urls = {json.dumps(urls)};
        const results = {{}};
        await Promise.all(urls.map(async (url) => {{
            try {{
                const resp = await fetch(url);
                if (!resp.ok) {{ results[url] = {{error: resp.status}}; return; }}
                const buf = await resp.arrayBuffer();
                const bytes = new Uint8Array(buf);
                let binary = '';
                for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                results[url] = {{data: btoa(binary)}};
            }} catch(e) {{ results[url] = {{error: String(e)}}; }}
        }}));
        return JSON.stringify(results);
    }})()
    """
    resp = await cdp_call(ws, "Runtime.evaluate", {
        "expression": js, "returnByValue": True,
        "awaitPromise": True, "timeout": 60000
    })
    return json.loads(resp.get("result", {}).get("result", {}).get("value", "{}"))

async def main():
    cdp_url = get_cdp()
    if not cdp_url:
        print("No CDP page!"); return
    
    async with websockets.connect(cdp_url, max_size=200*1024*1024) as ws:
        await cdp_call(ws, "Page.navigate", {"url": "https://www.timecigar.com/tc/cuban_mini_cigars"})
        await asyncio.sleep(3)
        
        all_products = []
        for bid, bname in BRAND_IDS.items():
            print(f"Scraping {bname} (brand_id={bid})...")
            products = await scrape_brand_js(ws, bid)
            for p in products:
                p['brand'] = bname
            all_products.extend(products)
            print(f"  → {len(products)} products")
        
        # Deduplicate by product_id (TC has duplicate listings per pack variant)
        seen_pids = set()
        unique_products = []
        for p in all_products:
            if p['product_id'] not in seen_pids:
                seen_pids.add(p['product_id'])
                unique_products.append(p)
        
        print(f"\nTotal: {len(all_products)} raw, {len(unique_products)} unique products")
        
        # Collect all image URLs
        url_map = {}
        for p in unique_products:
            for url in p['images']:
                if url not in url_map:
                    url_map[url] = p
        
        all_urls = list(url_map.keys())
        print(f"Images to download: {len(all_urls)}")
        
        # Download
        dl = skip = fail = 0
        BATCH = 8
        for i in range(0, len(all_urls), BATCH):
            batch = all_urls[i:i+BATCH]
            results = await download_batch(ws, batch)
            
            for url in batch:
                result = results.get(url, {})
                p = url_map[url]
                
                # Build directory: brand_slug / product_slug
                brand_slug = slugify(p['brand'])
                en_name = re.sub(r'[\u4e00-\u9fff]+', '', p['name']).strip()
                name_slug = slugify(en_name) if en_name else slugify(p['name'])
                
                dir_path = Path(MEDIA_ROOT) / brand_slug / name_slug
                fname = unquote(url.split('/')[-1])
                save_path = dir_path / fname
                
                if save_path.exists():
                    skip += 1; continue
                
                if 'error' in result:
                    fail += 1; continue
                
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(base64.b64decode(result['data']))
                dl += 1
            
            pct = min(100, int((i+BATCH)/len(all_urls)*100))
            print(f"  [{pct:3d}%] {i+len(batch)}/{len(all_urls)} | dl:{dl} skip:{skip} fail:{fail}")
            await asyncio.sleep(0.3)
    
    print(f"\nDone! Downloaded: {dl}, Skipped: {skip}, Failed: {fail}")

asyncio.run(main())
