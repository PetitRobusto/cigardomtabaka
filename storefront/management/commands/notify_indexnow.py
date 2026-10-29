"""Explicit operations for the opt-in public-page change notifier."""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from storefront.indexnow import configuration, next_attempt, send_pending, sync_changes
from storefront.models import IndexNowState


class Command(BaseCommand):
    help = '查看 IndexNow 状态；--sync 建立/更新基线，--send 发送一批，--retry-failed 重置失败项。'

    def add_arguments(self, parser):
        parser.add_argument('--path', help='只读查看某个已跟踪公开路径的通知状态。')
        actions = parser.add_mutually_exclusive_group()
        actions.add_argument('--sync', action='store_true')
        actions.add_argument('--send', action='store_true')
        actions.add_argument('--retry-failed', action='store_true')

    def handle(self, *args, **options):
        if options['path'] and any(options[action] for action in ('send', 'sync', 'retry_failed')):
            raise CommandError('--path 仅用于只读状态查询，不能与写入/发送选项一起使用。')
        try:
            config = configuration()
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        if not config:
            self.stdout.write(json.dumps({'enabled': False, 'sent': 0}))
            return
        result = {}
        if options['send']:
            result = send_pending()
        elif options['sync']:
            result['synced'] = sync_changes() is not None
        state = IndexNowState.objects.filter(origin=config[0]).first()
        if state and options['retry_failed']:
            with transaction.atomic():
                IndexNowState.objects.filter(pk=state.pk).update(key_hash=F('key_hash'))
                failed = list(state.urls.exclude(desired_hash=F('notified_hash')).exclude(
                    error='',
                ).filter(retry_at__isnull=True))
                now = timezone.now()
                for row in failed:
                    state.urls.filter(pk=row.pk).update(
                        attempts=0, retry_at=next_attempt(row, now), error='',
                    )
                result['rearmed'] = len(failed)
        result.update(enabled=True, origin=config[0], initialized=bool(state and state.initialized_at))
        if state:
            pending = state.urls.exclude(desired_hash=F('notified_hash'))
            result.update(
                tracked=state.urls.count(), pending=pending.count(),
                blocked=pending.filter(retry_at__isnull=True).count(),
                key_validation_pending=state.urls.filter(last_status=202).count(),
            )
        if options['path']:
            row = state.urls.filter(path=options['path']).first() if state else None
            result['url_status'] = None if row is None else {
                'path': row.path, 'public': bool(row.desired_hash),
                'pending': row.desired_hash != row.notified_hash,
                'attempts': row.attempts, 'last_status': row.last_status,
                'last_attempt_at': row.last_attempt_at.isoformat() if row.last_attempt_at else None,
                'retry_at': row.retry_at.isoformat() if row.retry_at else None,
                'error': row.error,
            }
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
