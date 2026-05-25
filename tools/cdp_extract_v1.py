#!/usr/bin/env python3
"""Extract cigar data from brand pages via CDP and save to JSON files."""
import asyncio, json, os, re
import websockets

CDP = "ws://127.0.0.1:9222/devtools/browser/4c14306e-d272-457c-8a4b-f520df4a426e"
BASE = "https://www.cubancigarwebsite.com"
OUT = os.path.expanduser("~/.hermes/cigar_inventory")

BRANDS = [
    ("diplomaticos", "Diplomáticos"),
    ("el-rey-del-mundo", "El Rey del Mundo"),
    ("juan-lopez", "Juan López"),
    ("la-flor-de-cano", "La Flor de Cano"),
    ("la-gloria-cubana", "La Gloria Cubana"),
    ("por-larranaga", "Por Larrañaga"),
    ("saint-luis-rey", "Saint Luis Rey"),
    ("san-cristobal", "San Cristóbal"),
    ("sancho-panza", "Sancho Panza"),
    ("vegas-robaina", "Vegas Robaina"),
]

async def cdp_call(ws, method, params=None):
    msg_id = getattr(cdp_call, '_id', 0) + 1
    cdp_call._id = msg_id
    await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == msg_id:
            return resp.get("result", {})

async def extract_brand(ws, slug, name):
    """Navigate to brand page and extract data."""
    # Navigate
    result = await cdp_call(ws, "Page.navigate", {"url": f"{BASE}/brand/{slug}"})
    await asyncio.sleep(2)
    
    # Extract via JS
    js_code = f"""
    (function() {{
        var slug = '{slug}';
        var name = '{name}';
        var BASE = 'https://www.cubancigarwebsite.com';
        var result = [];
        var table = document.querySelector('.maintable');
        if (!table) return JSON.stringify([]);
        var rows = Array.from(table.children);
        var sec = 'Current';
        var seen = {{}};
        
        for (var i = 0; i < rows.length; i++) {{
            var row = rows[i];
            var cls = row.className || '';
            if (cls.indexOf('section-head') >= 0 || (cls.indexOf('entry') >= 0 && cls.indexOf('text-center') >= 0)) {{
                var t = row.textContent.trim();
                if (t.indexOf('Current Production') >= 0) sec = 'Current';
                else if (t.indexOf('Discontinued Production') >= 0) sec = 'Discontinued';
                else if (t.indexOf('Special Releases') >= 0) sec = 'Special Releases';
                continue;
            }}
            if (cls.indexOf('entry') < 0) continue;
            
            var links = row.querySelectorAll('a');
            var pu = '', pn = '', vt = '', cn = '';
            var rg = null, ln = null;
            
            for (var j = 0; j < links.length; j++) {{
                var h = links[j].getAttribute('href') || '';
                if (h.indexOf('/cigar/' + slug + '/') >= 0 && h.match(new RegExp('/cigar/' + slug + '/[^/]+$'))) {{
                    if (seen[h]) {{ pu = ''; break; }}
                    seen[h] = true;
                    pu = BASE + h;
                    pn = links[j].textContent.trim();
                }}
                if (h.indexOf('factorynames=') >= 0) vt = links[j].textContent.trim();
                if (h.indexOf('commonnames=') >= 0) cn = links[j].textContent.trim();
            }}
            if (!pu) continue;
            
            var ft = row.textContent;
            var dm = ft.match(/Ring\\s*gaugerg?\\s*(\\d+(?:\\.\\d+)?)\\s*[×x]\\s*Length\\s*MMT\\s*(\\d+(?:\\.\\d+)?)\\s*mm/i);
            if (dm) {{ rg = parseFloat(dm[1]); ln = parseFloat(dm[2]); }}
            
            var pm = ft.match(/Packaging:\\s*([^]*?)(?=Status:|$)/);
            var pr = pm ? pm[1].replace(/\\s+/g, ' ').trim().substring(0, 500) : '';
            var sm = ft.match(/Status:\\s*([^\\n]+)/);
            var st = sm ? sm[1].trim() : '';
            
            var rt = '';
            for (var k = 0; k < links.length; k++) {{
                if ((links[k].getAttribute('href') || '').indexOf('types=') >= 0) {{
                    var tt = links[k].textContent.trim();
                    if (tt.indexOf('Limited Edition') >= 0) rt = 'Edición Limitada';
                    else if (tt.indexOf('Regional Edition') >= 0) rt = 'Edición Regional';
                    else if (tt.indexOf('Habanos Collection') >= 0) rt = 'Colección Habanos';
                    else if (tt.indexOf('Commemorative') >= 0) rt = 'Commemorative Release';
                    else rt = tt;
                }}
            }}
            if (rt && sec === 'Special Releases') {{
                var ym = st.match(/(\\d{{4}})/);
                if (ym && rt.indexOf(ym[1]) < 0) rt += ' ' + ym[1];
            }}
            
            var bs = [];
            var bm = pr.matchAll(/(?:box|pack|jar|humidor)\\s+(?:of\\s+)?(\\d+)/gi);
            var bmArr = Array.from(bm);
            for (var m = 0; m < bmArr.length; m++) {{
                var s = parseInt(bmArr[m][1]);
                if (s <= 100 && bs.indexOf(s) < 0) bs.push(s);
            }}
            bs.sort(function(a,b){{return a-b;}});
            
            result.push({{
                brand: name, name: pn, vitola: vt,
                ringGauge: rg, lengthMm: ln, commonName: cn,
                status: sec === 'Special Releases' ? 'Special Releases' : sec,
                releaseType: rt, url: pu, packagingRaw: pr, boxSizes: bs
            }});
        }}
        return JSON.stringify(result);
    }})()
    """
    
    eval_result = await cdp_call(ws, "Runtime.evaluate", {
        "expression": js_code,
        "returnByValue": True
    })
    
    value = eval_result.get("result", {}).get("value", "[]")
    products = json.loads(value)
    return products

async def main():
    async with websockets.connect(CDP, max_size=50*1024*1024) as ws:
        # Enable Page domain
        await cdp_call(ws, "Page.enable")
        await cdp_call(ws, "Runtime.enable")
        
        total = 0
        for slug, name in BRANDS:
            print(f"Extracting {name}...", end=" ", flush=True)
            products = await extract_brand(ws, slug, name)
            
            filepath = os.path.join(OUT, f"{slug}.json")
            with open(filepath, 'w') as f:
                json.dump(products, f, indent=2, ensure_ascii=False)
            
            print(f"{len(products)} products saved")
            total += len(products)
        
        print(f"\nDone! {total} total products across {len(BRANDS)} brands")

asyncio.run(main())
