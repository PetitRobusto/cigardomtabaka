"""收款方式配置命令。"""

from __future__ import annotations

import hashlib
import json

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError
from django.db import IntegrityError, transaction

from accounting.models import FundAccount
from cigars.models import User
from privnote.helpers import serialize_payment_method
from privnote.models import PaymentMethod, PaymentMethodAudit


class PaymentMethodActionError(ValueError):
    """收款方式配置动作输入或状态冲突。"""

    def __init__(self, message, *, status=400, details=None):
        super().__init__(message)
        self.status = status
        self.details = details or {}


def _idempotency_key(request):
    key = str(request.headers.get('Idempotency-Key', '')).strip()
    if not key or len(key) > 255:
        raise PaymentMethodActionError('写请求必须提供有效的 Idempotency-Key')
    return key


def _operator(request):
    if request.user.is_authenticated and request.user.is_staff:
        return request.user
    telegram_id = request.headers.get('X-Telegram-ID', '').strip()
    if telegram_id:
        try:
            return User.objects.get(telegram_id=telegram_id, is_staff=True)
        except User.DoesNotExist:
            pass
    raise PaymentMethodActionError('必须提供有效的工作人员操作人', status=403)


def _agent_fields(request):
    return {
        'agent_name': request.headers.get('X-Agent-Name', 'web').strip() or 'web',
        'agent_run_id': request.headers.get('X-Agent-Run-ID', '').strip(),
        'agent_request_id': request.headers.get('X-Agent-Request-ID', '').strip(),
        'command_name': request.headers.get('X-Command-Name', 'privnote.payment_method').strip() or 'privnote.payment_method',
    }


def _file_fingerprint(uploaded_file):
    if uploaded_file is None:
        return None
    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return {
        'name': uploaded_file.name,
        'size': uploaded_file.size,
        'sha256': digest.hexdigest(),
    }


def _validate_image(uploaded_file):
    if uploaded_file is None:
        return
    if uploaded_file.size > 5 * 1024 * 1024:
        raise PaymentMethodActionError('二维码图片不能超过 5MB')
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.verify()
        if image.format not in {'JPEG', 'PNG', 'WEBP'}:
            raise PaymentMethodActionError('二维码只支持 JPG、PNG 或 WebP 图片')
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PaymentMethodActionError('二维码文件不是有效图片') from exc
    finally:
        uploaded_file.seek(0)


def _parse_sort_order(raw):
    try:
        value = int(raw or 0)
    except (TypeError, ValueError) as exc:
        raise PaymentMethodActionError('排序必须是整数') from exc
    if value < 0:
        raise PaymentMethodActionError('排序不能为负数')
    return value


def _request_hash(payload, uploaded_file=None):
    value = {
        'payload': payload,
        'file': _file_fingerprint(uploaded_file),
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _existing_action(key, request_hash, action):
    existing = PaymentMethodAudit.objects.select_related('payment_method').filter(idempotency_key=key).first()
    if existing is None:
        return None
    if existing.request_hash != request_hash or existing.action != action:
        raise PaymentMethodActionError('幂等键已用于不同的收款方式操作', status=409)
    return existing.response_body


def _response(method):
    return {'payment_method': serialize_payment_method(method, include_fund_account=True, include_management=True)}


def _create_audit(*, method, action, operator, key, request_hash, response, request):
    agent = _agent_fields(request)
    return PaymentMethodAudit.objects.create(
        payment_method=method,
        action=action,
        operator=operator,
        idempotency_key=key,
        request_hash=request_hash,
        response_body=response,
        snapshot=serialize_payment_method(method, include_fund_account=True, include_management=True),
        **agent,
    )


def create_payment_method(*, request, payload, uploaded_file=None):
    operator = _operator(request)
    _validate_image(uploaded_file)
    key = _idempotency_key(request)
    request_hash = _request_hash(payload, uploaded_file)
    with transaction.atomic():
        existing = _existing_action(key, request_hash, PaymentMethodAudit.Action.CREATE)
        if existing is not None:
            return existing

        fund_account_id = payload.get('fund_account_id')
        try:
            fund_account_id = int(fund_account_id)
        except (TypeError, ValueError):
            raise PaymentMethodActionError('必须选择有效的 CNY 资金账户')
        if not FundAccount.objects.filter(
            pk=fund_account_id, is_active=True, currency=FundAccount.Currency.CNY,
        ).exists():
            raise PaymentMethodActionError('只能绑定启用中的人民币资金账户')

        method = PaymentMethod(
            method_type=str(payload.get('method_type') or '').strip(),
            label=str(payload.get('label') or '').strip(),
            bank_name=str(payload.get('bank_name') or '').strip(),
            card_number=str(payload.get('card_number') or '').strip(),
            card_holder=str(payload.get('card_holder') or '').strip(),
            account=str(payload.get('account') or '').strip(),
            remark=str(payload.get('remark') or '').strip(),
            sort_order=_parse_sort_order(payload.get('sort_order')),
            fund_account_id=fund_account_id,
            is_active=True,
        )
        if uploaded_file is not None:
            method.qr_image = uploaded_file
        try:
            method.save()
        except (ValidationError, ValueError) as exc:
            details = getattr(exc, 'message_dict', None) or {}
            raise PaymentMethodActionError('收款方式信息不完整或无效', details=details) from exc

        response = _response(method)
        try:
            _create_audit(
                method=method, action=PaymentMethodAudit.Action.CREATE, operator=operator,
                key=key, request_hash=request_hash, response=response, request=request,
            )
        except IntegrityError:
            existing = _existing_action(key, request_hash, PaymentMethodAudit.Action.CREATE)
            if existing is not None:
                return existing
            raise
        return response


def set_payment_method_active(*, request, method_id, active):
    operator = _operator(request)
    key = _idempotency_key(request)
    action = PaymentMethodAudit.Action.ACTIVATE if active else PaymentMethodAudit.Action.DEACTIVATE
    payload = {'method_id': method_id, 'active': active}
    request_hash = _request_hash(payload)
    with transaction.atomic():
        existing = _existing_action(key, request_hash, action)
        if existing is not None:
            return existing
        try:
            method = PaymentMethod.objects.select_for_update().get(pk=method_id)
        except PaymentMethod.DoesNotExist as exc:
            raise PaymentMethodActionError('收款方式不存在', status=404) from exc

        if method.is_active != active:
            method.is_active = active
            try:
                method.save(update_fields=['is_active'])
            except ValidationError as exc:
                raise PaymentMethodActionError('收款方式当前不能启用', details=getattr(exc, 'message_dict', {})) from exc

        response = _response(method)
        try:
            _create_audit(
                method=method, action=action, operator=operator,
                key=key, request_hash=request_hash, response=response, request=request,
            )
        except IntegrityError:
            existing = _existing_action(key, request_hash, action)
            if existing is not None:
                return existing
            raise
        return response
