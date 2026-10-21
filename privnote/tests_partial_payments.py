import json
from datetime import date

from django.test import TestCase

from accounting.models import FundAccount
from cigars.models import SalesReceipt
from privnote.models import PaymentSubmission
from privnote.services.payment_submissions import accept_payment_submission, PaymentSubmissionError
from privnote import tests_payment_submissions as fixtures


class PartialPaymentEvidenceTest(TestCase):
    setUp = fixtures.PaymentSubmissionWorkflowTest.setUp
    _note = fixtures.PaymentSubmissionWorkflowTest._note
    _image = fixtures.PaymentSubmissionWorkflowTest._image
    _submit = fixtures.PaymentSubmissionWorkflowTest._submit

    def accept(self, submission, amount, key, account=None):
        return self.staff_client.post(
            f'/api/sales/orders/{self.order.pk}/payment-submissions/{submission.pk}/accept/',
            data=json.dumps({'business_date': '2026-09-11', 'amount_cny': amount,
                             'fund_account_id': (account or self.account).pk}),
            content_type='application/json', HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_two_reviewed_payments_keep_link_open_until_fully_paid(self):
        note = self._note(with_qr=True)
        self._submit(note)
        first = PaymentSubmission.objects.get()
        response = self.accept(first, '40.00', 'partial-proof')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['payment_submission']['received_amount_cny'], 40)
        self.assertEqual(self.accept(first, '40.00', 'partial-proof').status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.amount_cny, 120)  # 上传快照不是实际入账金额
        with self.assertRaises(PaymentSubmissionError):
            accept_payment_submission(submission_id=first.pk, sales_order_id=self.order.pk,
                operator=self.staff, business_date=date(2026, 9, 11),
                idempotency_key='partial-proof', amount_cny='41.00')
        page = self.client.get(f'/api/privnote/{note.token}/').json()['data']
        self.assertEqual(page['payment_flow']['status'], 'partial')
        self.assertEqual(page['remaining_amount_cny'], 80)
        self.assertIsNotNone(page['payment_methods'][0]['qr_url'])
        self.assertEqual(self._submit(note, key='next-proof').status_code, 201)
        second = PaymentSubmission.objects.get(status='pending')
        other = FundAccount.objects.create(name='实际到账 B', currency='CNY', creation_idempotency_key='proof-b')
        self.assertEqual(self.accept(second, '80.00', 'tail-proof', other).status_code, 200)
        self.assertEqual(PaymentSubmission.objects.filter(status='accepted').count(), 2)
        self.assertEqual(SalesReceipt.objects.count(), 2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        page = self.client.get(f'/api/privnote/{note.token}/').json()['data']
        self.assertEqual(page['payment_flow']['status'], 'accepted')
        self.assertEqual(page['remaining_amount_cny'], 0)

    def test_missing_amount_and_overpayment_do_not_accept_evidence(self):
        note = self._note()
        self._submit(note)
        proof = PaymentSubmission.objects.get()
        for amount in (None, '0', '120.01', '1.001'):
            response = self.accept(proof, amount, f'invalid-{amount}')
            self.assertEqual(response.status_code, 400, response.content)
        proof.refresh_from_db()
        self.assertEqual(proof.status, 'pending')
        self.assertEqual(SalesReceipt.objects.count(), 0)

    def test_anonymous_review_cannot_post_money(self):
        note = self._note()
        self._submit(note)
        proof = PaymentSubmission.objects.get()
        response = self.client.post(
            f'/api/sales/orders/{self.order.pk}/payment-submissions/{proof.pk}/accept/',
            data=json.dumps({'business_date': '2026-09-11', 'amount_cny': '40'}),
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='anonymous-review',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(SalesReceipt.objects.count(), 0)
