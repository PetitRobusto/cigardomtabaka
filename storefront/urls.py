from django.urls import path, re_path

from . import views
from .indexnow import verification


urlpatterns = [
    re_path(r'^(?P<key>[A-Za-z0-9-]{8,128})\.txt$', verification, name='indexnow_verification'),
    path("api/storefront/page/", views.page_data, name="storefront_page_data"),
    path("api/storefront/rates/", views.rates, name="storefront_rates"),
    path("api/storefront/search/", views.search, name="storefront_search"),
    path("sitemap-storefront.xml", views.sitemap, name="storefront_sitemap"),
]
