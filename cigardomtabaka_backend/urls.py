from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render

from cigars import views
from cigars.auth_views import api_login, api_logout, api_me
from privnote.views import api_privnote


def spa_index(request):
    """Catch-all SPA entry point"""
    return render(request, 'spa_index.html')


urlpatterns = [
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
    path('api/privnote/<str:token>/', api_privnote, name='api_privnote'),
    path('privnote/', include('privnote.urls')),
    # SPA catch-all (must be last)
    re_path(r'^(?!admin/|api/|static/|media/|privnote/).*$', spa_index, name='spa_index'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
