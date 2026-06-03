from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='privnote_index'),
    path('create/', views.create, name='privnote_create'),
    path('api/search-cigars/', views.search_cigars, name='privnote_search_cigars'),
    path('api/payment-methods/', views.list_payment_methods, name='privnote_payment_methods'),
]
