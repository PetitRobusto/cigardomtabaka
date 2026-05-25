"""
下载品牌 LOGO 管理命令
用法: python manage.py download_brand_logos
"""
import json, os, urllib.request
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from cigars.models import Brand


LOGO_URLS_FILE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(__file__)))), 'brand_logos.json')


# 品牌名模糊匹配：cubancigarwebsite 和 DB 可能有细微差异
NAME_ALIASES = {
    'San Cristóbal de la Habana': 'San Cristóbal',
    'Saint Luis Rey':               'Saint Luis Rey',
}


class Command(BaseCommand):
    help = '从 cubancigarwebsite.com 下载品牌 LOGO 并绑定到 Brand 模型'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='只预览不下载')
        parser.add_argument('--brand', type=str, help='只处理指定品牌')

    def handle(self, **options):
        dry_run = options['dry_run']
        target_brand = options.get('brand')

        # 1. 加载 LOGO URL 清单
        if not os.path.exists(LOGO_URLS_FILE):
            self.stderr.write(f'LOGO URLs 文件不存在: {LOGO_URLS_FILE}')
            return

        with open(LOGO_URLS_FILE) as f:
            logos = json.load(f)

        # 2. 获取数据库中已有的品牌
        db_brands = set(Brand.objects.values_list('english_name', flat=True))

        # 3. 匹配 + 下载
        created = 0
        downloaded = 0
        skipped = 0

        for item in logos:
            brand_name = item['brand']
            logo_url = item['url']

            # 模糊匹配
            matched_name = self._match_brand(brand_name, db_brands)
            if not matched_name:
                # 创建新品牌（不在 DB 的也建，方便未来使用）
                matched_name = brand_name

            if target_brand and matched_name != target_brand:
                continue

            brand, is_new = Brand.objects.get_or_create(
                english_name=matched_name, defaults={'name': ''})

            if is_new:
                created += 1
                action = 'CREATED'
            else:
                action = 'EXISTS'

            # 如果已有 logo 就跳过下载
            if brand.logo and not dry_run:
                self.stdout.write(f'  [{action}] {matched_name} — logo 已有，跳过')
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(f'  [DRY-RUN] {matched_name} ← {logo_url}')
                continue

            # 下载
            try:
                self.stdout.write(f'  [{action}] {matched_name} — 下载中...')
                req = urllib.request.Request(logo_url, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; CigarBot/1.0)',
                    'Referer': 'https://www.cubancigarwebsite.com/brands',
                })
                with urllib.request.urlopen(req, timeout=30) as resp:
                    img_data = resp.read()

                ext = logo_url.rsplit('.', 1)[-1].split('?')[0]
                if ext not in ('jpg', 'jpeg', 'png', 'webp'):
                    ext = 'jpg'

                filename = f'{slugify(matched_name)}.{ext}'
                brand.logo.save(filename, ContentFile(img_data), save=False)
                brand.logo_url = logo_url
                brand.save()
                downloaded += 1
                self.stdout.write(f'    ✅ {len(img_data)} bytes → {filename}')

            except Exception as e:
                self.stderr.write(f'    ❌ 下载失败: {e}')

        self.stdout.write(self.style.SUCCESS(
            f'\n完成！新建 {created} 个品牌，下载 {downloaded} 个 LOGO，跳过 {skipped} 个'
        ))

    def _match_brand(self, name, db_set):
        """模糊匹配品牌名"""
        if name in db_set:
            return name
        if name in NAME_ALIASES and NAME_ALIASES[name] in db_set:
            return NAME_ALIASES[name]
        # 去掉末尾空格
        clean = name.strip()
        if clean in db_set:
            return clean
        return None
