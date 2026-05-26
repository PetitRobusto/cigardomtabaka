from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from cigars import views
from cigars.auth_views import api_login, api_logout, login_page
from cigars.views import inventory
from price_tracker.views import price_dashboard
from privnote.views import view_note

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.brand_list, name='brand_list'),
    path('brand/<slug:slug>/', views.brand_detail, name='brand_detail'),
    path('cigar/<int:cigar_id>/', views.cigar_detail, name='cigar_detail'),
    path('inventory/', inventory, name='inventory'),
    path('api/login/', api_login, name='api_login'),
    path('api/logout/', api_logout, name='api_logout'),
    path('login/', login_page, name='login_page'),
    path('prices/', price_dashboard, name='price_dashboard'),
    path('prices/<path:path>', price_dashboard, name='price_dashboard_catchall'),
    path('api/prices/', include('price_tracker.urls')),
    path('privnote/', include('privnote.urls')),
    path('p/<str:token>/', view_note, name='privnote_view'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
