from django.contrib import admin
from .models import Privnote, PaymentMethod, PaymentMethodAudit


@admin.register(Privnote)
class PrivnoteAdmin(admin.ModelAdmin):
    list_display = ['token', 'note_type', 'title', 'burn_after_read', 'view_count', 'created_at', 'expires_at']
    list_filter = ['note_type', 'burn_after_read']
    search_fields = ['token', 'title']
    readonly_fields = ['token', 'view_count', 'created_at']


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['label', 'method_type', 'fund_account', 'is_active', 'sort_order']
    list_filter = ['method_type', 'is_active']
    search_fields = ['label', 'bank_name', 'card_number']


@admin.register(PaymentMethodAudit)
class PaymentMethodAuditAdmin(admin.ModelAdmin):
    list_display = ['payment_method', 'action', 'operator', 'agent_name', 'created_at']
    list_filter = ['action', 'agent_name']
    search_fields = ['payment_method__label', 'operator__username', 'idempotency_key']
    readonly_fields = [field.name for field in PaymentMethodAudit._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
