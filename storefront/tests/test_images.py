from django.test import SimpleTestCase

from storefront.images import product_image_urls


class PublicImageTests(SimpleTestCase):
    origin = 'https://store.example'

    def payload(self, offers):
        return {'kind': 'product', 'product': {
            'offers': offers,
            'images': ['/media/single.jpg', '/media/box10.jpg', '/media/box25.jpg', '/media/unknown.jpg'],
            'image_variants': [
                {'url': '/media/single.jpg', 'image_type': 'cigar', 'box_size': None},
                {'url': '/media/box10.jpg', 'image_type': 'packaging', 'box_size': 10},
                {'url': '/media/box25.jpg', 'image_type': 'special', 'box_size': 25},
                {'url': '/media/unknown.jpg', 'image_type': None, 'box_size': None},
                {'url': '/media/band.jpg', 'image_type': 'band', 'box_size': None},
            ],
        }}

    def test_only_available_package_choices_and_auxiliary_singles_are_discovered(self):
        box = {'box_size': 10}
        self.assertEqual(product_image_urls(self.payload([box]), self.origin),
                         [self.origin + '/media/single.jpg', self.origin + '/media/box10.jpg'])
        self.assertEqual(product_image_urls(self.payload([{'sale_unit': 'stick'}]), self.origin),
                         [self.origin + '/media/single.jpg'])
        self.assertEqual(product_image_urls(self.payload([box, {'box_size': 25}]), self.origin),
                         [self.origin + '/media/single.jpg', self.origin + '/media/box10.jpg', self.origin + '/media/box25.jpg'])

    def test_catalog_without_offers_keeps_all_visible_images(self):
        payload = self.payload([])
        self.assertEqual(product_image_urls(payload, self.origin),
                         [self.origin + url for url in payload['product']['images']])
        payload['product'].pop('image_variants')
        payload['product']['offers'] = [{'box_size': 10}]
        self.assertEqual(len(product_image_urls(payload, self.origin)), 4)

    def test_external_hosts_tokens_and_nonmedia_urls_do_not_enter_sitemap(self):
        payload = self.payload([])
        payload['product']['images'] = [
            '/media/single.jpg', '/media/single.jpg', '//external.example/image.jpg',
            'https://store.example.evil/media/private.jpg', '/admin/photo.jpg',
            '/media/image.jpg?secret=token', '/media/image.jpg#fragment', 'data:image/png;base64,abc',
        ]
        self.assertEqual(product_image_urls(payload, self.origin), [self.origin + '/media/single.jpg'])
        self.assertEqual(product_image_urls({'kind': 'brand', 'product': payload['product']}, self.origin), [])
