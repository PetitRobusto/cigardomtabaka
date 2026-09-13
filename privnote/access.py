"""Best-effort, short-lived access observations, independent of business facts."""
import ipaddress
import json
import logging
import re
import uuid
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.core import signing
from django.core.paginator import Paginator
from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError, transaction
from django.db.models import Count, Max, Min, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Privnote, PrivnoteAccessEvent as Access

logger = logging.getLogger(__name__)
COOKIE = 'privnote_visitor'
SALT = 'privnote.access'
CLIENT_EVENTS = {Access.Event.QR_OPEN, Access.Event.COPY_CARD, Access.Event.COPY_ACCOUNT}


def retention_days():
    return max(1, int(getattr(settings, 'PRIVNOTE_ACCESS_RETENTION_DAYS', 30)))


def recent_events():
    return Access.objects.filter(created_at__gte=timezone.now() - timedelta(days=retention_days()))


def client_ip(request):
    peer = request.META.get('REMOTE_ADDR', '')
    # Empty REMOTE_ADDR is possible for Gunicorn's Unix socket; it still needs
    # explicit trust. Never take arbitrary client-supplied forwarding headers.
    trusted = getattr(settings, 'PRIVNOTE_TRUSTED_PROXIES', ())
    raw = request.headers.get('X-Real-IP', peer) if (peer or 'unix') in trusted else peer
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def device_info(ua, model=''):
    """No screen-size guesses or invented device-code mappings."""
    ua = ua[:1024]
    model = model.strip(' "')[:100]
    if not re.fullmatch(r'[\w .()+-]{0,100}', model):
        model = ''
    browser = next((label for marker, label in (
        ('MicroMessenger/', '微信'), ('AlipayClient/', '支付宝'),
        ('Edg', 'Edge'), ('OPR/', 'Opera'), ('SamsungBrowser/', '三星浏览器'),
        ('HuaweiBrowser/', '华为浏览器'), ('Firefox/', 'Firefox'),
        ('FxiOS/', 'Firefox'), ('Chrome/', 'Chrome'), ('CriOS/', 'Chrome'),
        ('Safari/', 'Safari'),
    ) if marker in ua), '未知浏览器')
    if 'iPhone' in ua:
        return 'iPhone', browser
    if 'iPad' in ua:
        return 'iPad', browser
    if 'Android' in ua or 'HarmonyOS' in ua:
        if not model:
            found = re.search(r';\s*([^;()]+?)\s+Build/', ua)
            model = found.group(1).strip()[:100] if found else ''
        combined = f'{ua} {model}'
        # Show exact names only when the browser actually provides a readable
        # name. Unknown vendor codes safely fall back to the brand.
        marketed = re.fullmatch(r'(?:Pixel \d[\w +.-]*|(?:HUAWEI |HONOR |Samsung )?(?:Mate|Pura|Galaxy) [\w +.-]+)', model, re.I)
        if marketed:
            return model, browser
        for marker, name in (
            ('HUAWEI', '华为'), ('HarmonyOS', '华为'), ('HONOR', '荣耀'),
            ('SAMSUNG', '三星'), ('SM-', '三星'), ('Xiaomi', '小米'),
            ('Redmi', 'Redmi'), ('OPPO', 'OPPO'), ('vivo', 'vivo'), ('OnePlus', '一加'),
        ):
            if marker.lower() in combined.lower():
                return name + ('平板' if 'Tablet' in ua else '手机'), browser
        return ('安卓手机' if 'Mobile' in ua else '安卓设备'), browser
    for marker, name in (('Windows', 'Windows 电脑'), ('Macintosh', 'Mac'), ('Linux', 'Linux 电脑')):
        if marker in ua:
            return name, browser
    return '未知设备', browser


def visitor_cookie(request):
    return request.get_signed_cookie(COOKIE, default='', salt=SALT, max_age=retention_days() * 86400)


def visitor_key(request, note, cookie=None):
    cookie = cookie or visitor_cookie(request)
    return salted_hmac(SALT, f'{note.pk}:{cookie}', algorithm='sha256').hexdigest() if cookie else ''


def record(request, note, event, *, visitor='', dedupe_key=None):
    ua = request.headers.get('User-Agent', '')[:1024]
    actor = Access.Actor.CUSTOMER
    if request.user.is_authenticated and request.user.is_staff:
        actor = Access.Actor.STAFF
    elif re.search(r'bot\b|crawler|spider|slackbot|telegrambot|facebookexternalhit|preview', ua, re.I):
        actor = Access.Actor.BOT
    device, browser = device_info(ua, request.headers.get('X-Privnote-Model', '') or request.headers.get('Sec-CH-UA-Model', ''))
    try:
        # A savepoint isolates telemetry failures from an outer transaction.
        with transaction.atomic():
            fields = dict(visitor_key=visitor or visitor_key(request, note), ip=client_ip(request),
                          device=device, browser=browser, actor=actor, event=event)
            if dedupe_key:
                return Access.objects.get_or_create(privnote=note, dedupe_key=dedupe_key, defaults=fields)[0]
            return Access.objects.create(privnote=note, **fields)
    except DatabaseError:
        logger.warning('Privnote access observation could not be saved', exc_info=True)
        return None


def observe_access(view):
    @wraps(view)
    def wrapped(request, token):
        response = view(request, token)
        note = getattr(request, '_access_note', None)
        if note is None:
            return response
        body = json.loads(response.content)
        if body.get('error'):
            event = {'expired': Access.Event.EXPIRED, 'destroyed': Access.Event.DESTROYED,
                     'closed': Access.Event.CLOSED}.get(body['error'], Access.Event.ERROR)
            if body.get('requires_password'):
                event = Access.Event.PASSWORD_FAILED
        elif body.get('requires_password'):
            event = Access.Event.PASSWORD_REQUIRED
        else:
            event = Access.Event.OPEN
        cookie = visitor_cookie(request)
        new_cookie = not cookie
        cookie = cookie or uuid.uuid4().hex
        visitor = visitor_key(request, note, cookie)
        entry = record(request, note, event, visitor=visitor)
        if entry and event == Access.Event.OPEN:
            body['tracking_token'] = signing.dumps({'visit': entry.pk, 'note': note.pk, 'visitor': visitor}, salt=SALT)
            response.content = json.dumps(body)
        if new_cookie:
            response.set_signed_cookie(COOKIE, cookie, salt=SALT, max_age=retention_days() * 86400,
                                       httponly=True, secure=request.is_secure() or not settings.DEBUG, samesite='Lax', path='/api/privnote/')
        response['Cache-Control'] = 'private, no-store'
        return response
    return wrapped


def staff_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        # A public Telegram ID supplied in a header is not authentication.
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({'error': '仅限已登录工作人员'}, status=403)
        response = view(request, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response
    return wrapped


def page_data(request, queryset):
    page = Paginator(queryset, 25).get_page(request.GET.get('page', '1'))
    return page, {'page': page.number, 'pages': page.paginator.num_pages, 'count': page.paginator.count}


def note_data(note):
    return {'token': note.token, 'title': note.title, 'note_type': note.note_type,
            'created_at': note.created_at.isoformat(), 'view_count': note.view_count}


@require_GET
@staff_only
def access_notes(request):
    notes = Privnote.objects.all().order_by('-created_at', '-id')
    q = request.GET.get('q', '').strip()[:200]
    if q:
        notes = notes.filter(Q(title__icontains=q) | Q(token__icontains=q))
    if request.GET.get('type'):
        notes = notes.filter(note_type=request.GET['type'])
    page, pagination = page_data(request, notes)
    rows = list(page)
    latest = dict(recent_events().filter(privnote__in=rows, event=Access.Event.OPEN, actor=Access.Actor.CUSTOMER)
                  .values('privnote_id').annotate(last=Max('created_at')).values_list('privnote_id', 'last'))
    return JsonResponse({'results': [{**note_data(note), 'last_opened_at': latest[note.pk].isoformat() if note.pk in latest else None}
                                     for note in rows], **pagination, 'retention_days': retention_days()})


@require_GET
@staff_only
def access_detail(request, token):
    note = get_object_or_404(Privnote, token=token)
    events = recent_events().filter(privnote=note)
    opens = events.filter(event=Access.Event.OPEN, actor=Access.Actor.CUSTOMER)
    summary = opens.aggregate(opens=Count('id'), visitors=Count('visitor_key', distinct=True, filter=~Q(visitor_key='')),
                              identified_opens=Count('id', filter=~Q(visitor_key='')), last_opened_at=Max('created_at'))
    summary['revisits'] = summary.pop('identified_opens') - summary['visitors']
    if request.GET.get('audience') != 'all':
        events = events.filter(actor=Access.Actor.CUSTOMER)
    page, pagination = page_data(request, events)
    rows = list(page)
    first_ids = dict(opens.filter(visitor_key__in=[row.visitor_key for row in rows if row.visitor_key])
                     .values('visitor_key').annotate(first=Min('id')).values_list('visitor_key', 'first'))
    return JsonResponse({'note': note_data(note), 'summary': summary, 'retention_days': retention_days(), **pagination,
                         'results': [{'id': row.pk, 'created_at': row.created_at.isoformat(),
                                      'visitor': row.visitor_key[:10], 'ip': row.ip, 'device': row.device,
                                      'browser': row.browser, 'actor': row.actor, 'event': row.event,
                                      'is_revisit': row.event == Access.Event.OPEN and row.actor == Access.Actor.CUSTOMER
                                      and row.pk != first_ids.get(row.visitor_key, row.pk)} for row in rows]})


@csrf_exempt
@require_POST
def access_event(request, token):
    try:
        if int(request.META.get('CONTENT_LENGTH') or 0) > 2048 or len(request.body) > 2048:
            return JsonResponse({'error': '请求过大'}, status=413)
        body = json.loads(request.body)
        if not isinstance(body, dict) or body.get('event') not in CLIENT_EVENTS:
            raise ValueError
        if not isinstance(body.get('tracking_token'), str):
            raise ValueError
        claim = signing.loads(body['tracking_token'], salt=SALT, max_age=86400)
        if not isinstance(claim, dict):
            raise ValueError
    except RequestDataTooBig:
        return JsonResponse({'error': '请求过大'}, status=413)
    except (ValueError, TypeError, signing.BadSignature):
        return JsonResponse({'error': '无效访问凭据或操作'}, status=400)
    note = get_object_or_404(Privnote, token=token)
    if (claim.get('note') != note.pk or not claim.get('visitor')
            or claim['visitor'] != visitor_key(request, note)
            or note.note_type != Privnote.NoteType.PAYMENT or note.is_expired
            or (note.has_password and request.session.get(f'privnote-password:{note.token}') != note.password_hash)):
        return JsonResponse({'error': '无权记录此操作'}, status=403)
    visit = recent_events().filter(pk=claim.get('visit'), privnote=note, visitor_key=claim['visitor'], event=Access.Event.OPEN).first()
    if not visit:
        return JsonResponse({'error': '访问已失效'}, status=403)
    record(request, note, body['event'], dedupe_key=f"visit:{visit.pk}:{body['event']}")
    return JsonResponse({'ok': True})
