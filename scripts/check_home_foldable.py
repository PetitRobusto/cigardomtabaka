"""Browser regression for the homepage across folding/resizing and opaque overlap.

Run against a local storefront with its media and age confirmation available:
  .venv/bin/python scripts/check_home_foldable.py --base-url http://127.0.0.1:5191 \
      --browser /path/to/chrome --output-dir /tmp/home-foldable
Requires Playwright and Pillow. Does not modify product data or media.
"""
import argparse
import asyncio
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageChops
from playwright.async_api import async_playwright

SIZES = [(320, 832), (360, 800), (540, 720), (690, 829), (768, 900),
         (853, 720), (900, 768), (1024, 768), (1440, 1000), (360, 800)]
MEASURE = """() => {
  const rect = e => { const r=e.getBoundingClientRect();
    return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}; };
  return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,
    hero:rect(document.querySelector('.store-home-hero')),
    copy:rect(document.querySelector('.store-home-hero__copy')),
    legend:rect(document.querySelector('.store-home-hero__legend')),
    images:[...document.querySelectorAll('.store-home-hero__cigar img')].map(e=>({
      ...rect(e),loaded:e.complete&&e.naturalWidth>0
    }))};
}"""


def check_layout(state):
    assert state['documentWidth'] <= state['width'] + 1, 'Page scrolls horizontally'
    assert len(state['images']) == 5 and all(i['loaded'] for i in state['images']), 'Missing cigar images'
    for image in state['images']:
        assert image['left'] >= -1 and image['right'] <= state['width'] + 1, 'Cigar clipped horizontally'
        assert image['top'] >= state['hero']['top'] - 1, 'Cigar clipped above hero'
        assert image['bottom'] <= state['legend']['top'] + 1, 'Cigar overlaps legend'
        copy = state['copy']
        overlaps = (image['left'] < copy['right'] and image['right'] > copy['left']
                    and image['top'] < copy['bottom'] and image['bottom'] > copy['top'])
        assert not overlaps, 'Cigar overlaps copy/actions'


async def check_opacity(page, output):
    # Force real overlap. Foreground pixels must be identical with/without rear cigars.
    override = await page.add_style_tag(content="""
      .store-home-hero__cigar {top:20%!important;left:0!important;width:100%!important;
        rotate:0deg!important;translate:none!important;scale:1!important;transition:none!important}
      .store-home-hero__cigar img {animation:none!important;rotate:0deg!important;translate:none!important}
      .store-home-hero__cigar::after {display:none!important}
    """)
    first = page.locator('.store-home-hero__cigar img').first
    layered = Image.open(BytesIO(await first.screenshot())).convert('RGB')
    hidden = await page.add_style_tag(content='.store-home-hero__cigar:not(:first-child){visibility:hidden!important}')
    alone = Image.open(BytesIO(await first.screenshot())).convert('RGB')
    width, height = alone.size
    # Interior includes both the wrapper and the light band, excluding antialiased edges.
    interior = (int(width * .15), int(height * .3), int(width * .85), int(height * .7))
    difference = ImageChops.difference(layered.crop(interior), alone.crop(interior))
    layered.save(output / 'overlap.png')
    assert difference.getbbox() is None, 'Rear cigar changes opaque foreground pixels'
    await hidden.evaluate('(e)=>e.remove()')
    # Negative control proves the pixel check detects the original multiply regression.
    multiply = await page.add_style_tag(content='.store-home-hero__cigar{mix-blend-mode:multiply!important}')
    blended = Image.open(BytesIO(await first.screenshot())).convert('RGB')
    assert ImageChops.difference(blended.crop(interior), alone.crop(interior)).getbbox(), 'Overlap negative control did not exercise blending'
    await multiply.evaluate('(e)=>e.remove()')
    await override.evaluate('(e)=>e.remove()')


async def run(args):
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            **({'executable_path': args.browser} if args.browser else {}))
        for locale in ('zh', 'ru', 'en'):
            page = await browser.new_page(viewport={'width': 768, 'height': 900}, has_touch=True)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            path = '/' if locale == 'zh' else f'/{locale}/'
            await page.goto(args.base_url.rstrip('/') + path, wait_until='domcontentloaded')
            # Native confirmation is confined to this fresh browser test context.
            gate = page.locator('.store-age-gate')
            if await gate.is_visible():
                await gate.locator('[data-age-confirm]').click()
            await page.locator('.store-home-hero__cigar img').last.wait_for()
            await page.evaluate("()=>Promise.all([...document.querySelectorAll('.store-home-hero img')].map(i=>i.decode().catch(()=>{})))")
            search = page.locator('.site-search input[type=search]')
            await search.fill('Cohiba')
            for width, height in SIZES:
                await page.set_viewport_size({'width': width, 'height': height})
                assert await search.input_value() == 'Cohiba', 'Resize lost search input'
                for menu_id in ('site-language-menu', 'site-currency-menu'):
                    trigger = page.locator(f'[aria-controls="{menu_id}"]')
                    if await trigger.count():
                        await trigger.click()
                        menu = await page.locator(f'#{menu_id}').bounding_box()
                        assert menu and menu['x'] >= 0 and menu['x'] + menu['width'] <= width + 1, 'Menu leaves viewport'
                        assert menu['y'] >= 0 and menu['y'] + menu['height'] <= height + 1, 'Menu leaves viewport vertically'
                        await trigger.press('Escape')
                for time in (0, 2000, 5000, 9000, 14000, 19000):
                    await page.evaluate('(t)=>document.getAnimations().forEach(a=>{a.pause();a.currentTime=t})', time)
                    state = await page.evaluate(MEASURE)
                    check_layout(state)
                carousel = page.locator('.store-carousel__viewport').first
                assert await carousel.count(), 'Provide a homepage with products to exercise the carousel'
                await carousel.press('End')
                handle = await carousel.element_handle()
                await page.wait_for_function('(e)=>Math.abs(e.scrollWidth-e.clientWidth-e.scrollLeft)<=1', arg=handle)
                await carousel.press('Home')
                await page.wait_for_function('(e)=>e.scrollLeft<=1', arg=handle)
                await page.evaluate('()=>window.scrollTo({top:0,behavior:"instant"})')
                carousels = await page.locator('.store-carousel__viewport').evaluate_all('es=>es.map(e=>({left:e.scrollLeft,max:e.scrollWidth-e.clientWidth}))')
                assert all(-1 <= c['left'] <= c['max'] + 1 for c in carousels), 'Carousel scroll invalid after resize'
                report.append({'locale': locale, 'width': width, 'height': height, 'hero_height': state['hero']['height']})
                if width in (360, 768, 853):
                    await page.screenshot(path=str(output / f'{locale}-{width}.png'), full_page=True)
            await page.set_viewport_size({'width': 768, 'height': 900})
            # Simulate enlarged browser text while leaving the viewport unchanged.
            enlarged = await page.add_style_tag(content='.store-home-hero__copy{font-size:125%}.store-home-hero__copy p,.store-home-hero__copy li,.store-home-hero__copy a{font-size:18px!important}.store-home-hero__title{font-size:40px!important}')
            check_layout(await page.evaluate(MEASURE))
            await enlarged.evaluate('(e)=>e.remove()')
            await page.emulate_media(reduced_motion='reduce')
            assert await page.locator('.store-home-hero__cigar img').evaluate_all("es=>es.every(e=>getComputedStyle(e).animationName==='none')")
            check_layout(await page.evaluate(MEASURE))
            if locale == 'zh':
                await check_opacity(page, output)
            assert not errors, errors
            await page.close()
        await browser.close()
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'PASS: {len(report)} locale/viewport cases, animation boundaries, enlarged text, reduced motion and opaque overlap')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--browser')
    parser.add_argument('--output-dir', default='/tmp/home-foldable')
    asyncio.run(run(parser.parse_args()))
