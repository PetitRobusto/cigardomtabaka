"""Apply a fixed 60-product/20-brand release with preview CAS and audit logs."""

import json
from pathlib import Path
import subprocess

from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from cigars.models import Brand, Cigar
from storefront.content_release import COPY_FIELDS, IDENTITY_FIELDS, LOCALES, SPEC_FIELDS, read_release
from storefront.management.commands.prepare_cohiba_content import Command as DevelopmentGuard
from storefront.management.commands.publish_cohiba_russian_copy import Command as CopyOptions, digest
from storefront.models import ProductListing, StoreTranslation


SOURCE = 'codex-seo18-19'
SCOPE = 'public-catalog-trilingual-copy-v1'


def snapshot(row):
    values = {field.attname: getattr(row, field.attname) for field in row._meta.concrete_fields}
    # Model image descriptors are not JSON values; snapshots must not open media.
    for field in row._meta.concrete_fields:
        if field.get_internal_type() in ('FileField', 'ImageField'):
            values[field.attname] = str(values[field.attname])
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


class Command(CopyOptions):
    help = '预览固定 60 商品/20 品牌三语资料及批准规格；不修改品名、价格、库存和发布状态。'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--confirm-production', action='store_true')

    def _guard_apply(self, options):
        if settings.DEBUG:
            if options['confirm_production']:
                raise CommandError('生产确认不能用于 DEBUG 开发数据库。')
            DevelopmentGuard()._guard_apply()
        else:
            configured_path = Path(str(connection.settings_dict.get('NAME') or '')).resolve()
            production_path = (Path(settings.BASE_DIR) / 'cigars.db').resolve()
            if (not options['confirm_production'] or connection.vendor != 'sqlite'
                    or configured_path != production_path or not production_path.is_file()):
                raise CommandError('生产写入要求 --confirm-production、DEBUG=False 和实际 cigars.db。')

    def _guard_commit_sha(self, options):
        if settings.DEBUG:
            return
        try:
            result = subprocess.run(
                ['git', '-C', str(settings.BASE_DIR), 'rev-parse', 'HEAD'],
                check=True, capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise CommandError('无法核验当前部署提交 SHA；生产写入拒绝。') from exc
        if result.stdout.strip() != options['commit_sha']:
            raise CommandError('--commit-sha 与当前部署代码不一致；生产写入拒绝。')

    def _prepare(self):
        scope, products, brands = read_release()
        updates, reports, identities = [], [], []
        expected_ids = {entry['id'] for entry in scope['products']}
        public_ids = set(ProductListing.objects.select_for_update().filter(
            published=True, withdrawn=False, cigar__deleted_at__isnull=True).values_list('cigar_id', flat=True))
        if public_ids != expected_ids:
            raise CommandError('公开商品集合已改变，请重新审核完整范围；整批停止。')

        def prepare_row(row, desired, fields, label):
            before = snapshot(row)
            changed_fields = [field for field in fields if getattr(row, field) != desired[field]]
            for field in changed_fields:
                setattr(row, field, desired[field])
            row.full_clean()
            reports.append({'kind': row._meta.label, 'key': label,
                            'action': 'update' if changed_fields else 'unchanged',
                            'fields': changed_fields, 'before': before, 'after': snapshot(row)})
            updates.append((row, changed_fields))

        def translations(kind, key, cigar_id, entry):
            for locale in LOCALES:
                row = StoreTranslation.objects.select_for_update().filter(kind=kind, key=key, locale=locale).first()
                if row is None or not row.published or row.cigar_id != cigar_id:
                    raise CommandError(f'{kind}/{key}/{locale} 缺失、草稿或关联错误；整批停止。')
                desired = entry['translations'][locale]
                if entry['decision'] == 'preserve' and any(getattr(row, f) != desired[f] for f in COPY_FIELDS):
                    raise CommandError(f'{kind}/{key}/{locale} 保留资料发生变化，需重新核对。')
                prepare_row(row, desired, COPY_FIELDS, f'{kind}/{key}/{locale}')

        for expected in scope['brands']:
            brand = Brand.objects.select_for_update().filter(slug=expected['slug'], english_name=expected['english_name']).first()
            if brand is None:
                raise CommandError(f"品牌 {expected['slug']} 身份不一致。")
            identities.append(snapshot(brand))
            translations('brand', brand.slug, None, brands[brand.slug])
        for expected in scope['products']:
            pk = expected['id']
            cigar = Cigar.objects.select_for_update().filter(pk=pk, deleted_at__isnull=True).first()
            if cigar is None or any(getattr(cigar, f) != expected[f] for f in IDENTITY_FIELDS):
                raise CommandError(f'商品 {pk} 身份或发行版本不一致。')
            old = expected['expected_specs']
            corrections = scope['spec_corrections'].get(str(pk), {})
            desired = {**old, **corrections}
            current = {f: getattr(cigar, f) for f in SPEC_FIELDS}
            if current not in (old, desired):
                raise CommandError(f'商品 {pk} 规格已经变动，需重新审核；整批停止。')
            prepare_row(cigar, desired, tuple(corrections), f'product/{pk}/specs')
            translations('product', str(pk), pk, products[pk])
        content_digest = digest({'scope': scope, 'products': products, 'brands': brands})
        expected_digest = digest({'scope': SCOPE, 'identities': identities,
                                  'before': [r['before'] for r in reports], 'content_digest': content_digest})
        return updates, reports, expected_digest, content_digest

    def _operation_used(self, options, actor, content_digest):
        marker = json.dumps({'operation_id': options['operation_id']})[1:-1]
        used = False
        for log in LogEntry.objects.filter(action_flag=CHANGE, change_message__contains=marker):
            try:
                messages = json.loads(log.change_message)
            except (ValueError, TypeError):
                continue
            for message in messages if isinstance(messages, list) else []:
                meta = message.get('seo_release', {}) if isinstance(message, dict) else {}
                if not isinstance(meta, dict) or meta.get('operation_id') != options['operation_id']:
                    continue
                used = True
                if (meta.get('source') != SOURCE or meta.get('scope') != SCOPE
                        or log.user_id != actor.pk or meta.get('content_digest') != content_digest
                        or meta.get('commit_sha') != options['commit_sha']):
                    raise CommandError('operation-id 已用于不同操作；整批停止。')
        return used

    def handle(self, *args, **options):
        self._validate_options(options)
        if options['apply']:
            self._guard_apply(options)
            self._guard_commit_sha(options)
        try:
            with transaction.atomic():
                actor = None
                if options['apply']:
                    actor = get_user_model().objects.select_for_update().filter(
                        username=options['actor'], is_active=True, is_staff=True).first()
                    if actor is None:
                        raise CommandError('操作者必须为现有 active staff 用户。')
                updates, reports, expected_digest, content_digest = self._prepare()
                changed_rows = sum(bool(fields) for _, fields in updates)
                if options['apply']:
                    used = self._operation_used(options, actor, content_digest)
                    if used and changed_rows:
                        raise CommandError('该 operation-id 已执行，但资料随后变化；重新预览并使用新 ID。')
                    if not used and options['expected_digest'] != expected_digest:
                        raise CommandError('expected-digest 不匹配；资料或清单已改变，整批停止。')
                    for (row, fields), report in zip(updates, reports):
                        if not fields:
                            continue
                        row.save(update_fields=[*fields, *(['updated_at'] if isinstance(row, StoreTranslation) else [])])
                        report['after'] = snapshot(row)
                        metadata = {'source': SOURCE, 'scope': SCOPE, 'operation_id': options['operation_id'],
                                    'commit_sha': options['commit_sha'], 'business_date': timezone.localdate().isoformat(),
                                    'content_digest': content_digest, 'expected_digest': expected_digest,
                                    'before': report['before'], 'after': report['after']}
                        LogEntry.objects.create(user_id=actor.pk, content_type=ContentType.objects.get_for_model(row),
                                                object_id=str(row.pk), object_repr=str(row), action_flag=CHANGE,
                                                change_message=json.dumps([{'changed': {'fields': fields},
                                                                           'seo_release': metadata}], ensure_ascii=False))
        except (ValidationError, DatabaseError, OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise CommandError(f'全目录资料校验/发布失败，事务未写入：{exc}') from exc
        self.stdout.write(json.dumps({'schema_version': 1, 'scope': SCOPE,
                                      'mode': 'apply' if options['apply'] else 'dry-run',
                                      'changed_rows': changed_rows, 'expected_digest': expected_digest,
                                      'content_digest': content_digest, 'records': reports}, ensure_ascii=False, indent=2))
