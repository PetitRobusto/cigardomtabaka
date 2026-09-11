"""Private storage used for customer payment artefacts.

Payment QR codes and proof images must never be handed to Django's public
``/media/`` route.  The storage is intentionally separate from product media;
views authorise each read and stream the file explicitly.
"""

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivatePaymentStorage(FileSystemStorage):
    """A migration-safe filesystem storage resolved from Django settings."""

    def __init__(self):
        super().__init__(location=settings.PRIVATE_PAYMENT_MEDIA_ROOT)

    def deconstruct(self):
        return ("privnote.storage.PrivatePaymentStorage", [], {})


private_payment_storage = PrivatePaymentStorage()
