"""使用 Playwright Python + stealth 批量爬取中文雪茄名"""
import asyncio
import json
import os, re, sys

from playwright.async_api import async_playwright

# Prevent auto-import noise
import warnings
warnings.filterwarnings('ignore')

BRANDS = {
    'bolivar': 'Bolívar', 'cohiba': 'Cohiba', 'cuaba': 'Cuaba',
    'diplomaticos': 'Diplomáticos', 'el-rey-del-mundo': 'El Rey del Mundo',
    'fonseca': 'Fonseca', 'h-upmann': 'H. Upmann',
    'hoyo-de-monterrey': 'Hoyo de Monterrey', 'jose-l-piedra': 'José L. Piedra',
    'juan-lopez': 'Juan López', 'la-flor-de-cano': 'La Flor de Cano',
    'la-gloria-cubana': 'La Gloria Cubana', 'montecristo': 'Montecristo',
    'partagas': 'Partagás', 'por-larranaga': 'Por Larrañaga',
    'punch': 'Punch', 'quai-dorsay': 'Quai d\'Orsay',
    'quintero': 'Quintero', 'rafael-gonzalez': 'Rafael González',
    'ramon-allones': 'Ramón Allones', 'romeo-y-julieta': 'Romeo y Julieta',
    'saint-luis-rey': 'Saint Luis Rey', 'san-cristobal': 'San Cristóbal',
    'sancho-panza': 'Sancho Panza', 'trinidad': 'Trinidad',
    'vegas-robaina': 'Vegas Robaina', 'vegueros': 'Vegueros',
}


def extract_chinese_name(text, brand_slug, brand_en_name):
    """从文本提取中文名"""
    text = text.strip()
    
    # 1. Remove brand prefix patterns
    brand_cn_map = {
        'bolivar': '玻利瓦', 'cohiba': '高希霸', 'cuaba': '库阿巴',
        'diplomaticos': '外交官', 'el-rey-del-mundo': '世界之王',
        'fonseca': '科塞卡', 'h-upmann': '乌普曼',
        'hoyo-de-monterrey': '好友', 'jose-l-piedra': '荷西比雅达',
        'juan-lopez': '胡安佩洛斯', 'la-flor-de-cano': '卡诺之花',
        'la-gloria-cubana': '古巴荣耀', 'montecristo': '蒙特',
        'partagas': '帕特加斯', 'por-larranaga': '波尔拉腊尼加',
        'punch': '潘趣', 'quai-dorsay': '多赛尔',
        'quintero': '金特罗', 'rafael-gonzalez': '拉斐尔冈萨雷斯',
        'ramon-allones': '拉蒙阿龙', 'romeo-y-julieta': '罗密欧与朱丽叶',
        'saint-luis-rey': '圣路易斯雷', 'san-cristobal': '圣克里斯托',
        'sancho-panza': '桑乔潘萨', 'trinidad': '特立尼达',
        'vegas-robaina': '维加斯罗瓦伊纳', 'vegueros': '威古洛',
    }
    brand_cn = brand_cn_map.get(brand_slug, '')
    brand_en = BRANDS.get(brand_slug, '')
    
    # Remove brand prefix
    for prefix in [brand_cn, brand_en, brand_en.replace(' ', r'\s+')]:
        if prefix:
            pattern = r'^' + re.escape(prefix)
            text = re.sub(pattern, '', text).strip()
            pattern = r'^' + re.escape(prefix.replace(' ', r'\s+'))
            text = re.sub(pattern, '', text).strip()
    
    if not text:
        return text
    
    # 2. Split into tokens, find where English starts
    tokens = text.split()
    cn_parts = []
    for tok in tokens:
        # Remove parenthetical numbers
        clean = re.sub(r'\(\d+\)', '', tok).strip()
        if not clean:
            cn_parts.append(tok)  # keep tokens that are just numbers
            continue
        # Check if token is English/alpha
        is_english = False
        if re.match(r'^[A-Z][a-zéíñ]+$', clean):
            is_english = True
        elif re.match(r'^[A-Z0-9][A-Za-z0-9éíñ]+$', clean):
            is_english = True
        elif clean.isdigit():
            is_english = True
        elif clean.upper() in ('BHK', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'A', 'B', 'C', 'D', 'E', 'P'):
            is_english = True
        if is_english:
            break
        cn_parts.append(tok)
    
    result = ' '.join(cn_parts).strip()
    # Clean up
    result = re.sub(r'\s*\(\d+\)\s*$', '', result).strip()
    return result if result else text


async def main():
    output_file = os.path.expanduser('~/moscow_cigar/cigar_cn_full.json')
    
    async with async_playwright() as p:
        # Use stealth + headless
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        page = await ctx.new_page()
        
        # Inject stealth
        await page.add_init_script('''
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN','zh','en'] });
        ''')
        
        all_data = {}
        total = 0
        
        for slug, en_name in BRANDS.items():
            url = f'https://www.cubancigarwebsite.com/zh-cn/brand/{slug}'
            try:
                resp = await page.goto(url, timeout=30000, wait_until='domcontentloaded')
                if resp and resp.status != 200:
                    print(f'  ⚠️ {slug}: HTTP {resp.status}', flush=True)
                    continue
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f'  ⚠️ {slug}: {e}', flush=True)
                continue
            
            entries = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('.cigarDetailsHead'))
                    .map(h => {
                        const a = h.querySelector('.cigarDetailsName a[name]');
                        const t = h.querySelector('.cigarDetailsName');
                        if (!a || !t) return null;
                        return [a.getAttribute('name'), t.textContent.trim().replace(/\\s+/g, ' ')];
                    }).filter(Boolean);
            }''')
            
            if entries:
                brand_results = []
                for slug_entry, text in entries:
                    cn_name = extract_chinese_name(text, slug, en_name)
                    if cn_name:
                        brand_results.append([slug_entry, cn_name])
                all_data[slug] = brand_results
                total += len(brand_results)
                print(f'  ✅ {slug}: {len(brand_results)} names', flush=True)
            else:
                print(f'  ❌ {slug}: 0 entries (page may be blocked)', flush=True)
        
        await browser.close()
    
    # Save
    with open(output_file, 'w') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    print(f'\n💾 Saved {total} entries to {output_file}', flush=True)
    return output_file


def update_db_from_json(json_path):
    """同步更新数据库（不能在async里调Django ORM）"""
    sys.path.insert(0, os.path.expanduser('~/moscow_cigar'))
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'moscow_cigar_backend.settings')
    django.setup()
    from cigars.models import Cigar
    import json
    
    with open(json_path) as f:
        all_data = json.load(f)
    
    updated = 0
    matched = 0
    for brand_slug, entries in all_data.items():
        en_brand = BRANDS[brand_slug]
        for slug_entry, cn_name in entries:
            eng_name = slug_entry.replace('-', ' ').title()
            eng_name = eng_name.replace('Bhk', 'BHK').replace('No ', 'No.')
            n = Cigar.objects.filter(
                brand=en_brand,
                english_name__iexact=eng_name
            ).update(name=cn_name)
            if n == 0:
                n = Cigar.objects.filter(
                    brand=en_brand,
                    english_name__icontains=eng_name
                ).update(name=cn_name)
            updated += n
            if n > 0:
                matched += 1
    
    empty = Cigar.objects.filter(name='').count()
    total = Cigar.objects.count()
    print(f'✅ DB updated: {updated} rows ({matched} entries)', flush=True)
    print(f'📊 Has Chinese: {total - empty} / {total} ({(total-empty)*100//total}%)', flush=True)


if __name__ == '__main__':
    result_file = asyncio.run(main())
    if result_file and os.path.exists(result_file):
        print('\n📝 Now updating database...', flush=True)
        # Re-import Django in sync context
        os.environ.pop('DJANGO_SETTINGS_MODULE', None)  # reset
        update_db_from_json(result_file)
