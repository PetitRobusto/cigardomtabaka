"""Prepare reviewed-by-human drafts; never publish or overwrite store content."""
from django.core.management.base import BaseCommand
from django.db import transaction

from storefront.languages import HOME_COPY as HOME_DRAFTS
from storefront.models import StoreSettings, StoreTranslation
from storefront.public_details import PUBLIC_DETAILS


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
                'address': PUBLIC_DETAILS['address']['ru'], 'phone': PUBLIC_DETAILS['phone'],
                'map_url': PUBLIC_DETAILS['map_url'],
                'wechat': 'cigardomtabaka', 'details_verified': False,
            })
            for locale, draft in HOME_DRAFTS.items():
                StoreTranslation.objects.get_or_create(kind='home', key='home', locale=locale,
                                                       defaults={**draft, 'published': False})
        self.stdout.write('首页和门店资料草稿已准备。请在 Admin 核对后发布；现有内容未被覆盖。')
