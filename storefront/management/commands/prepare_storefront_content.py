"""Prepare reviewed-by-human drafts; never publish or overwrite store content."""
from django.core.management.base import BaseCommand
from django.db import transaction

from storefront.models import StoreSettings, StoreTranslation


HOME_DRAFTS = {
    'zh': {
        'title': '莫斯科雪茄门店与现货 | CigarDomTabaka',
        'description': '查看 CigarDomTabaka 莫斯科雪茄门店的现货、盒装规格与价格，按品牌浏览并联系门店确认购买。',
        'body': '浏览当前可售的盒装雪茄，查看品牌、规格与价格。选择商品后，请联系门店确认现货和购买安排。人民币与美元换算仅供参考，正式标价以卢布为准。',
    },
    'ru': {
        'title': 'Сигары в Москве — наличие и цены | CigarDomTabaka',
        'description': 'Сигары в наличии в CigarDomTabaka в Москве: бренды, форматы коробок и цены. Свяжитесь с магазином для подтверждения покупки.',
        'body': 'Выберите сигары из доступных коробок, сравните бренды, форматы и цены. Перед покупкой свяжитесь с магазином, чтобы подтвердить наличие и договориться о покупке. Пересчёт в CNY и USD приведён для справки; основная цена указана в рублях.',
    },
    'en': {
        'title': 'Cigars in Moscow — stock and prices | CigarDomTabaka',
        'description': 'Browse cigars in stock at CigarDomTabaka in Moscow, with brands, box sizes and prices. Contact the store to confirm your purchase.',
        'body': 'Explore available boxes of cigars, compare brands and sizes, and view prices. Contact the store to confirm availability and purchase arrangements. CNY and USD conversions are for reference; the listed retail price is in rubles.',
    },
}


class Command(BaseCommand):
    help = '准备三语首页和已有门店资料草稿，不覆盖现有内容、不发布商品、不设置价格。'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if options['dry_run']:
            for locale, draft in HOME_DRAFTS.items():
                self.stdout.write(f'{locale}: {draft["title"]}（草稿）')
            return
        with transaction.atomic():
            StoreSettings.objects.get_or_create(pk=1, defaults={
                'address': 'Москва, Молодёжная ул. 3', 'phone': '+7 929 638-48-78',
                'wechat': 'cigardomtabaka', 'details_verified': False,
            })
            for locale, draft in HOME_DRAFTS.items():
                StoreTranslation.objects.get_or_create(kind='home', key='home', locale=locale,
                                                       defaults={**draft, 'published': False})
        self.stdout.write('首页和门店资料草稿已准备。请在 Admin 核对后发布；现有内容未被覆盖。')
