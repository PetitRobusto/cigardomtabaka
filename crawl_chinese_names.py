"""使用 Playwright Python 直接爬取所有品牌中文名，无需手动操作浏览器"""
import asyncio
import json
import os
import re
import sys

# Django setup
sys.path.insert(0, os.path.expanduser('~/cigardomtabaka'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cigardomtabaka_backend.settings')
import django
django.setup()

from cigars.models import Cigar
from playwright.async_api import async_playwright


BRANDS = {
    'bolivar': '玻利瓦尔',
    'cohiba': '高希霸',
    'cuaba': '库阿巴',
    'diplomaticos': '外交官',
    'el-rey-del-mundo': '世界之王',
    'fonseca': '丰塞卡',
    'h-upmann': '乌普曼',
    'hoyo-de-monterrey': '好友蒙特雷',
    'jose-l-piedra': '比德罗',
    'juan-lopez': '胡安洛佩斯',
    'la-flor-de-cano': '拉弗洛尔德卡诺',
    'la-gloria-cubana': '古巴荣耀',
    'montecristo': '蒙特',
    'partagas': '帕特加斯',
    'por-larranaga': '波尔拉腊尼加',
    'punch': '潘趣',
    'quai-dorsay': '多赛尔',
    'quintero': '金特罗',
    'rafael-gonzalez': '拉斐尔冈萨雷斯',
    'ramon-allones': '拉蒙阿龙',
    'romeo-y-julieta': '罗密欧与朱丽叶',
    'saint-luis-rey': '圣路易斯雷',
    'san-cristobal': '圣克里斯托',
    'sancho-panza': '桑乔潘萨',
    'trinidad': '特立尼达',
    'vegas-robaina': '维加斯罗瓦伊纳',
    'vegueros': '维格罗',
}


def extract_chinese_name(raw_text, brand_slug):
    """从中文页面提取中文雪茄名"""
    text = raw_text.strip()
    brand_cn = BRANDS.get(brand_slug, '')
    brand_en = brand_slug.replace('-', ' ').title()
    
    # 去掉品牌前缀
    if brand_cn:
        text = re.sub(r'^' + re.escape(brand_cn) + r'(?:\s+' + re.escape(brand_en.replace(' ', r'\s+')) + r')?\s*', '', text)
    text = re.sub(r'^' + re.escape(brand_en.replace(' ', r'\s+')) + r'\s*', '', text)
    
    # 寻找中文部分：从开头到第一个英文词之前
    tokens = text.split()
    cn_tokens = []
    for tok in tokens:
        tok_clean = re.sub(r'\(\d+\)', '', tok).strip()
        if not tok_clean:
            continue
        # 判断是否是英文词
        is_eng = bool(re.match(r'^[A-Z][a-zéí]+$', tok_clean)) or \
                 bool(re.match(r'^[A-Z0-9][A-Za-z0-9éí.]+$', tok_clean)) or \
                 tok_clean.isdigit() or \
                 tok_clean.upper() in ('BHK', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'A')
        if is_eng:
            break
        cn_tokens.append(tok)
    
    result = ' '.join(cn_tokens).strip()
    result = re.sub(r'\s*\(\d+\)\s*$', '', result).strip()
    return result if result else text


async def crawl_brand(page, brand_slug):
    """爬取单个品牌页面的中文名"""
    url = f'https://www.cubancigarwebsite.com/zh-cn/brand/{brand_slug}'
    print(f'  🌐 {brand_slug}', end=' ', flush=True)
    try:
        await page.goto(url, timeout=30000, wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f'    ⚠️ 导航失败: {e}')
        return []
    
    data = await page.evaluate('''() => {
        const heads = document.querySelectorAll('.cigarDetailsHead');
        return Array.from(heads).map(h => {
            const nameEl = h.querySelector('.cigarDetailsName');
            const a = nameEl ? nameEl.querySelector('a[name]') : null;
            return {
                slug: a ? a.getAttribute('name') : null,
                text: nameEl ? nameEl.textContent.trim().replace(/\\s+/g, ' ') : ''
            };
        });
    }''')
    
    results = []
    for item in data:
        if not item['slug']:  # 保湿盒内的雪茄条目，跳过（通常没有独立中文名）
            continue
        cn_name = extract_chinese_name(item['text'], brand_slug)
        if cn_name and cn_name != item['text']:
            english_name = item['slug'].replace('-', ' ').title().replace('Bhk', 'BHK')
            results.append({
                'brand': brand_slug,
                'slug': item['slug'],
                'english_name': english_name,
                'chinese_name': cn_name,
            })
    
    return results


async def main():
    import sys
    sys.stdout.reconfigure(line_buffering=True)  # force line buffering
    output_file = os.path.expanduser('~/cigardomtabaka/cigar_chinese_names_full.json')
    
    # 加载已有数据
    existing = {}
    if os.path.exists(output_file):
        with open(output_file) as f:
            for item in json.load(f):
                key = (item['brand'], item['english_name'])
                existing[key] = item['chinese_name']
        print(f'📄 已加载 {len(existing)} 条已有数据\n')
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        all_results = []
        for slug, cn in BRANDS.items():
            brand_results = await crawl_brand(page, slug)
            print(f'✅ {len(brand_results)}条', flush=True)
            all_results.extend(brand_results)
        
        await browser.close()
    
    # 合并已有数据
    seen = set()
    final = []
    for item in all_results:
        key = (item['brand'], item['english_name'])
        if item['chinese_name']:
            existing[key] = item['chinese_name']
    
    for (brand, en), cn in existing.items():
        final.append({'brand': brand, 'english_name': en, 'chinese_name': cn})
    
    # 保存
    with open(output_file, 'w') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    
    print(f'\n💾 保存 {len(final)} 条到 {output_file}')
    
    # 更新数据库
    updated = 0
    for item in final:
        n = Cigar.objects.filter(
            brand=item['brand'],
            english_name__iexact=item['english_name']
        ).update(name=item['chinese_name'])
        updated += n
    
    empty = Cigar.objects.filter(name='').count()
    print(f'✅ 数据库更新 {updated} 条')
    print(f'📊 仍缺中文名: {empty} / {Cigar.objects.count()}')


if __name__ == '__main__':
    asyncio.run(main())
