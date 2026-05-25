#!/usr/bin/env python3
"""CDP extract FIXED: handle duplicate product links in same entry."""
import asyncio, json, os, urllib.request
import websockets

BASE = "https://www.cubancigarwebsite.com"
OUT = os.path.expanduser("~/.hermes/cigar_inventory")
BRANDS = [
    ("diplomaticos", "Diplomáticos"), ("el-rey-del-mundo", "El Rey del Mundo"),
    ("juan-lopez", "Juan López"), ("la-flor-de-cano", "La Flor de Cano"),
    ("la-gloria-cubana", "La Gloria Cubana"), ("por-larranaga", "Por Larrañaga"),
    ("saint-luis-rey", "Saint Luis Rey"), ("san-cristobal", "San Cristóbal"),
    ("sancho-panza", "Sancho Panza"), ("vegas-robaina", "Vegas Robaina"),
]

def get_page_cdp():
    targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json").read())
    for t in targets:
        if t["type"] == "page":
            return t["webSocketDebuggerUrl"]
    return None

async def cdp_call(ws, method, params=None):
    cdp_call._id = getattr(cdp_call, '_id', 0) + 1
    await ws.send(json.dumps({"id": cdp_call._id, "method": method, "params": params or {}}))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == cdp_call._id:
            return resp

async def main():
    cdp_url = get_page_cdp()
    if not cdp_url: print("No page CDP!"); return
    
    async with websockets.connect(cdp_url, max_size=50*1024*1024) as ws:
        total = 0
        for slug, name in BRANDS:
            print(f"{name}...", end=" ", flush=True)
            await cdp_call(ws, "Page.navigate", {"url": f"{BASE}/brand/{slug}"})
            await asyncio.sleep(2)
            
            extract_js = f"""
(function() {{
    var slug='{slug}',name='{name}',BASE='https://www.cubancigarwebsite.com';
    var result=[],table=document.querySelector('.maintable');
    if(!table) return JSON.stringify([]);
    var rows=table.children,sec='Current',seen={{}};
    
    for(var i=0;i<rows.length;i++){{
        var row=rows[i],cls=row.className||'';
        if(cls.indexOf('section-head')>=0||(cls.indexOf('entry')>=0&&cls.indexOf('text-center')>=0)){{
            var t=row.textContent.trim();
            if(t.indexOf('Current Production')>=0) sec='Current';
            else if(t.indexOf('Discontinued Production')>=0) sec='Discontinued';
            else if(t.indexOf('Special Releases')>=0) sec='Special Releases';
            continue;
        }}
        if(cls.indexOf('entry')<0) continue;
        
        var links=row.querySelectorAll('a');
        var pu='',pn='',vt='',cn='',rg=null,ln=null;
        
        for(var j=0;j<links.length;j++){{
            var h=links[j].getAttribute('href')||'';
            var prefix='/cigar/'+slug+'/';
            if(h.indexOf(prefix)===0){{
                var rest=h.substring(prefix.length);
                if(rest.indexOf('/')<0&&rest.indexOf('?')<0){{
                    if(seen[h]){{ continue; }}  // FIX: continue not break!
                    seen[h]=true;
                    pu=BASE+h;
                    pn=links[j].textContent.trim();
                }}
            }}
            if(h.indexOf('factorynames=')>=0) vt=links[j].textContent.trim();
            if(h.indexOf('commonnames=')>=0) cn=links[j].textContent.trim();
        }}
        if(!pu) continue;
        
        var ft=row.textContent;
        var dm=ft.match(/Ring\\s*gaugerg?\\s*(\\d+(?:\\.\\d+)?)\\s*[×x]\\s*Length\\s*MMT\\s*(\\d+(?:\\.\\d+)?)\\s*mm/i);
        if(dm){{rg=parseFloat(dm[1]);ln=parseFloat(dm[2]);}}
        var pm=ft.match(/Packaging:\\s*([\\s\\S]*?)(?=Status:|$)/);
        var pr=pm?pm[1].replace(/\\s+/g,' ').trim().substring(0,500):'';
        var sm=ft.match(/Status:\\s*([^\\n]+)/);
        var st=sm?sm[1].trim():'';
        
        var rt='';
        for(var k=0;k<links.length;k++){{
            var lh=links[k].getAttribute('href')||'';
            if(lh.indexOf('types=')>=0){{
                var tt=links[k].textContent.trim();
                if(tt.indexOf('Limited Edition')>=0) rt='Edicion Limitada';
                else if(tt.indexOf('Regional Edition')>=0) rt='Edicion Regional';
                else if(tt.indexOf('Habanos Collection')>=0) rt='Coleccion Habanos';
                else if(tt.indexOf('Millennium Reserve')>=0) rt='Reserva del Milenio';
                else if(tt.indexOf('Commemorative')>=0) rt='Commemorative Release';
                else rt=tt;
            }}
        }}
        if(rt&&sec==='Special Releases'){{var ym=st.match(/(\\d{{4}})/);if(ym&&rt.indexOf(ym[1])<0) rt+=' '+ym[1];}}
        
        var bs=[],re=/(?:box|pack|jar|humidor)\\s+(?:of\\s+)?(\\d+)/gi,m;
        while((m=re.exec(pr))!==null){{var s=parseInt(m[1]);if(s<=100&&bs.indexOf(s)<0) bs.push(s);}}
        bs.sort(function(a,b){{return a-b;}});
        
        result.push({{brand:name,name:pn,vitola:vt,ringGauge:rg,lengthMm:ln,commonName:cn,status:sec==='Special Releases'?'Special Releases':sec,releaseType:rt,url:pu,packagingRaw:pr,boxSizes:bs}});
    }}
    return JSON.stringify(result);
}})()
"""
            
            resp = await cdp_call(ws, "Runtime.evaluate", {
                "expression": extract_js, "returnByValue": True
            })
            
            raw = resp.get("result", {}).get("result", {}).get("value", "[]")
            products = json.loads(raw)
            
            filepath = os.path.join(OUT, f"{slug}.json")
            with open(filepath, 'w') as f:
                json.dump(products, f, indent=2, ensure_ascii=False)
            
            print(f"{len(products)} products")
            total += len(products)
        
        print(f"\nTotal: {total} products")

asyncio.run(main())
