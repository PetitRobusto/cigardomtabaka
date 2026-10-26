"""Publish the two reviewed Cohiba Magicos images after an explicit preview."""

import hashlib
import json
import re
from pathlib import Path

from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction
from django.db.models import Q
from django.db.models.fields.files import FieldFile
from django.utils import timezone

from cigars.models import Cigar, CigarImage
from storefront.management.commands.apply_storefront_images import _normalize_assets


SOURCE = 'codex-seo13'
SCOPE = 'magicos-images-v1'
MANIFEST = Path(settings.BASE_DIR) / 'docs/data/storefront-images-20261026-magicos.json'
IDENTITY = {'cigar_id': 103, 'brand': 'Cohiba', 'english_name': 'Magicos',
            'length': 115, 'ring_gauge': 52, 'release_type': '', 'release_name': ''}
ASSETS = {
    ('single', None): ('storefront/generated-v4/products/103-single-detail.webp',
                       '7095d0a9dcbabec39ec981f61633ca8603771ad26bf3124e145c7cdcec2637f0',
                       'storefront/generated-v4/products/103-single-list.webp',
                       'bd374b12ce27c5111fa38795796c132d49b960c59d322afc39cdb13af33dc8a4'),
    ('box', 10): ('storefront/generated-v4/products/103-box-10-detail.webp',
                  'e85c93a16288be7aa9c1d8277d4b51a452a1c9d5f12796e42a24d6c5fff0d2ce',
                  'storefront/generated-v4/products/103-box-10-list.webp',
                  '3d23a1ba2eae52c413271b83b8c7f5695cf7670b2ace76945b30ffc415f9e751'),
}


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _snapshot(row):
    # Read the model's raw FK/FileField storage values; descriptors return related
    # objects and FieldFile wrappers that are not stable JSON snapshot values.
    values = {field.attname: row.__dict__.get(field.attname) for field in row._meta.concrete_fields}
    return {key: (value.name if isinstance(value, FieldFile) else
                  value.isoformat() if hasattr(value, 'isoformat') else value)
            for key, value in values.items()}


def _read_fixed_manifest(path):
    try:
        raw_bytes = path.read_bytes()
        payload = json.loads(raw_bytes.decode('utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CommandError(f'无法读取固定图片清单：{exc}') from exc
    assets = payload.get('product_assets', payload.get('assets')) if isinstance(payload, dict) else None
    if not isinstance(assets, list) or not assets:
        raise CommandError('固定图片清单必须包含非空 product_assets 或 assets 数组。')
    return assets, hashlib.sha256(raw_bytes).hexdigest()


class Command(BaseCommand):
    help = '预览或发布固定的两张 Cohiba Magicos 商品图片；保留其他图片关联。'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--confirm-production', action='store_true')
        parser.add_argument('--expected-digest', default='')
        parser.add_argument('--actor', default='')
        parser.add_argument('--operation-id', default='')
        parser.add_argument('--commit-sha', default='')

    def _validate_options(self, options):
        if options['apply'] and not options['confirm_production']:
            raise CommandError('--apply 必须同时提供 --confirm-production。')
        required = ('expected_digest', 'actor', 'operation_id', 'commit_sha')
        if options['apply'] and any(not options[name] for name in required):
            raise CommandError('--apply 必须提供 --expected-digest、--actor、--operation-id 和 --commit-sha。')
        for name, pattern in [('expected_digest', r'[0-9a-f]{64}'),
                              ('operation_id', r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}'),
                              ('commit_sha', r'[0-9a-f]{40}')]:
            if options[name] and not re.fullmatch(pattern, options[name]):
                raise CommandError(f'--{name.replace("_", "-")} 格式不正确。')
        actor = options['actor']
        if actor and (len(actor) > 150 or actor != actor.strip() or any(ord(c) < 32 for c in actor)):
            raise CommandError('--actor 必须为有效的现有用户名。')

    def _prepare(self):
        try:
            raw, manifest_hash = _read_fixed_manifest(MANIFEST)
            entries = _normalize_assets(raw, settings.MEDIA_ROOT)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(f'固定图片清单无效：{exc}') from exc
        expected_slots = set(ASSETS)
        actual_slots = {(entry['kind'], entry['box_size']) for entry in entries}
        if len(entries) != 2 or actual_slots != expected_slots:
            raise CommandError('清单必须恰好包含单支和 10 支盒两个固定图片槽位。')
        for entry in entries:
            slot = (entry['kind'], entry['box_size'])
            paths = ASSETS[slot]
            if (entry['cigar_id'] != IDENTITY['cigar_id'] or entry['brand'] != IDENTITY['brand']
                    or entry['english_name'] != IDENTITY['english_name']
                    or entry['release_type'] != '' or entry['release_name'] != ''
                    or (entry['image'], entry['image_file'].is_file() and _sha256(entry['image_file']),
                        entry['thumbnail'], entry['thumbnail_file'].is_file() and _sha256(entry['thumbnail_file'])) != paths):
                raise CommandError('清单商品身份、图片路径或 SHA-256 偏离固定审核值。')
        cigar = Cigar.objects.select_for_update().filter(pk=103, deleted_at__isnull=True).first()
        if cigar is None or any(getattr(cigar, key) != value for key, value in IDENTITY.items() if key != 'cigar_id'):
            raise CommandError('商品 #103 身份或规格与固定审核值不符。')
        identity = _snapshot(cigar)
        images = list(CigarImage.objects.select_for_update().filter(cigar_id=103).order_by('pk'))
        before_images = [_snapshot(row) for row in images]
        desired = []
        for entry in entries:
            desired.append({'image': entry['image'], 'thumbnail': entry['thumbnail'],
                            'image_type': entry['model_type'], 'box_size': entry['box_size'],
                            'order': -200 if entry['kind'] == 'single' else -190,
                            'is_primary': entry['kind'] == 'single'})
        # Current and desired images may not be shared with another product.
        target_paths = {path for item in desired for path in (item['image'], item['thumbnail'])}
        target_images = {item['image'] for item in desired}
        target_records = [row for row in images if row.image in target_images]
        if len(target_records) != len({row.image for row in target_records}):
            raise CommandError('数据库中目标图片路径重复；整批停止。')
        conflicts = CigarImage.objects.filter(
            Q(image__in=target_paths) | Q(thumbnail__in=target_paths)
        ).exclude(cigar_id=103)
        if conflicts.exists():
            raise CommandError('目标图片路径已属于另一商品；整批停止。')
        changed = []
        desired_by_path = {item['image']: item for item in desired}
        for row in images:
            after = dict(_snapshot(row))
            if row.image in desired_by_path:
                after.update(desired_by_path[row.image])
            elif row.is_primary:
                after['is_primary'] = False
            if after != _snapshot(row):
                changed.append({'pk': row.pk, 'action': 'update', 'before': _snapshot(row), 'after': after})
        existing = {row.image: row for row in images}
        for spec in desired:
            if spec['image'] not in existing:
                changed.append({'pk': None, 'action': 'create', 'before': None,
                                'after': {'cigar_id': 103, 'image': spec['image'], 'thumbnail': spec['thumbnail'],
                                          'image_type': spec['image_type'], 'box_size': spec['box_size'],
                                          'image_url': '', 'order': spec['order'], 'is_primary': spec['is_primary']}})
        expected_digest = _digest({'scope': SCOPE, 'identity': identity, 'images': before_images,
                                   'manifest_digest': manifest_hash, 'desired': desired})
        return cigar, images, desired, changed, expected_digest, manifest_hash

    def _check_operation(self, options, actor, manifest_hash, expected_digest):
        marker = json.dumps({'operation_id': options['operation_id']})[1:-1]
        used = False
        for log in LogEntry.objects.filter(action_flag=CHANGE, change_message__contains=marker):
            try:
                messages = json.loads(log.change_message)
            except (ValueError, TypeError):
                continue
            for message in messages if isinstance(messages, list) else []:
                meta = message.get('seo_release', {}) if isinstance(message, dict) else {}
                if not isinstance(meta, dict) or meta.get('source') != SOURCE or meta.get('operation_id') != options['operation_id']:
                    continue
                used = True
                if (meta.get('scope') != SCOPE or log.user_id != actor.pk
                        or meta.get('manifest_digest') != manifest_hash or meta.get('commit_sha') != options['commit_sha']):
                    raise CommandError('operation-id 已用于不同的范围、操作者、清单或提交；整批停止。')
                if meta.get('result_digest') != expected_digest:
                    raise CommandError('operation-id 已执行后图片状态发生变化；请重新预览并使用新的操作 ID。')
                if meta.get('expected_digest') != options['expected_digest']:
                    raise CommandError('operation-id 已用于不同的预览输入；请使用新的操作 ID。')
        return used

    def _check_database(self, confirm_production=False):
        if not confirm_production:
            raise CommandError('图片写入必须显式提供 --confirm-production。')
        if connection.vendor != 'sqlite':
            raise CommandError('图片发布只允许使用经核验的 SQLite 数据库配置。')
        database_name = str(connection.settings_dict['NAME'])
        if database_name.startswith('file:'):
            if settings.DEBUG and database_name.startswith('file:memorydb_') and '?mode=memory' in database_name:
                return
            raise CommandError('拒绝使用 SQLite file: URI；图片发布只接受规范数据库路径。')
        if database_name == ':memory:' and settings.DEBUG:
            return
        configured = Path(database_name)
        production = (Path(settings.BASE_DIR) / 'cigars.db').resolve()
        try:
            actual = configured.resolve(strict=False)
        except (OSError, RuntimeError):
            actual = configured.absolute()
        if settings.DEBUG:
            if actual == production:
                raise CommandError('DEBUG=True 指向正式数据库 cigars.db；拒绝写入。')
            return
        if actual != production:
            raise CommandError('DEBUG=False 必须指向项目根目录的正式数据库 cigars.db；拒绝写入。')
        if not production.is_file():
            raise CommandError('正式数据库 cigars.db 不存在；拒绝创建或连接空数据库。')

    def handle(self, *args, **options):
        self._validate_options(options)
        if options['apply']:
            # Reject unsafe settings and missing production files before atomic()
            # can open SQLite or implicitly create a database file.
            self._check_database(options['confirm_production'])
        try:
            with transaction.atomic():
                actor = None
                if options['apply']:
                    actor = get_user_model().objects.select_for_update().filter(
                        username=options['actor'], is_active=True, is_staff=True).first()
                    if actor is None:
                        raise CommandError('操作者必须是现有 active staff 用户；整批停止。')
                cigar, images, desired, changes, expected_digest, manifest_hash = self._prepare()
                if options['apply']:
                    reused = self._check_operation(options, actor, manifest_hash, expected_digest)
                    if not reused and options['expected_digest'] != expected_digest:
                        raise CommandError('图片已偏离已审核的预览（expected-digest 不匹配）；整批停止，请重新预览。')
                    if changes:
                        ct = ContentType.objects.get_for_model(CigarImage)
                        audit_rows = []
                        for change in changes:
                            after = change['after']
                            if change['action'] == 'create':
                                row = CigarImage.objects.create(**after)
                            else:
                                row = next(item for item in images if item.pk == change['pk'])
                                for field in ('thumbnail', 'image_type', 'box_size', 'order', 'is_primary'):
                                    setattr(row, field, after[field])
                                row.save(update_fields=['thumbnail', 'image_type', 'box_size', 'order', 'is_primary'])
                            audit_rows.append((row, change, _snapshot(row)))
                        result_images = [_snapshot(row) for row in CigarImage.objects.select_for_update()
                                         .filter(cigar_id=103).order_by('pk')]
                        result_digest = _digest({'scope': SCOPE, 'identity': _snapshot(cigar),
                            'images': result_images, 'manifest_digest': manifest_hash, 'desired': desired})
                        for row, change, after in audit_rows:
                            meta = {'source': SOURCE, 'scope': SCOPE, 'operation_id': options['operation_id'],
                                    'commit_sha': options['commit_sha'], 'business_date': timezone.localdate().isoformat(),
                                    'manifest_digest': manifest_hash, 'expected_digest': expected_digest,
                                    'result_digest': result_digest, 'before': change['before'], 'after': after}
                            LogEntry.objects.create(user_id=actor.pk, content_type=ct, object_id=str(row.pk),
                                object_repr=str(row), action_flag=CHANGE,
                                change_message=json.dumps([{'changed': {'fields': list(after)}, 'seo_release': meta}], ensure_ascii=False))
        except CommandError:
            raise
        except (DatabaseError, OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise CommandError(f'Magicos 图片发布失败，事务未写入：{exc}') from exc
        self.stdout.write(json.dumps({'schema_version': 1, 'mode': 'apply' if options['apply'] else 'dry-run',
            'scope': SCOPE, 'source': SOURCE, 'changed_rows': len(changes), 'expected_digest': expected_digest,
            'manifest_digest': manifest_hash, 'images': changes}, ensure_ascii=False, indent=2))


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()
