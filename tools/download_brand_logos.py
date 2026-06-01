#!/usr/bin/env python3
"""Download brand logos from CCW via CDP browser fetch()."""
import asyncio, json, os, base64, urllib.request, sys
import websockets

JSON_PATH = os.path.expanduser("~/moscow_cigar/brand_logos.json")
MEDIA_ROOT = os.path.expanduser("~/moscow_cigar/media/brand_logos")
CDP_PORT = 9222

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
    return None

async def main():
    with open(JSON_PATH) as f:
        brands = json.load(f)
    
    os.makedirs(MEDIA_ROOT, exist_ok=True)
    cdp_url = get_cdp()
    if not cdp_url:
        print("No CDP page!")
        return

    urls = [b['url'] for b in brands]
    print(f"Downloading {len(urls)} brand logos...")
    
    # Build fetch JS
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
            }} catch(e) {{
                results[url] = {{error: String(e)}};
            }}
        }}));
        return JSON.stringify(results);
    }})()
    """

    async with websockets.connect(cdp_url, max_size=50*1024*1024) as ws:
        resp = await cdp_call(ws, "Runtime.evaluate", {
            "expression": js, "returnByValue": True,
            "awaitPromise": True, "timeout": 60000
        })
    
    raw = resp.get("result", {}).get("result", {}).get("value", "{}")
    results = json.loads(raw)
    
    ok = 0
    fail = 0
    for b in brands:
        url = b['url']
        r = results.get(url, {})
        if 'error' in r:
            print(f"  ✗ {b['brand']}: {r['error']}")
            fail += 1
        else:
            # Save file: use brand name as filename
            brand_slug = b['brand'].lower().replace(' ', '-').replace('.', '').replace("'", '')
            ext = url.rsplit('.', 1)[-1]
            fname = f"{brand_slug}.{ext}"
            fpath = os.path.join(MEDIA_ROOT, fname)
            with open(fpath, 'wb') as f:
                f.write(base64.b64decode(r['data']))
            print(f"  ✓ {b['brand']} → {fname}")
            ok += 1
    
    print(f"\nDone: {ok} ok, {fail} fail")

asyncio.run(main())
