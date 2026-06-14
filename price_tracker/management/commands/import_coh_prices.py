"""Import COH JSON price data through the unified ingestion module."""
import json

from django.core.management.base import BaseCommand

from price_tracker.coh_import import iter_coh_items
from price_tracker.ingestion import ingest_items
from price_tracker.models import PriceSource


class Command(BaseCommand):
    help = '从 JSON 文件导入 COH 价格数据到 PriceSnapshot'

    def add_arguments(self, parser):
        parser.add_argument('json_file', help='JSON 文件路径，格式: {brand: [{brand, product, price, boxInfo}]}')
        parser.add_argument('--dry-run', action='store_true', help='只解析和匹配，不写入')

    def handle(self, *args, **options):
        source = PriceSource.objects.filter(slug='coh', active=True).first()
        if not source:
            self.stderr.write('COH 来源未找到，请先运行 seed_price_sources')
            return

        with open(options['json_file'], encoding='utf-8') as f:
            data = json.load(f)

        items, stats = iter_coh_items(data)

        if options.get('dry_run'):
            self.stdout.write(f"解析: {stats['total']}, 无价格跳过: {stats['skipped_no_price']}, 待导入: {len(items)}")
            for item in items[:20]:
                self.stdout.write(
                    f"  {item.raw_data.get('brand', '')}: {item.name} "
                    f"${item.price} box={item.box_size or '-'}"
                )
            return

        result = ingest_items(source, items, mode='import', run_delisting=False)
        skipped = stats['skipped_no_price'] + result.skipped

        self.stdout.write(self.style.SUCCESS(
            f"导入完成！总计: {stats['total']}, 匹配: {result.matched}, "
            f"新增: {result.created}, 跳过: {skipped}, 未匹配: {len(result.unmatched)}"
        ))
        if result.unmatched:
            self.stdout.write('未匹配示例:')
            for name in result.unmatched[:20]:
                self.stdout.write(f'  - {name}')
