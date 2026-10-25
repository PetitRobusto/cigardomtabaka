"""Read-only release gate for the complete current storefront generation."""
from django.core.management.base import BaseCommand, CommandError

from storefront.catalog import build_pages
from storefront.models import RefreshState, StorePage
from storefront.publishing import build_assets, generation_hash, renderer_digest


class Command(BaseCommand):
    help = '只读验收全部当前商城缓存；缺失、错误或构建代次不符时停止发布。'

    def handle(self, *args, **options):
        state = RefreshState.objects.filter(pk=1).values('revision', 'processed_revision').first()
        if not state or state['revision'] != state['processed_revision']:
            raise CommandError('商城内容仍待校验，不能通过缓存验收。')
        pages = build_pages()
        if not pages:
            raise CommandError('商城页面集合为空，不能通过缓存验收。')
        assets, build_id = build_assets(), renderer_digest()
        rows = {row['path']: row for row in StorePage.objects.filter(active=True, error='')
                .exclude(html='').values('path', 'desired_hash', 'rendered_hash', 'rendered_payload')}
        pending = []
        for path, payload in pages.items():
            row = rows.get(path)
            expected = generation_hash(payload, assets, build_id)
            if (not row or row['desired_hash'] != expected or row['rendered_hash'] != expected
                    or not row['rendered_payload']
                    or generation_hash(row['rendered_payload'], assets, build_id) != expected):
                pending.append(path)
        if pending:
            raise CommandError(f'缓存验收未通过：{len(pending)} 页待更新，样例 {pending[:10]}')
        if (state != RefreshState.objects.filter(pk=1).values('revision', 'processed_revision').first()
                or build_id != renderer_digest() or assets != build_assets()):
            raise CommandError('验收期间内容或构建已变化，请重新渲染并验收。')
        self.stdout.write(f'缓存验收通过：{len(pages)} 页与当前构建一致。')
