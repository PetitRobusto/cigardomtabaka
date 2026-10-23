"""Persistent, coalescing queue with compare-and-swap publication of React HTML."""
import hashlib
import json
import subprocess
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import RefreshState, StorePage


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def renderer_digest():
    return hashlib.sha256(Path(settings.STOREFRONT_RENDERER).read_bytes()).hexdigest()


def generation_hash(payload, assets, build_id):
    return digest({'payload': payload, 'assets': assets, 'renderer': build_id, 'origin': settings.STOREFRONT_ORIGIN})


def request_refresh():
    RefreshState.objects.get_or_create(pk=1)
    RefreshState.objects.filter(pk=1).update(revision=F('revision') + 1)


def build_assets():
    root = Path(settings.STOREFRONT_RENDERER).parent.parent
    manifest = json.loads((root / '.vite' / 'manifest.json').read_text())
    entry = manifest['src/storefront/client.tsx']
    css, visited = [], set()

    def visit(chunk):
        for name in chunk.get('css', []):
            if name not in css:
                css.append(name)
        for name in chunk.get('imports', []):
            if name not in visited:
                visited.add(name)
                visit(manifest[name])
    visit(entry)
    files = [entry['file'], *css]
    if any('..' in Path(name).parts or Path(name).is_absolute() or not (root / name).is_file() for name in files):
        raise ValueError('商城构建资源不完整')
    base = settings.STATIC_URL + 'frontend/'
    return {'js': [base + entry['file']], 'css': [base + name for name in css]}


def reconcile(*, assets=None):
    from .catalog import build_pages
    state, _ = RefreshState.objects.get_or_create(pk=1)
    revision = state.revision
    pages = build_pages()
    assets = assets if assets is not None else build_assets()
    build_id = renderer_digest()
    now = timezone.now()
    with transaction.atomic():
        # Serialize writers before touching pages and reject an obsolete source
        # snapshot, including a newer reconciliation of the same revision.
        if not RefreshState.objects.filter(
            pk=1, revision=revision, processed_revision=state.processed_revision,
            reconciled_at=state.reconciled_at,
        ).update(revision=F('revision')):
            return assets
        existing = {p.path: p for p in StorePage.objects.all()}
        for path, payload in pages.items():
            wanted = generation_hash(payload, assets, build_id)
            page = existing.pop(path, None)
            if page is None:
                StorePage.objects.create(path=path, payload=payload, desired_hash=wanted, changed_at=now)
            elif page.desired_hash != wanted or not page.active:
                # A frontend deployment alone does not fake a content lastmod.
                changed_at = now if page.payload != payload else page.changed_at
                StorePage.objects.filter(pk=page.pk).update(
                    active=True, payload=payload, desired_hash=wanted, changed_at=changed_at,
                    attempts=0, retry_at=now, error='',
                )
        StorePage.objects.filter(pk__in=[p.pk for p in existing.values()]).update(
            active=False, html='', rendered_payload={}, rendered_hash='',
        )
        RefreshState.objects.filter(pk=1).update(processed_revision=revision, reconciled_at=now)
    return assets


def render_batch(pages, assets):
    result = subprocess.run(
        ['node', str(settings.STOREFRONT_RENDERER)],
        input=json.dumps({'pages': [p.payload for p in pages], 'origin': settings.STOREFRONT_ORIGIN, 'assets': assets}),
        text=True, capture_output=True, check=True, timeout=120,
    )
    rendered = json.loads(result.stdout)
    if not isinstance(rendered, list) or len(rendered) != len(pages):
        raise ValueError('预渲染输出数量不匹配')
    output = {item['path']: item['html'] for item in rendered}
    if set(output) != {p.path for p in pages}:
        raise ValueError('预渲染输出页面不匹配')
    for html in output.values():
        if not isinstance(html, str) or '<h1' not in html or 'id="store-data"' not in html or 'rel="canonical"' not in html:
            raise ValueError('预渲染缺少正文或 SEO 元素')
    return output


def publish_pending(*, assets=None, renderer=render_batch):
    """Render without DB locks; atomically publish only if the desired generation is current."""
    assets = assets if assets is not None else build_assets()
    pending = StorePage.objects.filter(active=True).exclude(desired_hash=F('rendered_hash'))
    if pending.filter(retry_at__gt=timezone.now()).exists():
        return 0
    pages = list(pending.order_by('path'))
    if not pages:
        return 0
    state = RefreshState.objects.get(pk=1)
    if state.revision != state.processed_revision:
        return 0
    revision = state.revision
    build_id = renderer_digest()
    if any(generation_hash(page.payload, assets, build_id) != page.desired_hash for page in pages):
        # A different worker/build prepared these targets. Reconcile promptly
        # instead of labelling HTML from this build as the desired generation.
        request_refresh()
        return 0
    output = {}
    try:
        for offset in range(0, len(pages), 50):
            output.update(renderer(pages[offset:offset + 50], assets))
    except Exception as exc:
        # An unpublished link target must not be exposed by publishing half a set.
        for page in pages:
            StorePage.objects.filter(
                pk=page.pk, active=True, desired_hash=page.desired_hash,
            ).exclude(rendered_hash=F('desired_hash')).update(
                attempts=F('attempts') + 1, error=str(exc)[:2000],
                retry_at=timezone.now() + timedelta(seconds=min(300, 5 * 2 ** min(page.attempts, 6))),
            )
        return 0
    with transaction.atomic():
        current_build_id = renderer_digest()
        if current_build_id != build_id or any(
            generation_hash(page.payload, assets, current_build_id) != page.desired_hash for page in pages
        ):
            request_refresh()
            return 0
        # This write also serializes publishers on SQLite. It is rolled back if stale.
        if not RefreshState.objects.filter(pk=1, revision=revision, processed_revision=revision).update(revision=F('revision')):
            return 0
        for page in pages:
            if not StorePage.objects.filter(pk=page.pk, active=True, desired_hash=page.desired_hash).exists():
                return 0
        now = timezone.now()
        for page in pages:
            StorePage.objects.filter(pk=page.pk).update(
                html=output[page.path], rendered_payload=page.payload,
                rendered_changed_at=page.changed_at,
                rendered_hash=page.desired_hash, rendered_at=now, attempts=0, error='',
            )
    return len(pages)
