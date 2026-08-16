from django.urls import path

from . import views


urlpatterns = [
    # Day 1 is intentionally reachable by URL but never added to common navigation.
    path('day1/', views.day1_status, name='day1_status'),
    path('day1/draft/', views.day1_draft, name='day1_draft'),
    path('day1/confirm/', views.day1_confirm, name='day1_confirm'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('accounts/', views.accounts, name='accounts'),
    path('opening-balances/', views.opening_balances, name='opening_balances'),
    path('exchanges/', views.exchanges, name='exchanges'),
    path('transfers/', views.transfers, name='transfers'),
    path('overview/', views.overview, name='overview'),
    path('transactions/', views.transactions, name='transactions'),
    path('reports/monthly-profit/', views.monthly_profit_report, name='monthly_profit_report'),
    path('reports/summary/', views.summary_report, name='summary_report'),
    path('reconciliations/', views.reconciliations, name='reconciliations'),
    path(
        'reconciliations/<int:reconciliation_id>/confirm/',
        views.reconciliation_confirm,
        name='reconciliation_confirm',
    ),
    path('actions/', views.actions, name='accounting_actions'),
    path('purchases/', views.purchase_action, name='purchase_action_create'),
    path('purchases/<int:purchase_id>/', views.purchase_action, name='purchase_action_update'),
    path('purchases/<int:purchase_id>/pay/', views.purchase_action, {'action': 'pay'}, name='purchase_action_pay'),
    path('purchases/<int:purchase_id>/receive/', views.purchase_action, {'action': 'receive'}, name='purchase_action_receive'),
    path('purchases/<int:purchase_id>/reverse-receive/', views.purchase_action, {'action': 'reverse-receive'}, name='purchase_action_reverse_receive'),
    path('purchases/<int:purchase_id>/cancel/', views.purchase_action, {'action': 'cancel'}, name='purchase_action_cancel'),
    path('expenses/', views.expense_action, name='expense_action'),
    path('dividends/', views.dividend_action, name='dividend_action_collection'),
    path('dividends/<int:dividend_id>/', views.dividend_action, name='dividend_action_detail'),
    path('dividends/<int:dividend_id>/preview/', views.dividend_action, {'action': 'preview'}, name='dividend_action_preview'),
    path('dividends/<int:dividend_id>/confirm/', views.dividend_action, {'action': 'confirm'}, name='dividend_action_confirm'),
]
