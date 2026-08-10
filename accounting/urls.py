from django.urls import path

from . import views


urlpatterns = [
    path('accounts/', views.accounts, name='accounts'),
    path('opening-balances/', views.opening_balances, name='opening_balances'),
    path('exchanges/', views.exchanges, name='exchanges'),
    path('transfers/', views.transfers, name='transfers'),
    path('overview/', views.overview, name='overview'),
    path('transactions/', views.transactions, name='transactions'),
]
