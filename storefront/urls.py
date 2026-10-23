from django.urls import path

from . import views


urlpatterns = [
    path("api/storefront/page/", views.page_data, name="storefront_page_data"),
    path("api/storefront/rates/", views.rates, name="storefront_rates"),
    path("api/storefront/search/", views.search, name="storefront_search"),
    path("sitemap-storefront.xml", views.sitemap, name="storefront_sitemap"),
]
