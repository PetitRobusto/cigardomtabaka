from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render, redirect
from urllib.parse import urlencode

from cigars import views
from cigars.auth_views import api_login, api_logout, api_me
from privnote.views import (
    api_privnote, create as privnote_create,
    search_cigars as privnote_search_cigars,
    list_payment_methods as privnote_payment_methods,
    search_customers as privnote_search_customers,
    list_quote_products as privnote_quote_products,
    upload_image as privnote_upload_image,
)


def admin_login_redirect(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('/admin/')
        return redirect('/')
    next_url = request.GET.get('next', '/admin/')
    # 防止循环：next 指向 /admin/login/ 时纠正为 /admin/
    if next_url.startswith('/admin/login'):
        next_url = '/admin/'
    return redirect(f'/login/?{urlencode({"next": next_url})}')


def spa_index(request):
    """Catch-all SPA entry point"""
    return render(request, 'spa_index.html')


urlpatterns = [
    path('admin/login/', admin_login_redirect),
    path('admin/', admin.site.urls),
    # API endpoints
    path('api/login/', api_login, name='api_login'),
    path('api/logout/', api_logout, name='api_logout'),
    path('api/auth/me/', api_me, name='api_auth_me'),
    path('api/brands/', views.api_brand_list, name='api_brand_list'),
    path('api/brands/<slug:slug>/', views.api_brand_detail, name='api_brand_detail'),
    path('api/cigars/<int:cigar_id>/', views.api_cigar_detail, name='api_cigar_detail'),
    path('api/inventory/', views.api_inventory, name='api_inventory'),
    path('api/prices/', include('price_tracker.urls')),
    # Privnote — JSON API + customer view API (frontend handled by React SPA)
    path('api/privnote/<str:token>/', api_privnote, name='api_privnote'),
    path('privnote/create/', privnote_create, name='privnote_create'),
    path('privnote/api/search-cigars/', privnote_search_cigars, name='privnote_search_cigars'),
    path('privnote/api/payment-methods/', privnote_payment_methods, name='privnote_payment_methods'),
    path('privnote/api/search-customers/', privnote_search_customers, name='privnote_search_customers'),
    path('privnote/api/quote-products/', privnote_quote_products, name='privnote_quote_products'),
    path('privnote/api/upload-image/', privnote_upload_image, name='privnote_upload_image'),
    # SPA catch-all (must be last)
    re_path(r'^(?!admin/|api/|static/|media/).*$', spa_index, name='spa_index'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
