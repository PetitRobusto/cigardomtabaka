"""Payment evidence state transitions.

The public upload only creates a customer declaration.  The only path that
changes a SalesOrder to paid remains ``receive_sales_order_payment``.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounting.models import FundAccount
from accounting.services import _acquire_sqlite_writer_gate, _retry_sqlite_locked
from cigars.audit import AgentContext
from cigars.models import SalesOrder
from cigars.sales_accounting import receive_sales_order_payment
from privnote.models import PaymentAttachment, PaymentSubmission, Privnote
from privnote.storage import private_payment_storage


MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class PaymentSubmissionError(ValueError):
    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class PreparedAttachment:
    uploaded: UploadedFile
    sha256: str
    content_type: str
    size: int


def _payment_config(note: Privnote) -> dict:
    config = note.data_json if isinstance(note.data_json, dict) else {}
    if config.get("schema_version") != 2 or not isinstance(config.get("payment"), dict):
        raise PaymentSubmissionError("此收款单不支持上传付款凭证", status=409)
    return config["payment"]


def _validate_image(uploaded: UploadedFile) -> PreparedAttachment:
    if uploaded.content_type not in ALLOWED_CONTENT_TYPES:
        raise PaymentSubmissionError("凭证仅支持 JPG、PNG 或 WebP 图片")
    if not 0 < uploaded.size <= MAX_ATTACHMENT_BYTES:
        raise PaymentSubmissionError("每张凭证图片必须在 5MB 以内")
    try:
        from PIL import Image, UnidentifiedImageError

        image = Image.open(uploaded)
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise PaymentSubmissionError("上传文件不是有效图片")
    finally:
        uploaded.seek(0)

    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    return PreparedAttachment(
        uploaded=uploaded,
        sha256=digest.hexdigest(),
        content_type=uploaded.content_type,
        size=uploaded.size,
    )


def prepare_attachments(files: Iterable[UploadedFile]) -> list[PreparedAttachment]:
    values = list(files)
    if not values:
        raise PaymentSubmissionError("请至少上传一张付款凭证")
    if len(values) > MAX_ATTACHMENTS:
        raise PaymentSubmissionError("一次最多上传 5 张付款凭证")
    if sum(item.size for item in values) > MAX_TOTAL_BYTES:
        raise PaymentSubmissionError("付款凭证总大小不能超过 25MB")
    return [_validate_image(uploaded) for uploaded in values]


def _request_hash(prepared: list[PreparedAttachment]) -> str:
    value = "|".join(f"{item.sha256}:{item.size}:{item.content_type}" for item in prepared)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def serialize_submission(submission: PaymentSubmission, *, include_attachments: bool = False) -> dict:
    result = {
        "id": submission.id,
        "status": submission.status,
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "reviewed_at": submission.reviewed_at.isoformat() if submission.reviewed_at else None,
        "review_note": submission.review_note,
        "closed_reason": submission.closed_reason,
        "amount_cny": float(submission.amount_cny),
        "fund_account_id": submission.fund_account_id,
        "sales_receipt_id": submission.sales_receipt_id,
    }
    if include_attachments:
        result["attachments"] = [
            {
                "id": attachment.id,
                "name": attachment.original_name,
                "content_type": attachment.content_type,
                "size": attachment.size,
            }
            for attachment in submission.attachments.order_by("sort_order", "id")
        ]
    return result


def _save_attachment(prepared: PreparedAttachment) -> str:
    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }[prepared.content_type]
    name = f"payment-proofs/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}"
    return private_payment_storage.save(name, prepared.uploaded)


@_retry_sqlite_locked
def submit_payment_evidence(*, note: Privnote, files: Iterable[UploadedFile], idempotency_key: str) -> tuple[PaymentSubmission, bool]:
    """Create one pending declaration, or return the exact prior upload replay."""
    key = str(idempotency_key or "").strip()
    if not key or len(key) > 255:
        raise PaymentSubmissionError("提交凭证必须提供有效的幂等键")
    prepared = prepare_attachments(files)
    request_hash = _request_hash(prepared)
    saved_names: list[str] = []
    try:
        with transaction.atomic():
            _acquire_sqlite_writer_gate()
            # All payment mutations lock in the same order: order, link, then
            # submission.  This avoids a PostgreSQL deadlock with receipt or
            # cancellation paths that already own the order lock.
            order = SalesOrder.objects.select_for_update().get(pk=note.sales_order_id)
            locked_note = Privnote.objects.select_for_update().get(pk=note.pk, sales_order=order)
            if not locked_note.is_accessible:
                raise PaymentSubmissionError("收款链接已过期", status=410)
            config = _payment_config(locked_note)
            existing = PaymentSubmission.objects.select_for_update().filter(
                privnote=locked_note, idempotency_key=key,
            ).prefetch_related("attachments").first()
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise PaymentSubmissionError("幂等键已用于不同的付款凭证", status=409)
                return existing, True
            if (
                order.payment_status != SalesOrder.PaymentStatus.UNPAID
                or order.fulfillment_status not in (SalesOrder.FulfillmentStatus.CONFIRMED, SalesOrder.FulfillmentStatus.SHIPPED)
            ):
                raise PaymentSubmissionError("订单当前不能继续提交付款凭证", status=409)
            if PaymentSubmission.objects.filter(sales_order=order, status=PaymentSubmission.Status.PENDING).exists():
                raise PaymentSubmissionError("该订单已有待核实的付款凭证", status=409)
            try:
                account = FundAccount.objects.select_for_update().get(pk=config["fund_account_id"])
            except (KeyError, TypeError, ValueError, FundAccount.DoesNotExist):
                raise PaymentSubmissionError("收款单的入账账户无效", status=409)
            if not account.is_active or account.currency != FundAccount.Currency.CNY:
                raise PaymentSubmissionError("收款单的人民币入账账户当前不可用", status=409)
            try:
                submission = PaymentSubmission.objects.create(
                    sales_order=order,
                    privnote=locked_note,
                    amount_cny=order.amount_due_cny,
                    fund_account=account,
                    status=PaymentSubmission.Status.PENDING,
                    idempotency_key=key,
                    request_hash=request_hash,
                )
            except IntegrityError as exc:
                # A database constraint is the final backstop if this code is
                # ever invoked outside the standard writer gate.
                raise PaymentSubmissionError("付款凭证状态已变化，请刷新后重试", status=409) from exc
            for index, item in enumerate(prepared):
                storage_name = _save_attachment(item)
                saved_names.append(storage_name)
                PaymentAttachment.objects.create(
                    submission=submission,
                    file=storage_name,
                    original_name=os.path.basename(item.uploaded.name)[:255],
                    content_type=item.content_type,
                    size=item.size,
                    sha256=item.sha256,
                    sort_order=index,
                )
            from internal_notifications.business import schedule_payment_submission_notification
            schedule_payment_submission_notification(
                submission, order,
                [private_payment_storage.path(name) for name in saved_names],
            )
            return submission, False
    except Exception:
        for name in saved_names:
            private_payment_storage.delete(name)
        raise


@_retry_sqlite_locked
@transaction.atomic
def mark_submission_needs_more(*, submission_id: int, sales_order_id: int, operator, note: str) -> PaymentSubmission:
    reason = str(note or "").strip()
    if not reason:
        raise PaymentSubmissionError("请填写需要客户补充的内容")
    _acquire_sqlite_writer_gate()
    try:
        order = SalesOrder.objects.select_for_update().get(pk=sales_order_id)
        submission = PaymentSubmission.objects.select_for_update().select_related("sales_order").get(
            pk=submission_id, sales_order=order,
        )
    except (SalesOrder.DoesNotExist, PaymentSubmission.DoesNotExist, TypeError, ValueError) as exc:
        raise PaymentSubmissionError("付款凭证不存在或不属于该销售单", status=404) from exc
    if submission.status != PaymentSubmission.Status.PENDING:
        raise PaymentSubmissionError("该付款凭证当前不能要求补充", status=409)
    submission.status = PaymentSubmission.Status.NEEDS_MORE
    submission.reviewed_by = operator
    submission.reviewed_at = timezone.now()
    submission.review_note = reason
    submission.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    return submission


@_retry_sqlite_locked
@transaction.atomic
def accept_payment_submission(*, submission_id: int, sales_order_id: int, operator, business_date: date,
                              idempotency_key: str, agent_context: AgentContext | None = None) -> PaymentSubmission:
    _acquire_sqlite_writer_gate()
    try:
        order = SalesOrder.objects.select_for_update().get(pk=sales_order_id)
        submission = PaymentSubmission.objects.select_for_update().select_related(
            "sales_order", "fund_account", "sales_receipt__ledger_transaction",
        ).get(pk=submission_id, sales_order=order)
    except (SalesOrder.DoesNotExist, PaymentSubmission.DoesNotExist, TypeError, ValueError) as exc:
        raise PaymentSubmissionError("付款凭证不存在或不属于该销售单", status=404) from exc
    if submission.status == PaymentSubmission.Status.ACCEPTED:
        receipt = submission.sales_receipt
        replay_matches = (
            receipt is not None
            and submission.reviewed_by_id == getattr(operator, "pk", None)
            and submission.reviewed_at is not None
            and receipt.operator_id == getattr(operator, "pk", None)
            and receipt.business_date == business_date
            and receipt.ledger_transaction.idempotency_key == idempotency_key
        )
        if replay_matches:
            return submission
        raise PaymentSubmissionError("该付款凭证已由其他审核操作确认到账", status=409)
    if submission.status != PaymentSubmission.Status.PENDING:
        raise PaymentSubmissionError("该付款凭证当前不能确认到账", status=409)
    if submission.amount_cny != order.amount_due_cny:
        raise PaymentSubmissionError("订单应收金额已变化，不能确认该付款凭证", status=409)
    receipt = receive_sales_order_payment(
        order_id=order.id,
        amount_cny=submission.amount_cny,
        fund_account=submission.fund_account,
        business_date=business_date,
        operator=operator,
        idempotency_key=idempotency_key,
        payment_submission_id=submission.id,
        agent_context=agent_context or AgentContext(
            command_name='accept_payment_submission', idempotency_key=idempotency_key,
        ),
    )
    submission.status = PaymentSubmission.Status.ACCEPTED
    submission.reviewed_by = operator
    submission.reviewed_at = timezone.now()
    submission.sales_receipt = receipt
    submission.save(update_fields=["status", "reviewed_by", "reviewed_at", "sales_receipt"])
    return submission


@transaction.atomic
def close_open_submissions(*, order: SalesOrder, reason: str,
                           except_submission_id: int | None = None) -> list[int]:
    """Close unresolved declarations and return their IDs for the caller's audit event."""
    queryset = PaymentSubmission.objects.select_for_update().filter(
        sales_order=order,
        status__in=(PaymentSubmission.Status.PENDING, PaymentSubmission.Status.NEEDS_MORE),
    )
    if except_submission_id is not None:
        queryset = queryset.exclude(pk=except_submission_id)
    submission_ids = list(queryset.values_list('id', flat=True))
    if submission_ids:
        PaymentSubmission.objects.filter(pk__in=submission_ids).update(
            status=PaymentSubmission.Status.CLOSED,
            closed_reason=reason,
            closed_at=timezone.now(),
        )
    return submission_ids
