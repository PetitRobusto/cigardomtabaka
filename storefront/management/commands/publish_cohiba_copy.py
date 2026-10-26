"""Publish the same five reviewed Cohiba entries in all three fixed languages."""

from storefront.management.commands.publish_cohiba_russian_copy import Command as RussianCopyCommand


SCOPE = 'cohiba-trilingual-copy-v1'
LOCALES = ('zh', 'ru', 'en')


class Command(RussianCopyCommand):
    help = '预览或发布固定十五条已审核中俄英 Cohiba 资料；不改价格、库存或发布状态。'
    _locales = LOCALES
    _scope = SCOPE
    _label = '中俄英三语'
    _note = '仅更新固定十五条已发布中俄英资料的文案；已一致的资料、价格、库存、身份与发布状态保持原值。'
