from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='privnote_index'),
    path('create/', views.create, name='privnote_create'),
]
