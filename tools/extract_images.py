#!/usr/bin/env python3
"""
Extract ALL image URLs from cubancigarwebsite.com brand pages.
Groups images by entry (release), preserving type info for correct main-image selection.
Output: image_manifest.json with all URLs mapped to cigar (brand, name, release_type) keys.
"""
import asyncio, json, os, urllib.request, sys
import websockets

BASE = "https://www.cubancigarwebsite.com"
OUT = os.path.expanduser("~/.hermes/cigar_inventory")
MANIFEST = os.path.expanduser("~/cigardomtabaka/image_manifest.json")

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

IMAGES_JS = r"""
(function() {
    var BASE='https://www.cubancigarwebsite.com';
    var brandName=__BRAND_NAME__;
    var mt=document.querySelector('.maintable');
    if(!mt) return JSON.stringify({error:'No maintable'});
    var children=Array.from(mt.children),currentSection='Current',entries=[];
    
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
        
        var isSpecial=currentSection==='Special Releases';
        var dhs=row.querySelectorAll('.cigarDetailsHead');
        if(dhs.length===0) continue;
        
        // Gather all images in this entry
        var allImages=[];
        var imgLinks=row.querySelectorAll('a[href*="/img/"]');
        for(var j=0;j<imgLinks.length;j++){
            var href=imgLinks[j].getAttribute('href');
            if(!href||href==='#') continue;
            var type='other';
            if(href.indexOf('/img/cigars/')>=0) type='cigar';
            else if(href.indexOf('/img/cigarbands/')>=0) type='band';
            else if(href.indexOf('/img/cigarpackaging/')>=0) type='packaging';
            else if(href.indexOf('/img/specialpackaging/')>=0) type='special';
            else continue;
            allImages.push({type:type,url:BASE+href,path:href});
        }
        if(allImages.length===0) continue;
        
        // Release info
        var releaseName='',releaseType='';
        if(isSpecial){
            var rn=row.querySelector('.cigarReleaseName a');
            releaseName=rn?rn.textContent.trim():'';
            var rt=row.querySelector('.srsub a');
            releaseType=rt?rt.textContent.trim():'';
            
            // Clean concatenated names
            var keywords=['Edici\u00f3n Limitada','Edici\u00f3n Regional','Edicion Limitada','Edicion Regional',
                'La Casa del Habano','Reserva del Milenio','Reserva Cosecha','Gran Reserva',
                'Colecci\u00f3n Habanos','Coleccion Habanos','Travel Humidor','Diplomatic Gifts',
                'VIP Gifts','Aniversario Humidor','Aniversario Jar','Tributo','Habanos A\u00f1ejados',
                'Serie A Humidor','Especialista en Habanos','LCDH Exclusive','A\u00f1o Chino',
                'Limited Edition','Regional Edition','Special Events','Special Release',
                'Commemorative Release','Millennium Reserve','Grand Reserve','Reserve Series',
                'Habanos Collection','Chinese Year','Duty Free','Habanos Specialist'];
            for(var k=0;k<keywords.length;k++){
                var kw=keywords[k];
                var idx=releaseName.toLowerCase().indexOf(kw.toLowerCase());
                if(idx>0&&(releaseName[idx-1]===' '||/[A-Z]/.test(releaseName[idx-1]))){
                    releaseName=releaseName.substring(0,idx).trim();
                    if(!releaseType||releaseType.length<3) releaseType=releaseName.substring(idx).trim();
                    break;
                }
            }
        }
        
        // Get sub-cigar names from details heads (strip quantities)
        var subNames=[];
        for(var j=0;j<dhs.length;j++){
            var dh=dhs[j],nameDiv=dh.querySelector('.cigarDetailsName');
            var n='';
            if(nameDiv){
                var nameA=nameDiv.querySelector('a[name]');
                if(nameA) n=nameA.textContent.trim();
                else{
                    var clone=nameDiv.cloneNode(true);
                    clone.querySelectorAll('[style*="display:none"],[itemprop="brand"]').forEach(function(el){el.remove();});
                    n=clone.textContent.trim();
                }
            }
            n=n.replace(/\\s*\\(\\d+\\)\\s*/,'').replace(/\\s+/g,' ').trim();
            subNames.push(n);
        }
        
        entries.push({
            brand:brandName,
            status:currentSection,
            release_name:isSpecial?releaseName:'',
            release_type:isSpecial?releaseType:'',
            sub_names:subNames,
            dh_count:dhs.length,
            images:allImages
        });
    }
    return JSON.stringify({brand:brandName,entries:entries});
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

async def main():
    cdp_url = get_page_cdp()
    if not cdp_url:
        print("ERROR: No CDP page!")
        return

    os.makedirs(OUT, exist_ok=True)
    all_entries = []
    
    async with websockets.connect(cdp_url, max_size=50*1024*1024) as ws:
        for slug, name in BRAND_MAP.items():
            safe_name = json.dumps(name)
            js = IMAGES_JS.replace('__BRAND_NAME__', safe_name)
            
            await cdp_call(ws, "Page.navigate", {"url": f"{BASE}/brand/{slug}"})
            await asyncio.sleep(2.5)
            
            resp = await cdp_call(ws, "Runtime.evaluate", {
                "expression": js, "returnByValue": True
            })
            
            raw = resp.get("result", {}).get("result", {}).get("value", "{}")
            data = json.loads(raw)
            entries = data.get("entries", [])
            total_imgs = sum(len(e.get("images", [])) for e in entries)
            
            print(f"{name:25s}: {len(entries):3d} entries, {total_imgs:4d} images")
            all_entries.extend(entries)

    with open(MANIFEST, 'w') as f:
        json.dump(all_entries, f, indent=2, ensure_ascii=False)

    total = sum(len(e["images"]) for e in all_entries)
    types = {}
    for e in all_entries:
        for img in e["images"]:
            types[img["type"]] = types.get(img["type"], 0) + 1
    
    print(f"\n{'='*50}")
    print(f"Total: {len(all_entries)} entries, {total} image URLs")
    for t, c in sorted(types.items()):
        print(f"  {t}: {c}")
    print(f"Manifest: {MANIFEST}")

asyncio.run(main())
