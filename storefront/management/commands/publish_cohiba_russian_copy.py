"""Publish only the five reviewed Russian Cohiba translations after preview."""

import hashlib
import json
import re

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction
from django.utils import timezone

from cigars.models import Brand, Cigar
from storefront.management.commands.prepare_cohiba_content import COPY_FIELDS, read_content
from storefront.models import StoreTranslation


SOURCE = 'codex-seo05'
SCOPE = 'cohiba-russian-copy-v1'
PRODUCT_IDS = (102, 103, 97, 98)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def snapshot(row):
    result = {field.attname: getattr(row, field.attname) for field in row._meta.concrete_fields}
    result['updated_at'] = row.updated_at.isoformat()
    return result


class Command(BaseCommand):
    help = '预览或发布固定五条已审核俄语 Cohiba 资料；不改价格、库存或发布状态。'
    # Subclasses may define another reviewed, fixed Cohiba release scope. These
    # are deliberately not command-line arguments or user-selectable targets.
    _locales = ('ru',)
    _scope = SCOPE
    _label = '俄语'
    _note = '仅更新固定五条已发布俄语资料的文案；价格、库存、身份与发布状态保持原值。'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--expected-digest', default='', help='必须与已审核 dry-run 的 expected_digest 一致。')
        parser.add_argument('--actor', default='', help='正式操作的现有 active staff 用户名。')
        parser.add_argument('--operation-id', default='', help='本次操作的稳定 ID，1–120 个 ASCII 字母、数字、点、下划线或连字符。')
        parser.add_argument('--commit-sha', default='', help='经 CI 验证并部署的准确 40 位小写提交 SHA。')

    def _validate_options(self, options):
        required = ('expected_digest', 'actor', 'operation_id', 'commit_sha')
        if options['apply'] and any(not options[name] for name in required):
            raise CommandError('--apply 必须同时提供 --expected-digest、--actor、--operation-id 和 --commit-sha。')
        for name, pattern in [('expected_digest', r'[0-9a-f]{64}'),
                              ('operation_id', r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}'),
                              ('commit_sha', r'[0-9a-f]{40}')]:
            if options[name] and not re.fullmatch(pattern, options[name]):
                raise CommandError(f'--{name.replace("_", "-")} 格式不正确。')
        actor = options['actor']
        if actor and (len(actor) > 150 or actor != actor.strip() or any(ord(c) < 32 for c in actor)):
            raise CommandError('--actor 必须为有效的现有用户名。')

    def _prepare(self):
        content = read_content()
        brand = Brand.objects.select_for_update().filter(english_name='Cohiba', slug='cohiba').first()
        if brand is None:
            raise CommandError('缺少 Cohiba/cohiba 正式品牌记录；整批停止。')
        products = {entry['id']: entry for entry in content['products']}
        if set(products) != set(PRODUCT_IDS):
            raise CommandError('清单必须恰好包含固定四款商品。')
        identities = [{'kind': 'brand', 'id': brand.pk, 'english_name': brand.english_name, 'slug': brand.slug}]
        entries = [('brand', 'cohiba', None, content['brand']['translations'])]
        for pk in PRODUCT_IDS:
            expected = products[pk]
            cigar = Cigar.objects.select_for_update().filter(pk=pk, deleted_at__isnull=True).first()
            fields = ('english_name', 'length', 'ring_gauge')
            if (cigar is None or cigar.brand != 'Cohiba'
                    or any(getattr(cigar, field) != expected[field] for field in fields)
                    or (cigar.release_type or '') != expected['release_type']
                    or (cigar.release_name or '') != expected['release_name']):
                raise CommandError(f'商品 id={pk} 身份、尺寸或版本不符；整批停止。')
            identities.append({'kind': 'product', 'id': pk, 'brand': cigar.brand,
                               **{field: getattr(cigar, field) for field in fields},
                               'release_type': cigar.release_type, 'release_name': cigar.release_name})
            entries.append(('product', str(pk), pk, expected['translations']))
        targets = [(kind, key, cigar_id, locale, translations[locale])
                   for kind, key, cigar_id, translations in entries for locale in self._locales]
        rows, reports = [], []
        for kind, key, cigar_id, locale, desired in targets:
            row = StoreTranslation.objects.select_for_update().filter(kind=kind, key=key, locale=locale).first()
            if row is None or not row.published or row.cigar_id != cigar_id:
                raise CommandError(f'{kind}/{key}/{locale} 缺失、未发布或关联不符；整批停止。')
            before = snapshot(row)
            changed = any(getattr(row, field) != desired[field] for field in COPY_FIELDS)
            for field in COPY_FIELDS:
                setattr(row, field, desired[field])
            row.full_clean()
            reports.append({'kind': kind, 'key': key, 'locale': locale, 'id': row.pk,
                            'action': 'update' if changed else 'unchanged',
                            'before': before, 'after': snapshot(row)})
            rows.append((row, changed))
        content_digest = digest([{'kind': kind, 'key': key, 'locale': locale, 'copy': desired}
                                 for kind, key, _, locale, desired in targets])
        expected_digest = digest({'scope': self._scope, 'identities': identities,
                                  'before': [item['before'] for item in reports],
                                  'content_digest': content_digest})
        return rows, reports, expected_digest, content_digest

    def _check_operation(self, options, actor, content_digest, changed_rows):
        marker = json.dumps({'operation_id': options['operation_id']})[1:-1]
        used = False
        for log in LogEntry.objects.filter(action_flag=CHANGE, change_message__contains=marker):
            try:
                messages = json.loads(log.change_message)
            except (ValueError, TypeError):
                continue
            for message in messages if isinstance(messages, list) else []:
                metadata = message.get('seo_release', {}) if isinstance(message, dict) else {}
                if not isinstance(metadata, dict):
                    continue
                if metadata.get('source') != SOURCE or metadata.get('operation_id') != options['operation_id']:
                    continue
                used = True
                if (metadata.get('scope') != self._scope
                        or log.user_id != actor.pk or metadata.get('content_digest') != content_digest
                        or metadata.get('commit_sha') != options['commit_sha']):
                    raise CommandError('operation-id 已用于不同的范围、操作者、内容或提交；整批停止。')
        if used and changed_rows:
            raise CommandError('该 operation-id 已执行，但资料随后发生变化；请重新预览并使用新的操作 ID。')

    def handle(self, *args, **options):
        self._validate_options(options)
        try:
            with transaction.atomic():
                actor = None
                if options['apply']:
                    actor = get_user_model().objects.select_for_update().filter(
                        username=options['actor'], is_active=True, is_staff=True).first()
                    if actor is None:
                        raise CommandError('操作者必须是现有 active staff 用户；整批停止。')
                rows, reports, expected_digest, content_digest = self._prepare()
                changed_rows = sum(changed for _, changed in rows)
                if options['apply']:
                    self._check_operation(options, actor, content_digest, changed_rows)
                    if changed_rows and options['expected_digest'] != expected_digest:
                        raise CommandError('资料已偏离已审核的预览（expected-digest 不匹配）；整批停止，请重新预览。')
                    if changed_rows:
                        content_type = ContentType.objects.get_for_model(StoreTranslation)
                        for (row, changed), report in zip(rows, reports):
                            if not changed:
                                continue
                            row.save(update_fields=[*COPY_FIELDS, 'updated_at'])
                            report['after'] = snapshot(row)
                            metadata = {'source': SOURCE, 'scope': self._scope,
                                        'operation_id': options['operation_id'],
                                        'commit_sha': options['commit_sha'],
                                        'business_date': timezone.localdate().isoformat(),
                                        'content_digest': content_digest,
                                        'expected_digest': expected_digest,
                                        'before': report['before'], 'after': report['after']}
                            LogEntry.objects.create(
                                user_id=actor.pk, content_type=content_type, object_id=str(row.pk),
                                object_repr=str(row), action_flag=CHANGE,
                                change_message=json.dumps([{'changed': {'fields': list(COPY_FIELDS)},
                                                            'seo_release': metadata}], ensure_ascii=False))
        except (ValidationError, DatabaseError, OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise CommandError(f'Cohiba {self._label}资料发布失败，事务未写入：{exc}') from exc
        self.stdout.write(json.dumps({'schema_version': 1, 'mode': 'apply' if options['apply'] else 'dry-run',
                                      'scope': self._scope, 'source': SOURCE, 'changed_rows': changed_rows,
                                      'expected_digest': expected_digest, 'content_digest': content_digest,
                                      'translations': reports,
                                      'note': self._note},
                                     ensure_ascii=False, indent=2))
