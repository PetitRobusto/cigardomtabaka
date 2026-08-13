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
]
