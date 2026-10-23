"""Read-only URL inventory, suitable for joining with search-console exports."""
import csv
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from cigars.models import Brand, Cigar
from storefront.catalog import _product_slug


class Command(BaseCommand):
    help = '导出现有中文目录 URL；曝光、点击、外链需另从搜索后台导出，不臆测排名。'

    def handle(self, *args, **options):
        writer = csv.writer(sys.stdout)
        writer.writerow(['url', 'kind', 'id', 'name', 'search_impressions', 'search_clicks', 'indexed', 'backlinks'])
        writer.writerow([settings.STOREFRONT_ORIGIN + '/', 'home', '', 'CigarDomTabaka', '', '', '', ''])
        for brand in Brand.objects.order_by('pk'):
            writer.writerow([f'{settings.STOREFRONT_ORIGIN}/brand/{brand.slug}', 'brand', brand.pk, brand.english_name, '', '', '', ''])
        for cigar in Cigar.objects.filter(deleted_at__isnull=True).order_by('pk'):
            writer.writerow([f'{settings.STOREFRONT_ORIGIN}/cigar/{cigar.pk}/{_product_slug(cigar)}', 'product', cigar.pk, cigar.english_name, '', '', '', ''])
