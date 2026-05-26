"""每日价格抓取命令"""
import asyncio
import logging

from django.core.management.base import BaseCommand
from price_tracker.models import PriceSource
from price_tracker.scraper import run_scrape_sync

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '抓取所有活跃来源的雪茄价格'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source', '-s',
            help='指定来源 slug（不指定则全部）',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只列出会抓取的来源，不实际执行',
        )

    def handle(self, *args, **options):
        source_slug = options.get('source')
        dry_run = options.get('dry_run', False)

        # ⚠️ 在 async 外预取 queryset，避免 SynchronousOnlyOperation
        if source_slug:
            sources = list(PriceSource.objects.filter(slug=source_slug, active=True))
            if not sources:
                self.stderr.write(f'❌ 来源 "{source_slug}" 不存在或未启用')
                return
        else:
            sources = list(PriceSource.objects.filter(active=True))
            if not sources:
                self.stderr.write('❌ 没有活跃的价格来源，请先运行 seed_price_sources')
                return

        if dry_run:
            self.stdout.write('🔍 将抓取以下来源：')
            for s in sources:
                self.stdout.write(f'  · {s.name} ({s.slug}) — {s.base_url}')
            return

        # 串行同步抓取（避免 async/SQLite 打架）
        total_items = 0
        total_matched = 0
        total_created = 0
        total_skipped = 0
        errors = []

        for source in sources:
            self.stdout.write(f'🔄 正在抓取 {source.name}...')
            result = run_scrape_sync(source.slug)
            if 'error' in result:
                errors.append(result)
                self.stderr.write(f'  ⚠️  {source.name}: {result["error"]}')
            else:
                total_items += result.get('total_items', 0)
                total_matched += result.get('matched', 0)
                total_created += result.get('created', 0)
                total_skipped += result.get('skipped', 0)
                self.stdout.write(
                    f'  ✅ {source.name}: {result["matched"]}/{result["total_items"]} '
                    f'匹配，{result["created"]} 新增'
                )

        self.stdout.write(self.style.SUCCESS(
            f'\n📊 抓取完成！'
            f' 共 {len([s for s in sources])} 个来源，{total_items} 款雪茄'
            f'\n  ✅ 匹配: {total_matched}'
            f'\n  🆕 新增: {total_created}'
            f'\n  ⏭️  跳過: {total_skipped}'
            + (f'\n  ❌ 錯誤: {len(errors)}' if errors else '')
        ))

        for err in errors:
            self.stderr.write(f'  ⚠️  {err.get("source", "?")}: {err["error"]}')
