"""从 JSON 导入 COH 爬取的价格数据"""
import json
import re
from django.core.management.base import BaseCommand
from django.utils import timezone
from price_tracker.models import PriceSource, PriceSnapshot
from price_tracker.scraper import match_cigar_by_name
from price_tracker.pricing import convert_to_cny
from cigars.models import Cigar


class Command(BaseCommand):
    help = '从 JSON 文件导入 COH 价格数据到 PriceSnapshot'

    def add_arguments(self, parser):
        parser.add_argument('json_file', help='JSON 文件路径，格式: {brand: [{brand, product, price, boxInfo}]}')
        parser.add_argument('--dry-run', action='store_true', help='只匹配不写入')

    def handle(self, *args, **options):
        source = PriceSource.objects.filter(slug='coh', active=True).first()
        if not source:
            self.stderr.write('❌ COH 来源未找到，请先运行 seed_price_sources')
            return

        with open(options['json_file']) as f:
            data = json.load(f)

        dry_run = options.get('dry_run', False)
        total_matched = 0
        total_created = 0
        total_skipped = 0

        for brand_key, products in data.items():
            self.stdout.write(f'\n📦 {brand_key}: {len(products)} 款')
            for item in products:
                brand = item['brand']
                product = item['product']
                full_name = f'{brand} {product}'
                price = item['price']

                # 名字匹配
                cigar = match_cigar_by_name(full_name, source_name='COH', brand_hint=brand)
                if not cigar:
                    # 尝试只用 product 名字匹配
                    cigar = match_cigar_by_name(product, source_name='COH', brand_hint=brand)

                if not cigar:
                    total_skipped += 1
                    self.stdout.write(f'  ⚠️  未匹配: {full_name}')
                    continue

                total_matched += 1

                if dry_run:
                    self.stdout.write(f'  ✅ {cigar.brand} {cigar.english_name}: ${price}')
                    continue

                price_cny = convert_to_cny(price, 'USD')

                # Upsert today's price
                today = timezone.now().date()
                existing = PriceSnapshot.objects.filter(
                    source=source, cigar=cigar, scraped_at__date=today
                ).first()

                if existing:
                    existing.price = price
                    existing.price_cny = price_cny
                    existing.save()
                else:
                    PriceSnapshot.objects.create(
                        source=source,
                        cigar=cigar,
                        price=price,
                        currency='USD',
                        price_cny=price_cny,
                        in_stock=True,
                        raw_data={'brand': brand, 'product': product, 'box_info': item.get('boxInfo', '')},
                    )
                    total_created += 1

                self.stdout.write(f'  ✅ {cigar.brand} {cigar.english_name}: ${price} (¥{price_cny})')

        # 更新最后抓取时间
        if not dry_run:
            source.last_scraped = timezone.now()
            source.save(update_fields=['last_scraped'])

        self.stdout.write(self.style.SUCCESS(
            f'\n📊 导入完成！匹配: {total_matched}, 新增: {total_created}, 跳过: {total_skipped}'
        ))
