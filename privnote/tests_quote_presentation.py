"""报价单图片和品牌中文展示回归；不依赖生产媒体或数据库。"""
from django.test import TestCase

from cigars.models import Brand, Cigar, CigarImage, CigarPrice
from privnote.helpers import get_brand_info_map, get_thumb_url
from privnote.services.quote import build_quote_data


class QuotePresentationTests(TestCase):
    def setUp(self):
        self.cigar = Cigar.objects.create(brand='San Cristóbal', english_name='El Principe')
        CigarPrice.objects.create(
            cigar=self.cigar, box_size=25, wholesale_price=1000,
            is_active=True, can_preorder=True,
        )

    def image(self, path, *, kind='cigar', primary=False, thumbnail=True, order=0):
        return CigarImage.objects.create(
            cigar=self.cigar, image=path,
            thumbnail=f'{path}.thumb.webp' if thumbnail else '',
            image_type=kind, is_primary=primary, order=order,
        )

    def quote_item(self):
        return build_quote_data()['brand_groups'][0]['items'][0]

    def test_quote_keeps_legacy_product_image_when_storefront_primary_changes(self):
        legacy = self.image('cigars/san-cristobal/el-principe/cigar.jpg')
        primary = self.image('storefront/generated-v4/products/single.webp', primary=True, order=-200)
        self.assertEqual(self.quote_item()['thumb_url'], legacy.thumbnail.url)
        self.assertEqual(get_thumb_url(self.cigar), primary.thumbnail.url)
        self.assertEqual(self.cigar.primary_image.pk, primary.pk)

    def test_missing_legacy_thumbnail_uses_legacy_original(self):
        legacy = self.image('cigars/san-cristobal/el-principe/cigar.jpg', thumbnail=False)
        self.image('storefront/generated-v4/products/single.webp', primary=True, order=-200)
        self.assertEqual(self.quote_item()['thumb_url'], legacy.image.url)

    def test_no_legacy_product_uses_current_primary(self):
        primary = self.image('storefront/generated-v4/products/single.webp', primary=True, order=-200)
        self.assertEqual(self.quote_item()['thumb_url'], primary.thumbnail.url)

    def test_band_and_packaging_are_not_selected_as_legacy_product_image(self):
        self.image('cigars/old/band.jpg', kind='band', order=-500)
        self.image('cigars/old/box.jpg', kind='packaging', order=-400)
        primary = self.image('storefront/generated-v4/products/single.webp', primary=True, order=-200)
        self.assertEqual(self.quote_item()['thumb_url'], primary.thumbnail.url)

    def test_product_without_images_remains_empty(self):
        self.assertEqual(self.quote_item()['thumb_url'], '')

    def test_short_brand_name_has_chinese_without_matching_brand_row(self):
        Brand.objects.create(english_name='San Cristóbal de la Habana', name='圣克里斯多')
        group = build_quote_data()['brand_groups'][0]
        self.assertEqual(group['brand'], 'San Cristóbal')
        self.assertEqual(group['brand_cn'], '圣克里斯托')

    def test_approved_names_override_old_database_names_and_preserve_logos(self):
        approved = {
            'San Cristóbal': '圣克里斯托',
            'San Cristóbal de la Habana': '圣克里斯托',
            'Ramón Allones': '雷蒙阿隆',
            'Vegas Robaina': '罗宾娜',
            'Quintero': '君特罗',
            "Quai d'Orsay": '凯多赛',
        }
        for index, name in enumerate(approved):
            Brand.objects.create(english_name=name, name='旧译名', logo=f'brand_logos/{index}.jpg')
        info = get_brand_info_map(approved)
        for index, (name, chinese) in enumerate(approved.items()):
            with self.subTest(brand=name):
                self.assertEqual(info[name]['name'], chinese)
                self.assertTrue(info[name]['logo_url'].endswith(f'/brand_logos/{index}.jpg'))
        self.assertNotEqual(info['Quintero']['name'], info["Quai d'Orsay"]['name'])

    def test_unknown_brand_uses_database_name_or_english_fallback(self):
        Brand.objects.create(english_name='Custom Brand', name='自定义品牌')
        info = get_brand_info_map(['Custom Brand', 'Missing Brand'])
        self.assertEqual(info['Custom Brand']['name'], '自定义品牌')
        self.assertEqual(info['Missing Brand'], {'name': 'Missing Brand', 'logo_url': None})

    def test_image_queries_do_not_grow_with_number_of_products(self):
        self.image('cigars/old/cigar.jpg')
        with self.assertNumQueries(4):
            build_quote_data()
        for index in range(4):
            cigar = Cigar.objects.create(brand='Quintero', english_name=f'Product {index}')
            CigarPrice.objects.create(cigar=cigar, box_size=25, wholesale_price=1000, can_preorder=True)
            CigarImage.objects.create(cigar=cigar, image=f'cigars/{index}.jpg',
                                      thumbnail=f'cigars/{index}-thumb.jpg', image_type='cigar')
        with self.assertNumQueries(4):
            self.assertEqual(build_quote_data()['total_items'], 5)
