"""Public gallery URLs from an already published product payload; no media queries."""
from urllib.parse import urljoin, urlsplit


def product_image_urls(payload, origin):
    if payload.get('kind') != 'product':
        return []
    product = payload.get('product') or {}
    variants = product.get('image_variants')
    offers = product.get('offers') or []
    if variants is None or not offers:
        urls = product.get('images') or [product.get('image_url')]
    else:
        # Match offerImages/detailImages: every publicly selectable package, plus
        # its auxiliary single-cigar views. Unoffered boxes and unknown types stay out.
        sticks = any(offer.get('sale_unit') == 'stick' for offer in offers)
        boxes = {offer.get('box_size') for offer in offers
                 if offer.get('sale_unit') != 'stick' and offer.get('box_size') is not None}
        urls = [image.get('url') for image in variants if (
            (image.get('image_type') == 'cigar' and (sticks or (boxes and image.get('box_size') is None)))
            or (image.get('image_type') in ('packaging', 'special') and image.get('box_size') in boxes)
        )]
    site = urlsplit(origin)
    result = []
    for url in urls:
        if not url:
            continue
        absolute = urljoin(origin + '/', url)
        parsed = urlsplit(absolute)
        # Existing product media are local; external source domains are not
        # verified image hosts for this sitemap. Include the public file, no tokens.
        if (parsed.scheme == site.scheme and parsed.netloc == site.netloc
                and parsed.path.startswith('/media/') and not parsed.query and not parsed.fragment
                and '\\' not in absolute and not any(ord(char) < 32 for char in absolute)
                and absolute not in result):
            result.append(absolute)
    return result[:1000]
