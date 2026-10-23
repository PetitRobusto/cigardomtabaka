import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from storefront.models import RefreshState, StorePage
from storefront.publishing import build_assets, publish_pending, reconcile


class Command(BaseCommand):
    help = '预渲染公开商城；--watch 持续消费事务后刷新任务并每小时校验。'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true')

    def handle(self, *args, **options):
        first = True
        while True:
            close_old_connections()
            try:
                state, _ = RefreshState.objects.get_or_create(pk=1)
                due = not state.reconciled_at or state.reconciled_at < timezone.now() - timedelta(hours=1)
                assets = build_assets()
                if first or due or state.revision != state.processed_revision:
                    reconcile(assets=assets)
                count = publish_pending(assets=assets)
                if count:
                    self.stdout.write(f'已更新 {count} 个公开页面')
                first = False
                if not options['watch']:
                    failed = StorePage.objects.filter(active=True).exclude(error='').count()
                    if failed:
                        raise CommandError(f'{failed} 个页面生成失败，详见商城页面后台')
                    return
            except (KeyboardInterrupt, SystemExit):
                return
            except Exception as exc:
                if not options['watch']:
                    raise CommandError(str(exc)) from exc
                self.stderr.write(f'商城刷新失败，将重试：{exc}')
            time.sleep(5)
