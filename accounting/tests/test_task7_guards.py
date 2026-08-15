from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounting.dividend_actions import DividendActionError, create_dividend_draft
from accounting.expense_actions import ExpenseActionError, record_expense
from accounting.guards import Day1IncompleteError
from accounting.models import FundAccount, LedgerTransaction
from accounting.purchase_actions import PurchaseActionError, create_purchase_order
from accounting.services import exchange_to_rub, transfer_same_currency
from cigars.models import Brand, Cigar, User


class Task7ServiceGuardTest(TestCase):
    day = date(2026, 8, 14)

    def setUp(self):
        self.operator = User.objects.create_user(
            'task7-guard-operator', password='pass', is_staff=True,
        )
        self.cny = FundAccount.objects.create(
            name='Task7 guard CNY', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='task7-guard-cny',
        )
        self.rub = FundAccount.objects.create(
            name='Task7 guard RUB', currency=FundAccount.Currency.RUB,
            creation_idempotency_key='task7-guard-rub',
        )
        brand = Brand.objects.create(english_name='Task7 Guard Brand', name='Task7 Guard Brand')
        self.cigar = Cigar.objects.create(
            brand=brand.english_name, english_name='Task7 Guard Cigar', name='Task7 Guard Cigar',
        )

    def test_formal_services_reject_before_day1(self):
        with self.assertRaises(Day1IncompleteError) as exchange:
            exchange_to_rub(
                self.cny, self.rub, Decimal('1.00'), Decimal('12.00'),
                self.day, self.operator, 'task7-guard-exchange',
            )
        self.assertEqual(exchange.exception.code, 'day1_incomplete')
        with self.assertRaises(Day1IncompleteError) as transfer:
            transfer_same_currency(
                self.cny, self.rub, Decimal('1.00'), self.day,
                self.operator, 'task7-guard-transfer',
            )
        self.assertEqual(transfer.exception.code, 'day1_incomplete')


        with self.assertRaises(PurchaseActionError) as purchase:
            create_purchase_order(
                supplier_id=1,
                items=[{
                    'cigar_id': self.cigar.pk, 'box_size': 25, 'box_quantity': 1,
                    'unit_price_rub_per_box': '100.00',
                }],
                business_date=self.day,
                operator=self.operator, idempotency_key='task7-guard-purchase',
            )
        self.assertEqual(purchase.exception.code, 'day1_incomplete')

        with self.assertRaises(ExpenseActionError) as expense:
            record_expense(
                category='salary', amount='1.00', fund_account_id=999,
                business_date=self.day, operator=self.operator,
                idempotency_key='task7-guard-expense',
            )
        self.assertEqual(expense.exception.code, 'day1_incomplete')

        with self.assertRaises(DividendActionError) as dividend:
            create_dividend_draft(
                total_cny='1.00', business_date=self.day,
                operator=self.operator, idempotency_key='task7-guard-dividend',
            )
        self.assertEqual(dividend.exception.code, 'day1_incomplete')
        self.assertEqual(LedgerTransaction.objects.count(), 0)
