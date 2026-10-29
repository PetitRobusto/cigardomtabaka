"""Notify changes to successfully published public pages, outside business transactions."""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_safe

from .models import IndexNowState, IndexNowURL, RefreshState, StorePage

ENDPOINT = 'https://yandex.com/indexnow'
MIN_INTERVAL = timedelta(minutes=10)
MAX_ATTEMPTS = 6
BATCH_SIZE = 100
logger = logging.getLogger(__name__)


def configuration():
    if not getattr(settings, 'INDEXNOW_ENABLED', False) or not settings.STOREFRONT_ENABLED:
        return None
    key = getattr(settings, 'INDEXNOW_KEY', '')
    origin = settings.STOREFRONT_ORIGIN.rstrip('/')
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError as exc:
        raise ImproperlyConfigured('Invalid IndexNow canonical origin') from exc
    if not re.fullmatch(r'[A-Za-z0-9-]{8,128}', key):
        raise ImproperlyConfigured('INDEXNOW_KEY must contain 8–128 ASCII letters, digits or hyphens')
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or port):
        raise ImproperlyConfigured('IndexNow requires an HTTPS canonical origin without port or path')
    return origin, key


@require_safe
def verification(request, key):
    config = configuration()
    if not config or not constant_time_compare(key, config[1]):
        raise Http404
    return HttpResponse(config[1], content_type='text/plain; charset=utf-8', headers={
        'X-Robots-Tag': 'noindex', 'Cache-Control': 'no-cache',
    })


def _public_snapshot():
    from .catalog import allowed_payload, public_dependencies, public_page_paths, semantic_hash
    dependencies = public_dependencies()
    paths = public_page_paths(dependencies)
    # These are the same eligibility rules as the public sitemap. Content, not
    # renderer/build hashes, defines changes; failed renders keep the previous version.
    return {
        path: semantic_hash(payload)
        for path, payload in StorePage.objects.filter(
            active=True, html__gt='', rendered_hash__gt='',
        ).values_list('path', 'rendered_payload')
        if path in paths and payload.get('indexable') and allowed_payload(payload, dependencies)
    }


def _safe_public_path(path):
    parsed = urlsplit(path)
    return (path.startswith('/') and not path.startswith('//') and not parsed.netloc
            and not parsed.scheme and not parsed.fragment and '\\' not in path
            and not any(ord(c) < 32 for c in path))


def next_attempt(row, now):
    return max(now, row.last_attempt_at + MIN_INTERVAL) if row.last_attempt_at else now


def sync_changes():
    """Coalesce actual public state. The first successful scan seeds a quiet baseline."""
    config = configuration()
    if not config:
        return None
    origin, key = config
    state, _ = IndexNowState.objects.get_or_create(origin=origin)
    now = timezone.now()
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    with transaction.atomic():
        # Take the SQLite writer lock before building the snapshot. No concurrent
        # publisher can make an older snapshot overwrite a newer queue generation.
        IndexNowState.objects.filter(pk=state.pk).update(key_hash=F('key_hash'))
        state.refresh_from_db()
        refresh = RefreshState.objects.filter(pk=1).first()
        if refresh and refresh.revision != refresh.processed_revision:
            return None
        snapshot = _public_snapshot()
        # During incomplete publication, old pages can temporarily fail dependency
        # checks (503). Defer the scan instead of notifying those as deletions.
        if StorePage.objects.filter(active=True).exclude(desired_hash=F('rendered_hash')).exists():
            return None
        if any(not _safe_public_path(path) for path in snapshot):
            raise ValueError('Non-local path in public IndexNow snapshot')
        existing = {row.path: row for row in state.urls.all()}
        first_scan = state.initialized_at is None
        for path in sorted(snapshot.keys() | existing.keys()):
            wanted = snapshot.get(path, '')
            row = existing.get(path)
            if row is None:
                IndexNowURL.objects.create(
                    state=state, path=path, desired_hash=wanted,
                    notified_hash=wanted if first_scan else '',
                    retry_at=None if first_scan else now, updated_at=now,
                )
            elif row.desired_hash != wanted:
                due = next_attempt(row, now)
                IndexNowURL.objects.filter(pk=row.pk).update(
                    desired_hash=wanted, attempts=0,
                    retry_at=due if wanted != row.notified_hash else None,
                    error='', updated_at=now,
                )
            elif state.key_hash != key_hash and wanted != row.notified_hash:
                # A corrected verification key releases permanent failures.
                IndexNowURL.objects.filter(pk=row.pk).update(
                    attempts=0, retry_at=next_attempt(row, now), error='',
                )
        IndexNowState.objects.filter(pk=state.pk).update(
            initialized_at=state.initialized_at or now, key_hash=key_hash,
        )
    return state


def _post(payload):
    # Redirects are not notification acceptance (the endpoint redirects a bare GET
    # to its documentation). Never forward the verification key to another host.
    response = requests.post(ENDPOINT, json=payload, timeout=(3, 10), allow_redirects=False)
    return response.status_code, response.headers.get('Retry-After')


def send_pending(*, transport=None):
    """One bounded batch; lease + generation checks preserve concurrent changes."""
    config = configuration()
    if not config:
        return {'sent': 0, 'status': 'disabled'}
    origin, key = config
    state = sync_changes()
    if not state:
        return {'sent': 0, 'status': 'publication_pending'}
    now, token = timezone.now(), uuid.uuid4().hex
    acquired = IndexNowState.objects.filter(pk=state.pk).filter(
        Q(lease_until__isnull=True) | Q(lease_until__lte=now),
    ).update(lease_token=token, lease_until=now + timedelta(minutes=2))
    if not acquired:
        return {'sent': 0, 'status': 'busy'}
    rows = []
    try:
        with transaction.atomic():
            # Persist the attempt before networking. Concurrent content updates and
            # recovery after a killed worker must respect this URL's cooldown.
            if not IndexNowState.objects.filter(pk=state.pk, lease_token=token).update(lease_token=token):
                return {'sent': 0, 'status': 'busy'}
            rows = list(state.urls.filter(retry_at__lte=now, attempts__lt=MAX_ATTEMPTS).exclude(
                desired_hash=F('notified_hash'),
            ).order_by('retry_at', 'pk')[:BATCH_SIZE])
            if any(not _safe_public_path(row.path) for row in rows):
                raise ValueError('Non-local path in IndexNow queue')
            for row in rows:
                IndexNowURL.objects.filter(pk=row.pk).update(
                    attempts=row.attempts + 1, last_attempt_at=now, last_status=None,
                    retry_at=now + MIN_INTERVAL if row.attempts + 1 < MAX_ATTEMPTS else None,
                    error='Notification outcome unknown',
                )
        if not rows:
            return {'sent': 0, 'status': 'idle'}
        payload = {'host': urlsplit(origin).hostname, 'key': key,
                   'keyLocation': f'{origin}/{key}.txt',
                   'urlList': [origin + row.path for row in rows]}
        status, retry_after, error = None, None, ''
        try:
            status, retry_after = (transport or _post)(payload)
        except requests.RequestException as exc:
            # Exception text may contain request/key details. Persist only its type.
            error = type(exc).__name__
        accepted = status in (200, 202)
        transient = status is None or status == 429 or (status is not None and 500 <= status <= 599)
        for row in rows:
            attempt = row.attempts + 1
            updates = {'attempts': attempt, 'last_attempt_at': now, 'last_status': status}
            if accepted:
                updates.update(notified_hash=row.desired_hash, retry_at=None, error='')
            else:
                delay = min(86400, 600 * 2 ** min(attempt - 1, 7))
                if retry_after and str(retry_after).isdigit():
                    delay = max(delay, min(86400, int(retry_after)))
                updates.update(
                    retry_at=now + timedelta(seconds=delay) if transient and attempt < MAX_ATTEMPTS else None,
                    error=error or f'IndexNow HTTP {status}',
                )
            # An in-flight completion must never acknowledge a newer public version.
            IndexNowURL.objects.filter(pk=row.pk, desired_hash=row.desired_hash,
                                       updated_at=row.updated_at).update(**updates)
        if not accepted:
            logger.warning('IndexNow notification deferred: HTTP %s; %s URLs', status, len(rows))
        return {'sent': len(rows) if accepted else 0, 'attempted': len(rows), 'status': status}
    finally:
        IndexNowState.objects.filter(pk=state.pk, lease_token=token).update(lease_token='', lease_until=None)


def process_changes():
    if not configuration():
        return {'sent': 0, 'status': 'disabled'}
    return send_pending()
