"""Only enqueue after commit; rendering never runs inside a business transaction."""
from django.db import transaction
from django.db.models.signals import post_delete, post_save

from cigars.models import Brand, Cigar, CigarImage, CigarPrice, PurchaseBatch, StockMovement
from .models import ProductListing, StoreSettings, StoreTranslation


def public_content_changed(sender, **kwargs):
    if kwargs.get('raw'):
        return
    from .publishing import request_refresh
    transaction.on_commit(request_refresh, robust=True)


for model in (Brand, Cigar, CigarImage, CigarPrice, PurchaseBatch, StockMovement,
              ProductListing, StoreSettings, StoreTranslation):
    post_save.connect(public_content_changed, sender=model, weak=False,
                      dispatch_uid=f'storefront.save.{model._meta.label}')
    post_delete.connect(public_content_changed, sender=model, weak=False,
                        dispatch_uid=f'storefront.delete.{model._meta.label}')
