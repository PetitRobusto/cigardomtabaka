import base64
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from accounting.models import Day1Initialization, FundAccount
from cigars.models import Brand, Cigar, OrderEvent, SalesOrder, SalesOrderItem, SalesReceipt, User
from cigars.sales_accounting import receive_sales_order_payment
from cigars.services import cancel_confirmed_sales_order
from privnote.models import PaymentMethod, PaymentSubmission
from privnote.services.payment_requests import create_payment_request


PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


class PaymentSubmissionWorkflowTest(TestCase):
    """The customer declaration must stay separate from the accounting receipt."""

    def setUp(self):
        self.staff = User.objects.create_user('proof-reviewer', password='pass', is_staff=True)
        self.client = Client()
        self.staff_client = Client()
        self.staff_client.force_login(self.staff)
        Day1Initialization.objects.create(
            singleton_key='company', status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 9, 11), completed_by=self.staff,
        )
        self.account = FundAccount.objects.create(
            name='凭证测试 CNY', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='proof-test-account',
        )
        brand = Brand.objects.create(english_name='Proof Brand', name='凭证品牌')
        cigar = Cigar.objects.create(brand=brand.english_name, english_name='Proof Cigar', name='凭证雪茄')
        self.order = SalesOrder.objects.create(
            operator=self.staff, customer_name='付款客户',
            fulfillment_status=SalesOrder.FulfillmentStatus.CONFIRMED,
            payment_status=SalesOrder.PaymentStatus.UNPAID, status='pending_payment',
            goods_amount_cny=Decimal('120.00'), amount_due_cny=Decimal('120.00'), total_revenue=Decimal('120.00'),
        )
        SalesOrderItem.objects.create(
            sales_order=self.order, cigar=cigar, quantity=1,
            sale_unit=SalesOrderItem.SaleUnit.STICK, sale_quantity=1,
            unit_price=Decimal('120.00'), unit_cost=Decimal('80.00'),
            revenue=Decimal('120.00'), cost=Decimal('80.00'), profit=Decimal('40.00'),
        )

    def _note(self, *, password='', with_qr=False):
        return create_payment_request(
            sales_order_id=self.order.id, duration_hours=24, password=password,
            source='temporary', fund_account_id=self.account.id,
            method_type='wechat', account='proof-wechat',
            qr_file=self._image('payment-qr.png') if with_qr else None,
            operator=self.staff,
        )

    def _image(self, name='proof.png'):
        return SimpleUploadedFile(name, PNG, content_type='image/png')

    def _submit(self, note, *, key='proof-submit-1'):
        return self.client.post(
            f'/api/privnote/{note.token}/payment-submissions/',
            {'files': self._image()}, HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_temporary_request_is_repeat_viewable_and_snapshots_only_internal_account_id(self):
        note = self._note()
        self.assertFalse(note.burn_after_read)
        self.assertEqual(note.max_views, 0)
        self.assertEqual(note.data_json['schema_version'], 2)
        self.assertEqual(note.data_json['payment']['source'], 'temporary')
        self.assertEqual(note.data_json['payment']['fund_account_id'], self.account.id)
        response = self.client.get(f'/api/privnote/{note.token}/')
        self.assertEqual(response.status_code, 200)
        method = response.json()['data']['payment_methods'][0]
        self.assertNotIn('fund_account_id', method)
        self.assertEqual(response.json()['data']['payment_flow']['status'], 'active')

    def test_saved_qr_is_copied_to_private_snapshot_and_keeps_its_content_type(self):
        method = PaymentMethod.objects.create(
            method_type=PaymentMethod.MethodType.WECHAT,
            label='常用二维码', fund_account=self.account,
            qr_image=self._image('saved-qr.png'),
        )
        note = create_payment_request(
            sales_order_id=self.order.id, duration_hours=24, password='',
            source='saved', payment_method_id=method.id, operator=self.staff,
        )
        self.assertTrue(note.data_json['payment']['qr_private_name'].startswith('payment-qrs/'))
        qr = self.client.get(f'/api/privnote/{note.token}/payment-images/qr/')
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(qr['Content-Type'], 'image/png')

    def test_invalid_temporary_qr_returns_400_without_creating_a_payment_request(self):
        from privnote.models import Privnote

        self.staff_client.raise_request_exception = False
        invalid_images = [
            ('empty.png', b'', 'image/png'),
            ('invalid.png', b'not an image', 'image/png'),
            ('unsupported.gif', PNG, 'image/gif'),
            ('large.png', b'x' * (5 * 1024 * 1024 + 1), 'image/png'),
        ]
        for name, content, content_type in invalid_images:
            with self.subTest(name=name):
                response = self.staff_client.post('/privnote/create/', {
                    'note_type': 'payment', 'sales_order_id': self.order.id,
                    'duration': '24', 'payment_source': 'temporary',
                    'fund_account_id': self.account.id, 'temporary_method_type': 'wechat',
                    'temporary_qr_image': SimpleUploadedFile(name, content, content_type=content_type),
                })
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())
                self.assertFalse(Privnote.objects.filter(sales_order=self.order).exists())
                self.assertFalse(SalesReceipt.objects.filter(sales_order=self.order).exists())

    def test_anonymous_submission_is_idempotent_and_does_not_create_a_receipt(self):
        note = self._note()
        first = self._submit(note)
        second = self._submit(note)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(PaymentSubmission.objects.count(), 1)
        self.assertFalse(SalesReceipt.objects.filter(sales_order=self.order).exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, SalesOrder.PaymentStatus.UNPAID)
        submission = PaymentSubmission.objects.get()
        self.assertEqual(submission.status, PaymentSubmission.Status.PENDING)
        self.assertEqual(submission.attachments.count(), 1)

    def test_password_protects_submission_and_private_attachment_read(self):
        note = self._note(password='open-sesame')
        unauthorised = self._submit(note)
        self.assertEqual(unauthorised.status_code, 401)
        unlocked = self.client.post(f'/api/privnote/{note.token}/', data='{"password":"open-sesame"}', content_type='application/json')
        self.assertEqual(unlocked.status_code, 200)
        created = self._submit(note)
        self.assertEqual(created.status_code, 201)
        attachment_id = PaymentSubmission.objects.get().attachments.get().id
        image = self.client.get(f'/api/privnote/{note.token}/payment-images/{attachment_id}/')
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image['Cache-Control'], 'private, no-store')

    def test_needs_more_then_new_submission_and_acceptance_creates_one_receipt(self):
        note = self._note()
        self._submit(note)
        first = PaymentSubmission.objects.get()
        more = self.staff_client.post(
            f'/api/sales/orders/{self.order.id}/payment-submissions/{first.id}/needs-more/',
            data='{"review_note":"请上传完整银行回单"}', content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='proof-needs-more',
        )
        self.assertEqual(more.status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.status, PaymentSubmission.Status.NEEDS_MORE)
        self.assertEqual(first.review_note, '请上传完整银行回单')
        second = self._submit(note, key='proof-submit-2')
        self.assertEqual(second.status_code, 201)
        current = PaymentSubmission.objects.get(status=PaymentSubmission.Status.PENDING)
        accepted = self.staff_client.post(
            f'/api/sales/orders/{self.order.id}/payment-submissions/{current.id}/accept/',
            data='{"business_date":"2026-09-11"}', content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='proof-accept',
        )
        self.assertEqual(accepted.status_code, 200)
        current.refresh_from_db()
        self.assertEqual(current.status, PaymentSubmission.Status.ACCEPTED)
        self.assertIsNotNone(current.sales_receipt_id)
        self.assertEqual(SalesReceipt.objects.filter(sales_order=self.order).count(), 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, SalesOrder.PaymentStatus.PAID)

    def test_direct_receipt_closes_pending_evidence(self):
        note = self._note(with_qr=True)
        self._submit(note)
        receipt = receive_sales_order_payment(
            order_id=self.order.id, amount_cny=Decimal('120.00'), fund_account=self.account,
            business_date=date(2026, 9, 11), operator=self.staff, idempotency_key='direct-proof-receipt',
        )
        self.assertEqual(receipt.sales_order_id, self.order.id)
        submission = PaymentSubmission.objects.get()
        self.assertEqual(submission.status, PaymentSubmission.Status.CLOSED)
        self.assertEqual(submission.closed_reason, 'paid_elsewhere')
        event = OrderEvent.objects.get(
            sales_order=self.order, command_name='receive_sales_order_payment',
        )
        self.assertEqual(event.operator_id, self.staff.id)
        self.assertEqual(event.metadata['payment_submission_ids_closed'], [submission.id])
        self.assertEqual(event.metadata['payment_submission_close_reason'], 'paid_elsewhere')
        self.assertEqual(event.metadata['idempotency_key'], 'direct-proof-receipt')
        customer_page = self.client.get(f'/api/privnote/{note.token}/')
        self.assertEqual(customer_page.status_code, 200)
        self.assertEqual(customer_page.json()['data']['payment_flow']['status'], 'accepted')
        self.assertIsNone(customer_page.json()['data']['payment_methods'][0]['qr_url'])
        self.assertEqual(
            self.client.get(f'/api/privnote/{note.token}/payment-images/qr/').status_code,
            404,
        )

    def test_order_cancellation_closes_pending_evidence_without_deleting_it(self):
        note = self._note()
        self._submit(note)
        cancel_confirmed_sales_order(
            sales_order_id=self.order.id, operator=self.staff,
            note='客户取消订单', business_date=date(2026, 9, 11),
        )
        submission = PaymentSubmission.objects.get()
        self.assertEqual(submission.status, PaymentSubmission.Status.CLOSED)
        self.assertEqual(submission.closed_reason, 'order_cancelled')
        self.assertEqual(submission.attachments.count(), 1)
        event = OrderEvent.objects.get(sales_order=self.order, command_name='cancel_confirmed_sales_order')
        self.assertEqual(event.metadata['payment_submission_ids_closed'], [submission.id])
        self.assertEqual(event.metadata['payment_submission_close_reason'], 'order_cancelled')

    def test_review_replay_must_match_original_audit_and_unknown_submission_is_404(self):
        note = self._note()
        self._submit(note)
        submission = PaymentSubmission.objects.get()
        accepted = self.staff_client.post(
            f'/api/sales/orders/{self.order.id}/payment-submissions/{submission.id}/accept/',
            data='{"business_date":"2026-09-11"}', content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='proof-accept-audit',
        )
        self.assertEqual(accepted.status_code, 200)
        conflicting_replay = self.staff_client.post(
            f'/api/sales/orders/{self.order.id}/payment-submissions/{submission.id}/accept/',
            data='{"business_date":"2026-09-10"}', content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='proof-accept-audit-different',
        )
        self.assertEqual(conflicting_replay.status_code, 409)
        unknown = self.staff_client.post(
            f'/api/sales/orders/{self.order.id}/payment-submissions/999999/needs-more/',
            data='{"review_note":"请补充"}', content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='proof-unknown-submission',
        )
        self.assertEqual(unknown.status_code, 404)
