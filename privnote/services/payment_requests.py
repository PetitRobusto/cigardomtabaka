"""Creation of a customer payment request and its immutable display snapshot."""
from __future__ import annotations

import mimetypes
import uuid
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from accounting.models import FundAccount
from accounting.services import _acquire_sqlite_writer_gate, _retry_sqlite_locked
from cigars.models import SalesOrder
from privnote.helpers import serialize_payment_method
from privnote.models import PaymentMethod, PaymentSubmission, Privnote
from privnote.storage import private_payment_storage
from .payment_submissions import PaymentSubmissionError, _validate_image


ALLOWED_DURATIONS = {1, 6, 24, 72, 168, 720}
PAYMENT_TYPES = set(PaymentMethod.MethodType.values)


class PaymentRequestError(ValueError):
    def __init__(self, message: str, *, status: int = 400, existing_note: Privnote | None = None):
        super().__init__(message)
        self.status = status
        self.existing_note = existing_note


def _active_cny_account(raw_id) -> FundAccount:
    try:
        account = FundAccount.objects.select_for_update().get(pk=int(raw_id))
    except (FundAccount.DoesNotExist, TypeError, ValueError):
        raise PaymentRequestError('请选择有效的人民币入账账户')
    if not account.is_active or account.currency != FundAccount.Currency.CNY:
        raise PaymentRequestError('入账账户必须是启用中的人民币账户')
    return account


def _save_private_file(uploaded: UploadedFile, *, prefix: str) -> str:
    prepared = _validate_image(uploaded)
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[prepared.content_type]
    return private_payment_storage.save(
        f'{prefix}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}', prepared.uploaded,
    )


def _copy_saved_qr(payment_method: PaymentMethod) -> str:
    if not payment_method.qr_image:
        return ''
    payment_method.qr_image.open('rb')
    try:
        # Revalidate the copied image rather than trusting historical public media.
        copied = ContentFile(payment_method.qr_image.read(), name=payment_method.qr_image.name)
        copied.content_type = mimetypes.guess_type(payment_method.qr_image.name)[0] or 'application/octet-stream'
        return _save_private_file(copied, prefix='payment-qrs')
    finally:
        payment_method.qr_image.close()


def _clean_temporary_details(*, method_type: str, bank_name: str, card_number: str,
                             card_holder: str, account: str, qr_file: UploadedFile | None) -> tuple[dict, str]:
    if method_type not in PAYMENT_TYPES:
        raise PaymentRequestError('收款方式类型无效')
    display = {
        'method_type': method_type,
        'bank_name': bank_name.strip(),
        'card_number': card_number.strip(),
        'card_holder': card_holder.strip(),
        'account': account.strip(),
        'remark': '',
    }
    if method_type == PaymentMethod.MethodType.BANK_CARD:
        missing = [label for label, value in {
            '银行名': display['bank_name'], '卡号': display['card_number'], '户名': display['card_holder'],
        }.items() if not value]
        if missing:
            raise PaymentRequestError('银行卡收款方式请填写' + '、'.join(missing))
    elif not display['account'] and not qr_file:
        raise PaymentRequestError('微信或支付宝至少填写收款账号或上传二维码')
    return display, _save_private_file(qr_file, prefix='payment-qrs') if qr_file else ''


@_retry_sqlite_locked
@transaction.atomic
def create_payment_request(*, sales_order_id, duration_hours, password: str,
                           source: str, payment_method_id=None, fund_account_id=None,
                           method_type: str = '', bank_name: str = '', card_number: str = '',
                           card_holder: str = '', account: str = '', qr_file: UploadedFile | None = None,
                           remark: str = '', legacy_images=None, operator=None) -> Privnote:
    """Create one repeat-viewable payment link from either a saved or temporary method."""
    # This request competes with evidence submission, direct receipt and order
    # cancellation.  The order lock protects PostgreSQL; the common writer gate
    # gives SQLite the same whole-transaction serialisation.
    _acquire_sqlite_writer_gate()
    try:
        duration = int(duration_hours)
    except (TypeError, ValueError):
        raise PaymentRequestError('有效期必须是指定小时数')
    if duration not in ALLOWED_DURATIONS:
        raise PaymentRequestError('有效期只能为 1、6、24、72、168 或 720 小时')
    try:
        order = SalesOrder.objects.select_for_update().get(pk=int(sales_order_id))
    except (SalesOrder.DoesNotExist, TypeError, ValueError):
        raise PaymentRequestError('销售单不存在')
    if (
        order.payment_status != SalesOrder.PaymentStatus.UNPAID
        or order.fulfillment_status not in (SalesOrder.FulfillmentStatus.CONFIRMED, SalesOrder.FulfillmentStatus.SHIPPED)
    ):
        raise PaymentRequestError('只有已确认或已出库且未收款的销售单才能创建收款单')
    active = next((note for note in Privnote.objects.select_for_update().filter(
        sales_order=order, note_type=Privnote.NoteType.PAYMENT,
    ).order_by('-created_at', '-id') if note.is_accessible), None)
    if active:
        raise PaymentRequestError('该订单已有有效收款单', status=409, existing_note=active)
    if PaymentSubmission.objects.select_for_update().filter(sales_order=order, status=PaymentSubmission.Status.PENDING).exists():
        raise PaymentRequestError('该订单已有待核实的付款凭证，不能生成新收款单', status=409)

    source = str(source or 'saved').strip()
    saved_file_name = ''
    try:
        if source == 'saved':
            try:
                payment_method = PaymentMethod.objects.select_related('fund_account').get(pk=int(payment_method_id))
            except (PaymentMethod.DoesNotExist, TypeError, ValueError):
                raise PaymentRequestError('请选择常用收款方式')
            if (
                not payment_method.is_active or not payment_method.fund_account_id
                or not payment_method.fund_account.is_active
                or payment_method.fund_account.currency != FundAccount.Currency.CNY
            ):
                raise PaymentRequestError('常用收款方式未启用或未绑定有效人民币账户')
            display = serialize_payment_method(payment_method, include_label=False)
            display.pop('qr_url', None)
            saved_file_name = _copy_saved_qr(payment_method)
            internal_account = payment_method.fund_account
            display['remark'] = payment_method.remark
        elif source == 'temporary':
            internal_account = _active_cny_account(fund_account_id)
            display, saved_file_name = _clean_temporary_details(
                method_type=method_type, bank_name=bank_name, card_number=card_number,
                card_holder=card_holder, account=account, qr_file=qr_file,
            )
        else:
            raise PaymentRequestError('收款方式来源无效')
        data = {
            'schema_version': 2,
            # Kept only for historical staff-side readers; v2 code always uses
            # the explicit nested payment snapshot below.
            'payment_method_id': payment_method.id if source == 'saved' else None,
            'remark': str(remark or '').strip(),
            'images': legacy_images if isinstance(legacy_images, list) else [],
            'payment': {
                'source': source,
                'display': display,
                'fund_account_id': internal_account.id,
                'fund_account_name': internal_account.name,
                'qr_private_name': saved_file_name,
                'remark': str(remark or '').strip(),
            },
        }
        note = Privnote(
            token=uuid.uuid4().hex[:12],
            note_type=Privnote.NoteType.PAYMENT,
            title=f'收款单 · {order.order_number}',
            data_json=data,
            sales_order=order,
            created_by=operator,
            # Payment links intentionally remain accessible until their expiry.
            burn_after_read=False,
            max_views=0,
            expires_at=timezone.now() + timedelta(hours=duration),
        )
        if password:
            note.set_password(password)
        note.save()
        return note
    except Exception:
        if saved_file_name:
            private_payment_storage.delete(saved_file_name)
        raise
