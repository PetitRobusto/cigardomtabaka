from django.contrib import admin
from .models import Privnote, PaymentMethod


@admin.register(Privnote)
class PrivnoteAdmin(admin.ModelAdmin):
    list_display = ['token', 'note_type', 'title', 'burn_after_read', 'view_count', 'created_at', 'expires_at']
    list_filter = ['note_type', 'burn_after_read']
    search_fields = ['token', 'title']
    readonly_fields = ['token', 'view_count', 'created_at']


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['label', 'method_type', 'is_active', 'sort_order']
    list_filter = ['method_type', 'is_active']
    search_fields = ['label', 'bank_name', 'card_number']
