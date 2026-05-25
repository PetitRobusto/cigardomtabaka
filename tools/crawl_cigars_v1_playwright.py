"""v3: playwright-stealth + delays + persistent context"""
import asyncio, json, re, time
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

BASE = "https://www.cubancigarwebsite.com"
OUTPUT = Path.home() / "moscow_cigar" / "cigars_catalog.json"

CURRENT_BRANDS = [
    ("Global", ["cohiba", "h-upmann", "hoyo-de-monterrey", "montecristo", "partagas", "romeo-y-julieta"]),
    ("Portfolio", ["bolivar", "cuaba", "diplomaticos", "el-rey-del-mundo", "fonseca", "jose-l-piedra",
                   "juan-lopez", "la-flor-de-cano", "la-gloria-cubana", "por-larranaga", "punch",
                   "quai-dorsay", "quintero", "rafael-gonzalez", "ramon-allones", "saint-luis-rey",
                   "san-cristobal", "sancho-panza", "trinidad", "vegas-robaina", "vegueros"]),
    ("Misc", ["belinda", "guantanamera", "small-cigars", "troya", "edmundo-dantes"]),
]


async def main():
    all_cigars = []
    
    user_data_dir = Path.home() / ".cache" / "playwright-profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await stealth_async(page)
        
        print("Passing Cloudflare...")
        await page.goto(BASE, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)
        
        title = await page.title()
        print(f"Homepage: {title}")
        if "blocked" in title.lower() or "checking" in title.lower():
            print("BLOCKED at homepage!")
            return
        
        for category, brands in CURRENT_BRANDS:
            print(f"\n--- {category} ---")
            for slug in brands:
                brand_name = slug.replace("-", " ").title()
                url = f"{BASE}/brand/{slug}"
                
                try:
                    resp = await page.goto(url, wait_until="networkidle", timeout=30000)
                    await asyncio.sleep(2)
                    status = resp.status if resp else "?"
                except Exception as e:
                    print(f"  {brand_name}: ERROR {e}")
                    continue
                
                print(f"  {brand_name}: HTTP {status}", end="")
                
                if status == 403 or status == 429:
                    print(" -> BLOCKED, cooling down...")
                    await asyncio.sleep(30)
                    continue
                
                links = await page.evaluate(f"""
                    () => {{
                        const all = document.querySelectorAll('a');
                        const result = [];
                        const seen = new Set();
                        all.forEach(l => {{
                            const h = l.getAttribute('href');
                            const n = l.textContent.trim();
                            if (h && h.includes('/cigar/{slug}/') && n.length > 2 && !seen.has(h)) {{
                                seen.add(h);
                                result.push({{ href: h, name: n.substring(0, 80) }});
                            }}
                        }});
                        return result;
                    }}
                """)
                
                print(f", {len(links)} links", end="")
                
                if len(links) == 0:
                    body = await page.evaluate("() => document.body.textContent.substring(0, 150)")
                    print(f" (body: {body[:100]})")
                    continue
                
                brand_cigars = []
                for cl in links:
                    await asyncio.sleep(1.5)  # Rate limit
                    try:
                        await page.goto(BASE + cl["href"], wait_until="domcontentloaded", timeout=20000)
                        await asyncio.sleep(0.5)
                        text = await page.evaluate("() => document.body.textContent")
                    except Exception as e:
                        print(f"\n    ERR {cl['name']}: {e}")
                        continue
                    
                    if "discontinued" in text.lower():
                        continue
                    
                    data = {"status": "", "factory_name": "", "ring_gauge": None, "length_mm": None}
                    
                    if "current regular production" in text.lower():
                        data["status"] = "current"
                    elif "current special" in text.lower():
                        data["status"] = "current_special"
                    elif "special release" in text.lower():
                        data["status"] = "special_release"
                    elif "limited edition" in text.lower():
                        data["status"] = "limited_edition"
                    elif "commemorative" in text.lower():
                        data["status"] = "commemorative"
                    else:
                        data["status"] = "other"
                    
                    m = re.search(r"Factory Name:\s*(.+?)(?:\n|$)", text)
                    if m: data["factory_name"] = m.group(1).strip()
                    
                    m = re.search(r"rg\s*(\d+)", text, re.IGNORECASE)
                    if m: data["ring_gauge"] = int(m.group(1))
                    
                    m = re.search(r"Length\s+MMT\s*(\d+)\s*mm", text, re.IGNORECASE)
                    if m: data["length_mm"] = int(m.group(1))
                    
                    brand_cigars.append({
                        "brand": brand_name,
                        "name": cl["name"],
                        "vitola": data["factory_name"],
                        "ring_gauge": data["ring_gauge"],
                        "length_mm": data["length_mm"],
                        "status": data["status"],
                        "category": category,
                    })
                    
                    # Save incrementally
                    with open(OUTPUT, "w") as f:
                        json.dump(all_cigars + brand_cigars, f, indent=2, ensure_ascii=False)
                
                all_cigars.extend(brand_cigars)
                print(f", {len(brand_cigars)} kept")
        
        await context.close()
    
    with open(OUTPUT, "w") as f:
        json.dump(all_cigars, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone! {len(all_cigars)} cigars saved")
    brands = {}
    for c in all_cigars:
        brands[c["brand"]] = brands.get(c["brand"], 0) + 1
    for b, n in sorted(brands.items()):
        print(f"  {b}: {n}")


asyncio.run(main())
