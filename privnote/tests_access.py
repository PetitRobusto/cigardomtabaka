"""高价值的 Privnote 访问观察回归测试。

这些测试只验证访问观察与现有业务状态之间的边界；访问观察失败不能阻断
客户请求，且日志不能被公开身份头伪造读取。
"""

import json
from io import StringIO
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.core.management import call_command
from django.http import HttpResponse
from django.db import DatabaseError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from cigars.models import SalesOrder, User
from privnote.access import record
from privnote.models import Privnote, PrivnoteAccessEvent as Access


@override_settings(
    DJANGO_DEBUG=True,
    DEBUG=True,
    PRIVNOTE_ACCESS_RETENTION_DAYS=30,
    PRIVNOTE_TRUSTED_PROXIES=[],
)
class PrivnoteAccessTestCase(TestCase):
    """访问端点、短期日志和访客绑定的行为契约。"""

    def _note(self, token, *, note_type=Privnote.NoteType.MESSAGE, **kwargs):
        defaults = {
            'note_type': note_type,
            'title': token,
            'data_json': {'message': 'hello'},
            'expires_at': timezone.now() + timedelta(days=1),
            'burn_after_read': False,
            'max_views': 0,
        }
        defaults.update(kwargs)
        return Privnote.objects.create(token=token, **defaults)

    def _staff(self, username='access-staff', telegram_id=None):
        return User.objects.create_user(username, password='testpass', is_staff=True, telegram_id=telegram_id)

    def _request(self, *, remote='127.0.0.1', user=None, **headers):
        request = RequestFactory().get('/api/privnote/test/', REMOTE_ADDR=remote, **headers)
        request.user = user or AnonymousUser()
        return request

    def test_successful_open_records_open_tracking_token_and_advances_only_once(self):
        note = self._note('open-once', view_count=3)

        response = self.client.get('/api/privnote/open-once/', REMOTE_ADDR='192.0.2.10')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('tracking_token'))
        note.refresh_from_db()
        self.assertEqual(note.view_count, 4)
        self.assertEqual(
            Access.objects.filter(privnote=note, event=Access.Event.OPEN).count(), 1
        )

    def test_observation_does_not_backfill_existing_view_count(self):
        note = self._note('legacy-count', view_count=7)

        entry = record(
            self._request(HTTP_USER_AGENT='Mozilla/5.0'),
            note,
            Access.Event.OPEN,
        )

        self.assertIsNotNone(entry)
        note.refresh_from_db()
        self.assertEqual(note.view_count, 7)
        self.assertEqual(Access.objects.filter(privnote=note).count(), 1)

    def test_anonymous_cookie_identity_is_stable_per_note_and_isolated_across_notes(self):
        first = self._note('cookie-a')
        second = self._note('cookie-b')
        browser_a = Client()
        browser_b = Client()

        browser_a.get('/api/privnote/cookie-a/', REMOTE_ADDR='192.0.2.11')
        browser_a.get('/api/privnote/cookie-a/', REMOTE_ADDR='192.0.2.11')
        browser_b.get('/api/privnote/cookie-a/', REMOTE_ADDR='192.0.2.11')
        browser_a.get('/api/privnote/cookie-b/', REMOTE_ADDR='192.0.2.11')

        a_events = list(Access.objects.filter(privnote=first, event=Access.Event.OPEN).order_by('id'))
        b_events = list(Access.objects.filter(privnote=second, event=Access.Event.OPEN).order_by('id'))
        self.assertEqual(len(a_events), 3)
        self.assertEqual(a_events[0].visitor_key, a_events[1].visitor_key)
        self.assertNotEqual(a_events[0].visitor_key, a_events[2].visitor_key)
        self.assertEqual(len(b_events), 1)
        self.assertNotEqual(a_events[0].visitor_key, b_events[0].visitor_key)

    def test_bad_expired_and_rotated_anonymous_cookies_do_not_break_open(self):
        note = self._note('cookie-recovery', note_type=Privnote.NoteType.PAYMENT)
        url = f'/api/privnote/{note.token}/'
        tracking = self.client.get(url).json()['tracking_token']
        original_cookie = self.client.cookies['privnote_visitor'].value
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() - 31 * 86400):
            old_response = HttpResponse()
            old_response.set_signed_cookie('privnote_visitor', 'old-visitor', salt='privnote.access')
        for label, cookie in (
            ('damaged', 'not-a-valid-signature'),
            ('expired', old_response.cookies['privnote_visitor'].value),
        ):
            with self.subTest(cookie=label):
                self.client.cookies['privnote_visitor'] = cookie
                rejected = self.client.post(
                    f'{url}events/', data=json.dumps({'event': 'qr_open', 'tracking_token': tracking}),
                    content_type='application/json',
                )
                self.assertEqual(rejected.status_code, 403)
                opened = self.client.get(url)
                self.assertEqual(opened.status_code, 200)
                self.assertTrue(opened.json()['tracking_token'])
                self.assertNotEqual(opened.cookies['privnote_visitor'].value, cookie)

        self.client.cookies['privnote_visitor'] = original_cookie
        with override_settings(SECRET_KEY='access-rotated-test-key', SECRET_KEY_FALLBACKS=[]):
            opened = self.client.get(url)
        self.assertEqual(opened.status_code, 200)
        self.assertTrue(opened.json()['tracking_token'])
        self.assertNotEqual(opened.cookies['privnote_visitor'].value, original_cookie)
        self.assertEqual(Access.objects.filter(privnote=note, event=Access.Event.OPEN).count(), 4)

    def test_access_outcomes_record_password_expired_destroyed_and_closed(self):
        password_note = self._note('password-note')
        password_note.set_password('secret')
        password_note.save()

        self.assertTrue(
            self.client.get('/api/privnote/password-note/').json()['requires_password']
        )
        wrong = self.client.post(
            '/api/privnote/password-note/',
            data=json.dumps({'password': 'wrong'}),
            content_type='application/json',
        )
        self.assertEqual(wrong.status_code, 401)
        opened = self.client.post(
            '/api/privnote/password-note/',
            data=json.dumps({'password': 'secret'}),
            content_type='application/json',
        )
        self.assertEqual(opened.status_code, 200)

        expired = self._note(
            'expired-note', expires_at=timezone.now() - timedelta(minutes=1)
        )
        destroyed = self._note('destroyed-note', burn_after_read=True, max_views=1, view_count=1)
        staff = self._staff('closed-owner')
        order = SalesOrder.objects.create(
            customer_name='closed',
            operator=staff,
            fulfillment_status=SalesOrder.FulfillmentStatus.DRAFT,
            payment_status=SalesOrder.PaymentStatus.UNPAID,
        )
        closed = self._note(
            'closed-note', note_type=Privnote.NoteType.PAYMENT, sales_order=order
        )

        self.assertEqual(self.client.get('/api/privnote/expired-note/').status_code, 410)
        self.assertEqual(self.client.get('/api/privnote/destroyed-note/').status_code, 410)
        self.assertEqual(self.client.get('/api/privnote/closed-note/').status_code, 410)

        events = {
            note.token: set(
                Access.objects.filter(privnote=note).values_list('event', flat=True)
            )
            for note in (password_note, expired, destroyed, closed)
        }
        self.assertIn(Access.Event.PASSWORD_REQUIRED, events[password_note.token])
        self.assertIn(Access.Event.PASSWORD_FAILED, events[password_note.token])
        self.assertIn(Access.Event.OPEN, events[password_note.token])
        self.assertEqual(events[expired.token], {Access.Event.EXPIRED})
        self.assertEqual(events[destroyed.token], {Access.Event.DESTROYED})
        self.assertEqual(events[closed.token], {Access.Event.CLOSED})

    def test_only_authenticated_staff_can_read_access_log_even_with_fake_telegram_header(self):
        note = self._note('staff-list')
        staff = self._staff('access-staff', telegram_id='tg-real-staff')
        self.client.get('/api/privnote/staff-list/')

        self.assertEqual(self.client.get('/privnote/api/access/').status_code, 403)
        self.assertEqual(
            self.client.get(
                '/privnote/api/access/', HTTP_X_TELEGRAM_ID=staff.telegram_id
            ).status_code,
            403,
        )

        staff_client = Client()
        staff_client.force_login(staff)
        listing = staff_client.get('/privnote/api/access/')
        detail = staff_client.get('/privnote/api/access/staff-list/')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertIn(note.token, {row['token'] for row in listing.json()['results']})

    def test_staff_and_bot_events_are_hidden_by_default_and_visible_with_audience_all(self):
        note = self._note('audience-note')
        staff_client = Client()
        staff_client.force_login(self._staff('audience-staff'))
        staff_client.get('/api/privnote/audience-note/')
        self.client.get(
            '/api/privnote/audience-note/',
            HTTP_USER_AGENT='Googlebot/2.1 (+http://www.google.com/bot.html)',
        )
        self.client.get('/api/privnote/audience-note/', HTTP_USER_AGENT='Mozilla/5.0 Chrome/1')

        detail = staff_client.get('/privnote/api/access/audience-note/').json()
        self.assertEqual(detail['summary']['opens'], 1)
        self.assertEqual(detail['summary']['visitors'], 1)
        self.assertEqual(detail['summary']['revisits'], 0)
        self.assertEqual(len(detail['results']), 1)
        self.assertEqual(detail['results'][0]['actor'], Access.Actor.CUSTOMER)

        all_events = staff_client.get(
            '/privnote/api/access/audience-note/?audience=all'
        ).json()['results']
        self.assertEqual({row['actor'] for row in all_events}, {
            Access.Actor.STAFF, Access.Actor.BOT, Access.Actor.CUSTOMER,
        })

    def test_access_detail_excludes_events_older_than_retention_window(self):
        note = self._note('retention-note')
        recent = Access.objects.create(
            privnote=note, visitor_key='recent-visitor', ip='192.0.2.20',
            device='未知设备', browser='未知浏览器', actor=Access.Actor.CUSTOMER,
            event=Access.Event.OPEN,
        )
        old = Access.objects.create(
            privnote=note, visitor_key='old-visitor', ip='192.0.2.21',
            device='未知设备', browser='未知浏览器', actor=Access.Actor.CUSTOMER,
            event=Access.Event.OPEN,
        )
        Access.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        staff_client = Client()
        staff_client.force_login(self._staff('retention-staff'))

        payload = staff_client.get('/privnote/api/access/retention-note/').json()
        self.assertEqual(payload['summary']['opens'], 1)
        self.assertEqual(payload['summary']['visitors'], 1)
        self.assertEqual([row['id'] for row in payload['results']], [recent.pk])

    def test_trusted_real_ip_accepts_ipv6_but_untrusted_forwarding_header_is_ignored(self):
        note = self._note('ip-note')
        with override_settings(PRIVNOTE_TRUSTED_PROXIES=['127.0.0.1']):
            trusted = record(
                self._request(
                    remote='127.0.0.1',
                    HTTP_X_REAL_IP='2001:db8::1',
                    HTTP_X_FORWARDED_FOR='203.0.113.99',
                    HTTP_USER_AGENT='Dalvik/1.6 (Linux; Android 13; ZZ Build/ABC) Mobile',
                ),
                note,
                Access.Event.OPEN,
            )
            untrusted = record(
                self._request(
                    remote='2001:db8::2',
                    HTTP_X_REAL_IP='192.0.2.99',
                    HTTP_USER_AGENT='Dalvik/1.6 (Linux; Android 13; ZZ Build/ABC)',
                ),
                note,
                Access.Event.OPEN,
            )

        self.assertEqual(trusted.ip, '2001:db8::1')
        self.assertEqual(untrusted.ip, '2001:db8::2')
        self.assertEqual(trusted.device, '安卓手机')
        self.assertEqual(trusted.browser, '未知浏览器')

    def test_device_parser_covers_iphone_wechat_huawei_pixel_and_safe_unknown_fallbacks(self):
        note = self._note('device-note')
        iphone = record(
            self._request(
                HTTP_USER_AGENT=(
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                    'MicroMessenger/8.0.45'
                )
            ),
            note,
            Access.Event.OPEN,
        )
        huawei = record(
            self._request(
                HTTP_USER_AGENT=(
                    'Mozilla/5.0 (Linux; Android 13; HUAWEI ABC Build/HUAWEI) '
                    'AppleWebKit/537.36 Mobile'
                )
            ),
            note,
            Access.Event.OPEN,
        )
        pixel = record(
            self._request(
                HTTP_USER_AGENT=(
                    'Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/AP2A) '
                    'AppleWebKit/537.36 Chrome/120.0 Mobile'
                )
            ),
            note,
            Access.Event.OPEN,
        )
        unknown = record(
            self._request(
                HTTP_USER_AGENT=(
                    'Mozilla/5.0 (Linux; Android 14; ZZ Build/UNKNOWN) '
                    'AppleWebKit/537.36 Mobile'
                ),
                HTTP_X_PRIVNOTE_MODEL='x' * 101,
            ),
            note,
            Access.Event.OPEN,
        )

        self.assertEqual((iphone.device, iphone.browser), ('iPhone', '微信'))
        self.assertEqual(huawei.device, '华为手机')
        self.assertEqual(pixel.device, 'Pixel 8')
        self.assertEqual(unknown.device, '安卓手机')
        self.assertLessEqual(len(unknown.device), 100)

    def test_payment_interactions_require_bound_visit_cookie_and_dedupe_per_event(self):
        payment = self._note('payment-events', note_type=Privnote.NoteType.PAYMENT)
        other = self._note('other-payment', note_type=Privnote.NoteType.PAYMENT)
        opened = self.client.get('/api/privnote/payment-events/')
        tracking = opened.json()['tracking_token']
        event_url = '/api/privnote/payment-events/events/'
        body = json.dumps({'event': Access.Event.QR_OPEN, 'tracking_token': tracking})

        first = self.client.post(event_url, data=body, content_type='application/json')
        duplicate = self.client.post(event_url, data=body, content_type='application/json')
        illegal = self.client.post(
            event_url,
            data=json.dumps({'event': Access.Event.SUBMISSION, 'tracking_token': tracking}),
            content_type='application/json',
        )
        cross_token = self.client.post(
            f'/api/privnote/{other.token}/events/', data=body, content_type='application/json'
        )
        missing_cookie = Client().post(event_url, data=body, content_type='application/json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(illegal.status_code, 400)
        self.assertEqual(cross_token.status_code, 403)
        self.assertEqual(missing_cookie.status_code, 403)
        self.assertEqual(
            Access.objects.filter(privnote=payment, event=Access.Event.QR_OPEN).count(), 1
        )

    def test_interactions_reject_malformed_expired_and_password_revoked_credentials(self):
        note = self._note('secure-events', note_type=Privnote.NoteType.PAYMENT)
        note.set_password('secret')
        note.save()
        tracking = self.client.post(
            f'/api/privnote/{note.token}/',
            data=json.dumps({'password': 'secret'}), content_type='application/json',
        ).json()['tracking_token']
        url = f'/api/privnote/{note.token}/events/'
        for body in ('[]', '{', json.dumps({'event': [], 'tracking_token': tracking}),
                     json.dumps({'event': 'qr_open', 'tracking_token': 'tampered'})):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(url, data=body, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(url, data='x' * 2049, content_type='application/json').status_code, 413)

        claim = signing.loads(tracking, salt='privnote.access')
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() - 86401):
            expired = signing.dumps(claim, salt='privnote.access')
        self.assertEqual(self.client.post(
            url, data=json.dumps({'event': 'qr_open', 'tracking_token': expired}),
            content_type='application/json',
        ).status_code, 400)

        note.set_password('changed')
        note.save()
        self.assertEqual(self.client.post(
            url, data=json.dumps({'event': 'qr_open', 'tracking_token': tracking}),
            content_type='application/json',
        ).status_code, 403)
        self.assertFalse(Access.objects.filter(privnote=note, event=Access.Event.QR_OPEN).exists())

    def test_detail_pagination_keeps_summary_and_first_visit_across_pages(self):
        note = self._note('paginated-events')
        for _ in range(26):
            self.client.get(f'/api/privnote/{note.token}/')
        self.client.force_login(self._staff('pagination-staff'))
        first = self.client.get(f'/privnote/api/access/{note.token}/').json()
        second = self.client.get(f'/privnote/api/access/{note.token}/?page=2').json()
        self.assertEqual((first['count'], first['pages'], len(first['results'])), (26, 2, 25))
        self.assertEqual(len(second['results']), 1)
        self.assertEqual(first['summary'], second['summary'])
        self.assertEqual(first['summary']['revisits'], 25)
        self.assertTrue(all(row['is_revisit'] for row in first['results']))
        self.assertFalse(second['results'][0]['is_revisit'])

    def test_purge_command_defaults_to_preview_and_apply_keeps_view_count(self):
        note = self._note('purge-note', view_count=9)
        recent = Access.objects.create(
            privnote=note, visitor_key='recent', ip='192.0.2.30',
            device='未知设备', browser='未知浏览器', actor=Access.Actor.CUSTOMER,
            event=Access.Event.OPEN,
        )
        old = Access.objects.create(
            privnote=note, visitor_key='old', ip='192.0.2.31',
            device='未知设备', browser='未知浏览器', actor=Access.Actor.CUSTOMER,
            event=Access.Event.OPEN,
        )
        Access.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )

        preview = StringIO()
        call_command('purge_privnote_access', stdout=preview)
        self.assertIn('未修改', preview.getvalue())
        self.assertTrue(Access.objects.filter(pk=old.pk).exists())

        applied = StringIO()
        call_command('purge_privnote_access', '--apply', stdout=applied)
        self.assertIn('累计查看次数不变', applied.getvalue())
        self.assertFalse(Access.objects.filter(pk=old.pk).exists())
        self.assertTrue(Access.objects.filter(pk=recent.pk).exists())
        note.refresh_from_db()
        self.assertEqual(note.view_count, 9)

    @patch('privnote.access.Access.objects.create', side_effect=DatabaseError('telemetry down'))
    def test_database_error_while_recording_does_not_break_successful_business_response(self, _create):
        note = self._note('telemetry-failure')

        response = self.client.get('/api/privnote/telemetry-failure/')

        self.assertEqual(response.status_code, 200)
        note.refresh_from_db()
        self.assertEqual(note.view_count, 1)


class PrivnoteAccessModelTestCase(TestCase):
    """访问观察模型之外，保留阅后即焚的旧 mark_viewed 语义。"""

    @override_settings(DJANGO_DEBUG=True, DEBUG=True)
    def test_mark_viewed_remains_a_plain_legacy_counter(self):
        note = Privnote.objects.create(
            token='legacy-mark',
            expires_at=timezone.now() + timedelta(hours=1),
            burn_after_read=True,
            max_views=1,
        )

        note.mark_viewed()
        note.mark_viewed()
        note.refresh_from_db()
        self.assertEqual(note.view_count, 2)
