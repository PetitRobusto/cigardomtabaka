#!/usr/bin/env python3
"""CDP extract v5: Uses cigarDetailsHead for ALL entries (Current, Discontinued, Special)."""
import asyncio, json, os, urllib.request, sys
import websockets

BASE = "https://www.cubancigarwebsite.com"
OUT = os.path.expanduser("~/.hermes/cigar_inventory")

BRAND_MAP = {
    'bolivar': 'Bolívar', 'cohiba': 'Cohiba', 'cuaba': 'Cuaba',
    'diplomaticos': 'Diplomáticos', 'el-rey-del-mundo': 'El Rey del Mundo',
    'fonseca': 'Fonseca', 'h-upmann': 'H. Upmann', 'hoyo-de-monterrey': 'Hoyo de Monterrey',
    'jose-l-piedra': 'José L. Piedra', 'juan-lopez': 'Juan López',
    'la-flor-de-cano': 'La Flor de Cano', 'la-gloria-cubana': 'La Gloria Cubana',
    'montecristo': 'Montecristo', 'partagas': 'Partagás', 'por-larranaga': 'Por Larrañaga',
    'punch': 'Punch', 'quai-dorsay': "Quai d'Orsay", 'quintero': 'Quintero',
    'rafael-gonzalez': 'Rafael González', 'ramon-allones': 'Ramón Allones',
    'romeo-y-julieta': 'Romeo y Julieta', 'saint-luis-rey': 'Saint Luis Rey',
    'san-cristobal': 'San Cristóbal', 'sancho-panza': 'Sancho Panza',
    'trinidad': 'Trinidad', 'vegas-robaina': 'Vegas Robaina', 'vegueros': 'Vegueros'
}

BRANDS = list(BRAND_MAP.items())

EXTRACT_JS_TEMPLATE = r"""
(function() {
    var BASE='https://www.cubancigarwebsite.com', brandName="__BRAND_NAME__";
    var mt=document.querySelector('.maintable');
    if(!mt) return JSON.stringify({error:'No maintable',brand:brandName,results:[]});
    var children=Array.from(mt.children),currentSection='Current',results=[];
    
    for(var i=0;i<children.length;i++){
        var row=children[i],cls=row.className||'';
        if(cls.indexOf('section-head')>=0){
            var t=row.textContent.trim();
            if(/Current\s*Production/i.test(t)) currentSection='Current';
            else if(/Discontinued\s*Production/i.test(t)) currentSection='Discontinued';
            else if(/Special\s*Releases/i.test(t)) currentSection='Special Releases';
            continue;
        }
        if(cls.indexOf('text-center')>=0) continue;
        if(cls.indexOf('entry')<0) continue;
        
        var detailsHeads=row.querySelectorAll('.cigarDetailsHead');
        if(detailsHeads.length===0) continue;
        
        var isSpecial=currentSection==='Special Releases';
        var releaseName='',releaseUrl='',releaseType='';
        
        if(isSpecial){
            var rnEl=row.querySelector('.cigarReleaseName a');
            releaseName=rnEl?rnEl.textContent.trim():'';
            releaseUrl=rnEl?(rnEl.getAttribute('href')||''):'';
            var rtEl=row.querySelector('.srsub a');
            releaseType=rtEl?rtEl.textContent.trim():'';
        }
        
        var subCigars=[];
        for(var j=0;j<detailsHeads.length;j++){
            var dh=detailsHeads[j];
            // Name: try <a> first (Current), then textContent (Special Releases)
            var nameDiv=dh.querySelector('.cigarDetailsName');
            var cigarName='';
            if(nameDiv){
                var nameA=nameDiv.querySelector('a[name]');
                if(nameA) cigarName=nameA.textContent.trim();
                else {
                    // Special Releases: text directly in div, strip hidden spans
                    var clone=nameDiv.cloneNode(true);
                    var hidden=clone.querySelectorAll('[style*=\"display:none\"], [itemprop=\"brand\"]');
                    for(var hi=0;hi<hidden.length;hi++) hidden[hi].remove();
                    cigarName=clone.textContent.trim();
                }
            }
            var quantity=null;
            var qm=cigarName.match(/\((\d+)\)/);
            if(qm){quantity=parseInt(qm[1]);cigarName=cigarName.replace(/\s*\(\d+\)\s*/,'').trim();}
            cigarName=cigarName.replace(/\s+/g,' ').trim();
            
            var fEl=dh.querySelector('.cigarDetailsFactoryName a');
            var vitola=fEl?fEl.textContent.trim():'';
            
            var ring=null;
            var rl=dh.querySelector('a[href*="ringlow"]');
            if(rl) ring=parseFloat(rl.textContent.trim());
            else{
                var sd=dh.querySelector('.cigarDetailsSize');
                if(sd){
                    var vs=sd.querySelectorAll('span[itemprop="value"]');
                    if(vs.length>0) ring=parseFloat(vs[0].textContent.trim());
                }
            }
            
            var length=null;
            var ll=dh.querySelector('a[href*="lengthmm"]');
            if(ll) length=parseFloat(ll.textContent.trim());
            
            var cn=dh.querySelector('a[href*="commonnames"]');
            var commonName=cn?cn.textContent.trim():'';
            
            subCigars.push({name:cigarName,vitola:vitola,ring_gauge:ring,length_mm:length,common_name:commonName,quantity:quantity});
        }
        
        var ft=row.textContent;
        var pm=ft.match(/Packaging:\s*([\s\S]*?)(?=Status:|Construction:|Bands:|Ring|$)/i);
        var packagingRaw=pm?pm[1].replace(/\s+/g,' ').trim().substring(0,500):'';
        var sm=ft.match(/Status:\s*([^\n]+)/);
        var statusText=sm?sm[1].trim():'';
        
        var bsSet={},re=/(?:box|pack|jar|humidor)\s+(?:of\s+)?(\d+)/gi,m;
        while((m=re.exec(packagingRaw))!==null){var s=parseInt(m[1]);if(s<=100)bsSet[s]=true;}
        var boxSizes=Object.keys(bsSet).map(Number).sort(function(a,b){return a-b;});
        
        var cleanReleaseName=releaseName,cleanReleaseType=releaseType;
        if(isSpecial&&releaseName){
            var keywords=['Edición Limitada','Edición Regional','Edicion Limitada','Edicion Regional',
                'La Casa del Habano','Reserva del Milenio','Reserva Cosecha',
                'Gran Reserva','Colección Habanos','Coleccion Habanos',
                'Travel Humidor','Diplomatic Gifts','VIP Gifts',
                'LCDH Humidor','Aniversario Humidor','Aniversario Jar','Tributo',
                'Habanos Añejados','Serie A Humidor',
                'Especialista en Habanos','LCDH Exclusive',
                'Año Chino','520 Aniversario','Humidor Cohiba',
                'Grand Churchills','Salomones Espanola','S. T. Dupont',
                'Jarra','Siglo de Oro','Limited Edition','Regional Edition',
                'Special Events','Special Release','Commemorative Release',
                'Millennium Reserve','Grand Reserve','Reserve Series',
                'Habanos Collection','Chinese Year','Duty Free','Habanos Specialist',
                'Selección','Réplica de Humidor','Replica de Humidor'];
            for(var k=0;k<keywords.length;k++){
                var kw=keywords[k];
                var idx=releaseName.toLowerCase().indexOf(kw.toLowerCase());
                // Split when a letter or digit glues to the keyword start (no space between)
                // "PirámidesEdición" (sE) → split, "Behike40 Aniversario" (0A) → split, "125 Aniversario" (space) → keep
                if(idx>0&&/[A-Za-z0-9]/.test(releaseName[idx-1])){
                    cleanReleaseName=releaseName.substring(0,idx).trim();
                    if(!cleanReleaseType||cleanReleaseType.length<3) cleanReleaseType=releaseName.substring(idx).trim();
                    break;
                }
            }
        }
        
        for(var j=0;j<subCigars.length;j++){
            var sc=subCigars[j];
            results.push({
                brand:brandName,name:sc.name||(isSpecial?cleanReleaseName:''),
                common_name:sc.common_name,vitola:sc.vitola,
                ring_gauge:sc.ring_gauge,length_mm:sc.length_mm,
                status:isSpecial?'Special Releases':currentSection,
                release_type:isSpecial?cleanReleaseType:'',
                release_name:isSpecial?cleanReleaseName:'',
                url:releaseUrl?BASE+releaseUrl:'',
                packaging_raw:packagingRaw,box_sizes:boxSizes,
                sub_quantity:sc.quantity,status_text:statusText,
                sub_index: j, sub_total: subCigars.length
            });
        }
    }
    return JSON.stringify({brand:brandName,total:results.length,
        with_both:results.filter(function(r){return r.ring_gauge!==null&&r.length_mm!==null;}).length,
        missing_both:results.filter(function(r){return r.ring_gauge===null||r.length_mm===null;}).length,
        results:results});
})()
"""

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

async def extract_brand(ws, slug, name):
    # Use json.dumps to safely escape brand names with quotes (e.g. Quai d'Orsay)
    safe_name = json.dumps(name)
    extract_js = EXTRACT_JS_TEMPLATE.replace('"__BRAND_NAME__"', safe_name)
    await cdp_call(ws, "Page.navigate", {"url": f"{BASE}/brand/{slug}"})
    await asyncio.sleep(2.5)
    
    resp = await cdp_call(ws, "Runtime.evaluate", {
        "expression": extract_js, "returnByValue": True
    })
    
    raw = resp.get("result", {}).get("result", {}).get("value", "{}")
    data = json.loads(raw)
    
    filepath = os.path.join(OUT, f"{slug}.json")
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return data.get("total", 0), data.get("missing_both", 0)

async def main():
    cdp_url = get_page_cdp()
    if not cdp_url:
        print("ERROR: No CDP page found! Is Chrome running with --remote-debugging-port=9222?")
        return
    
    os.makedirs(OUT, exist_ok=True)
    
    async with websockets.connect(cdp_url, max_size=50*1024*1024) as ws:
        grand_total = 0
        grand_missing = 0
        
        for slug, name in BRANDS:
            print(f"{name:25s} ...", end=" ", flush=True)
            try:
                total, missing = await extract_brand(ws, slug, name)
                status = "✓" if missing == 0 else f"✗ {missing} missing"
                print(f"{total:3d} cigars  {status}")
                grand_total += total
                grand_missing += missing
            except Exception as e:
                print(f"ERROR: {e}")
        
        print(f"\n{'='*50}")
        print(f"Total: {grand_total} cigars across {len(BRANDS)} brands")
        print(f"Missing dimensions: {grand_missing}")
        print(f"Output: {OUT}/")

asyncio.run(main())
