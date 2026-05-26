#!/usr/bin/env python3
"""
TimeCigar 小雪茄批量爬虫 — 爬取非Cohiba品牌的详情页规格
用法: python3 scrape_timecigar_details.py
输出: timecigar_minis_full.json
"""
import json, time, sys, os
from playwright.sync_api import sync_playwright

PRODUCT_LIST_FILE = '/home/jason/moscow_cigar/timecigar_minis_products.json'
OUTPUT_FILE = '/home/jason/moscow_cigar/timecigar_minis_full.json'

def extract_specs(page, product_id):
    """爬取单个产品的详情页规格"""
    url = f'https://www.timecigar.com/lb_ps_quick_add?id={product_id}&form_page_type=open&form_session=view'
    
    try:
        page.goto(url, timeout=15000)
        page.wait_for_timeout(800)
        
        result = page.evaluate('''() => {
            const r = {};
            const allText = document.body.innerText;
            
            // Find spec by label text
            const findBefore = (label) => {
                const els = [...document.querySelectorAll('[ref]')];
                for (let i = 0; i < els.length; i++) {
                    if (els[i].textContent.trim() === label && i > 0) {
                        return els[i-1].textContent.trim();
                    }
                }
                return '';
            };
            
            r.vitola = findBefore('品型');
            r.length_raw = findBefore('長度');
            r.ring_gauge = findBefore('環徑');
            
            // strength is after label
            const els = [...document.querySelectorAll('[ref]')];
            for (let i = 0; i < els.length; i++) {
                if (els[i].textContent.trim() === '濃度' && i+1 < els.length) {
                    r.strength = els[i+1].textContent.trim();
                    break;
                }
            }
            
            // Price extraction - look for price pattern
            const priceMatch = allText.match(/(\\d+\\.?\\d*)\\s*\\n\\s*(\\d+\\.?\\d*)\\s*\\n/);
            
            // Pack size from text
            const packMatch = allText.match(/(\\d+)\\s*支/);
            r.pack_size = packMatch ? packMatch[1] : '';
            
            return r;
        }''')
        
        return result
    except Exception as e:
        return {'error': str(e)}

def main():
    # Load product list
    with open(PRODUCT_LIST_FILE) as f:
        products = json.load(f)
    
    print(f"Loaded {len(products)} products")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # First navigate and accept age
        page.goto('https://www.timecigar.com/tc/cuban_mini_cigars', timeout=30000)
        page.wait_for_timeout(2000)
        try:
            page.evaluate('() => { if (typeof accept_agreement === "function") accept_agreement(); }')
            page.evaluate('() => { document.querySelectorAll("[id*=popup], [class*=popup]").forEach(el => el.style.display="none"); }')
        except:
            pass
        
        enriched = []
        total = len(products)
        
        for i, p in enumerate(products):
            pid = p['product_id']
            print(f"[{i+1}/{total}] {p['brand_name']} - {p['name'][:40]}...", end=' ')
            
            specs = extract_specs(page, pid)
            
            # Parse specs
            length_mm = None
            ring_gauge = None
            if specs.get('length_raw'):
                try:
                    length_mm = float(specs['length_raw'].replace('mm', '').strip())
                except:
                    pass
            if specs.get('ring_gauge'):
                try:
                    ring_gauge = int(specs['ring_gauge'].strip())
                except:
                    pass
            if specs.get('ring_gauge') is None and p.get('ring_gauge'):
                ring_gauge = p['ring_gauge']
            
            p['vitola'] = specs.get('vitola', '')
            p['length_mm'] = length_mm
            p['ring_gauge'] = ring_gauge
            p['strength'] = specs.get('strength', '')
            
            # Parse Chinese name from product name
            name_parts = p['name'].split('  ')
            if len(name_parts) >= 2:
                p['english_name_short'] = name_parts[0].split()[-1] if name_parts[0].split() else ''
                p['chinese_name'] = name_parts[1].strip()
            else:
                p['chinese_name'] = p['name']
                p['english_name_short'] = ''
            
            enriched.append(p)
            print(f"→ {length_mm}mm×{ring_gauge}RG")
            
            # Rate limit
            time.sleep(0.5)
        
        browser.close()
    
    # Save
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    
    print(f"\nDone! Saved {len(enriched)} products to {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
