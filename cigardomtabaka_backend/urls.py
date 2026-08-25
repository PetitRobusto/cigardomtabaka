from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render, redirect
from urllib.parse import urlencode

from cigars import views
from cigars import agent_api
from cigars import sales_api
from cigars import inventory_api
from cigars.auth_views import api_login, api_logout, api_me
from cigars.guide_views import guide_status, guide_complete, guide_replay
from privnote.views import (
    api_privnote, create as privnote_create,
    search_cigars as privnote_search_cigars,
    list_payment_methods as privnote_payment_methods,
    payment_method_action as privnote_payment_method_action,
    list_payment_orders as privnote_payment_orders,
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
    return render(request, 'spa_index.html', {'debug': settings.DEBUG})


urlpatterns = [
    path('admin/login/', admin_login_redirect),
    path('admin/', admin.site.urls),
    # API endpoints
    path('api/login/', api_login, name='api_login'),
    path('api/logout/', api_logout, name='api_logout'),
    path('api/auth/me/', api_me, name='api_auth_me'),
    path('api/guides/status/', guide_status, name='guide_status'),
    path('api/guides/complete/', guide_complete, name='guide_complete'),
    path('api/guides/replay/', guide_replay, name='guide_replay'),
    path('api/brands/', views.api_brand_list, name='api_brand_list'),
    path('api/brands/<slug:slug>/', views.api_brand_detail, name='api_brand_detail'),
    path('api/cigars/<int:cigar_id>/', views.api_cigar_detail, name='api_cigar_detail'),
    path('api/inventory/', views.api_inventory, name='api_inventory'),
    path('api/agent/search/', agent_api.search_inventory, name='agent_search_inventory'),
    path('api/agent/stock/', agent_api.stock_query, name='agent_stock_query'),
    path('api/agent/suppliers/', agent_api.supplier_list, name='agent_supplier_list'),
    path('api/agent/purchase-orders/create/', agent_api.create_purchase_order_command, name='agent_create_purchase_order'),
    path('api/agent/purchase-orders/update/', agent_api.update_purchase_order_command, name='agent_update_purchase_order'),
    path('api/agent/purchase-orders/cancel/', agent_api.cancel_purchase_order_command, name='agent_cancel_purchase_order'),
    path('api/agent/purchase-orders/receive/', agent_api.receive_purchase_order_command, name='agent_receive_purchase_order'),
    path('api/agent/purchase-orders/reverse-receive/', agent_api.reverse_purchase_receipt_command, name='agent_reverse_purchase_receipt'),
    path('api/agent/orders/', agent_api.sales_orders_query, name='agent_sales_orders'),
    path('api/agent/orders/<int:order_id>/', agent_api.sales_order_detail_query, name='agent_sales_order_detail'),
    path('api/agent/orders/create/', agent_api.create_sales_order_command, name='agent_create_sales_order'),
    path('api/agent/orders/update/', agent_api.update_sales_order_command, name='agent_update_sales_order'),
    path('api/agent/orders/confirm/', agent_api.confirm_sales_order_command, name='agent_confirm_sales_order'),
    path('api/agent/orders/cancel/', agent_api.cancel_sales_order_command, name='agent_cancel_sales_order'),
    path('api/agent/orders/ship/', agent_api.ship_sales_order_command, name='agent_ship_sales_order'),
    path('api/agent/orders/receive/', agent_api.receive_sales_order_payment_command, name='agent_receive_sales_order_payment'),
    path('api/agent/orders/refund/', agent_api.refund_sales_order_payment_command, name='agent_refund_sales_order_payment'),
    path('api/agent/orders/return/', agent_api.return_sales_order_command, name='agent_return_sales_order'),
    path('api/agent/orders/transport-cost/', agent_api.record_sales_transport_cost_command, name='agent_record_sales_transport_cost'),
    path('api/agent/stock/adjust/', agent_api.adjust_stock_command, name='agent_adjust_stock'),
    path('api/agent/stock/adjust/reverse/', agent_api.reverse_stock_adjustment_command, name='agent_reverse_stock_adjustment'),
    path('api/agent/stock/audit/', agent_api.inventory_audit_query, name='agent_inventory_audit'),
    path('api/agent/reports/basic/', agent_api.business_report, name='agent_business_report'),
    path('api/sales/orders/', sales_api.sales_orders, name='sales_orders'),
    path('api/sales/orders/<int:order_id>/', sales_api.sales_order_detail, name='sales_order_detail'),
    path('api/sales/orders/<int:order_id>/confirm/', sales_api.sales_order_confirm, name='sales_order_confirm'),
    path('api/sales/orders/<int:order_id>/cancel/', sales_api.sales_order_cancel, name='sales_order_cancel'),
    path('api/sales/orders/<int:order_id>/ship/', sales_api.sales_order_ship, name='sales_order_ship'),
    path('api/sales/orders/<int:order_id>/receive/', sales_api.sales_order_receive, name='sales_order_receive'),
    path('api/sales/orders/<int:order_id>/refund/', sales_api.sales_order_refund, name='sales_order_refund'),
    path('api/sales/orders/<int:order_id>/return/', sales_api.sales_order_return, name='sales_order_return'),
    path('api/sales/orders/<int:order_id>/transport-cost/', sales_api.sales_order_transport_cost, name='sales_order_transport_cost'),
    path('api/sales/customers/', sales_api.sales_customers, name='sales_customers'),
    path('api/sales/customers/<int:customer_id>/', sales_api.sales_customer_detail, name='sales_customer_detail'),
    path('api/inventory/adjustments/<int:adjustment_id>/reverse/', inventory_api.inventory_adjustment_reverse, name='inventory_adjustment_reverse'),
    path('api/inventory/audit/', inventory_api.inventory_audit, name='inventory_audit'),
    path('api/inventory/suppliers/', inventory_api.inventory_suppliers, name='inventory_suppliers'),
    path('api/inventory/purchases/', inventory_api.inventory_purchases, name='inventory_purchases'),
    path('api/inventory/purchases/<int:purchase_id>/', inventory_api.inventory_purchases, name='inventory_purchase_detail'),
    path('api/accounting/', include('accounting.urls')),
    path('api/prices/', include('price_tracker.urls')),
    # Privnote — JSON API + customer view API (frontend handled by React SPA)
    path('api/privnote/<str:token>/', api_privnote, name='api_privnote'),
    path('privnote/create/', privnote_create, name='privnote_create'),
    path('privnote/api/search-cigars/', privnote_search_cigars, name='privnote_search_cigars'),
    path('privnote/api/payment-methods/', privnote_payment_methods, name='privnote_payment_methods'),
    path('privnote/api/payment-methods/<int:method_id>/<str:action>/', privnote_payment_method_action, name='privnote_payment_method_action'),
    path('privnote/api/payment-orders/', privnote_payment_orders, name='privnote_payment_orders'),
    path('privnote/api/search-customers/', privnote_search_customers, name='privnote_search_customers'),
    path('privnote/api/quote-products/', privnote_quote_products, name='privnote_quote_products'),
    path('privnote/api/upload-image/', privnote_upload_image, name='privnote_upload_image'),
    # SPA catch-all (must be last)
    re_path(r'^(?!admin/|api/|static/|media/).*$', spa_index, name='spa_index'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
