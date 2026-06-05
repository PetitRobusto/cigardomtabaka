"""价格跟踪系统 — URL 路由"""
from django.conf import settings
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'sources', views.PriceSourceViewSet, basename='price-source')
router.register(r'snapshots', views.PriceSnapshotViewSet, basename='price-snapshot')
router.register(r'alerts', views.PriceAlertViewSet, basename='price-alert')

urlpatterns = [
    path('', include(router.urls)),
    path('import_coh/', views.import_coh_bulk, name='import_coh_bulk'),
]

# push-bulk 仅在 DEBUG=False (生产模式) 时注册
if not settings.DEBUG:
    from .push_api import push_bulk
    urlpatterns.append(path('push-bulk/', push_bulk, name='push_bulk'))
