from django.contrib import admin

from .models import (
    Cigar, CigarImage, Customer, User, Brand,
    PurchaseOrder, PurchaseOrderItem, PurchaseBatch,
    SalesOrder, SalesOrderItem,
    AdjustmentRecord,
)


@admin.register(Cigar)
class CigarAdmin(admin.ModelAdmin):
    list_display = ['brand', 'name', 'english_name', 'vitola', 'vitola_cn', 'common_name_cn', 'length', 'ring_gauge', 'origin', 'status', 'release_type_cn', 'parent']
    list_editable = ['name']
    list_filter = ['brand', 'origin', 'status', 'release_type', 'parent']
    search_fields = ['brand', 'name', 'english_name', 'vitola', 'vitola_cn', 'common_name_cn']
    list_per_page = 50
    autocomplete_fields = ['parent']

    def get_ordering(self, request):
        # Current → Special Releases → Discontinued, then by brand+name
        return ['status', 'brand', 'english_name']


class CigarImageInline(admin.TabularInline):
    model = CigarImage
    extra = 0
    fields = ['image', 'thumbnail', 'image_type', 'is_primary', 'order']
    readonly_fields = ['thumbnail']


@admin.register(CigarImage)
class CigarImageAdmin(admin.ModelAdmin):
    list_display = ['cigar', 'image_type', 'is_primary', 'order']
    list_filter = ['image_type', 'is_primary']
    search_fields = ['cigar__brand', 'cigar__name']


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'created_at']
    search_fields = ['name', 'phone']


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['username', 'first_name', 'telegram_id', 'is_staff', 'is_superuser', 'is_active', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active']
    search_fields = ['username', 'first_name', 'telegram_id']


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'supplier', 'rub_total', 'cny_total',
                    'operator', 'locked', 'created_at']
    list_filter = ['locked', 'supplier', 'created_at']
    search_fields = ['supplier__name', 'operator__username', 'note']
    inlines = [PurchaseOrderItemInline]
    date_hierarchy = 'created_at'


class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 0


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'customer_name', 'total_revenue',
                    'total_cost', 'total_profit', 'operator', 'locked', 'created_at']
    list_filter = ['locked', 'created_at']
    search_fields = ['customer_name', 'operator__username', 'note']
    inlines = [SalesOrderItemInline]
    date_hierarchy = 'created_at'


@admin.register(PurchaseBatch)
class PurchaseBatchAdmin(admin.ModelAdmin):
    list_display = ['cigar', 'quantity', 'remaining', 'unit_cost_cny', 'purchased_at']
    list_filter = ['cigar__brand']


@admin.register(AdjustmentRecord)
class AdjustmentRecordAdmin(admin.ModelAdmin):
    list_display = ['type', 'cigar', 'quantity', 'unit_cost_cny', 'operator', 'created_at']
    list_filter = ['type']


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'english_name', 'slug', 'category', 'origin', 'has_logo', 'created_at']
    list_filter = ['category', 'origin']
    search_fields = ['name', 'english_name', 'slug']
    readonly_fields = ['slug', 'logo_preview']

    def has_logo(self, obj):
        return bool(obj.logo)
    has_logo.boolean = True
    has_logo.short_description = '有LOGO'

    def logo_preview(self, obj):
        if obj.logo:
            return f'<img src="{obj.logo.url}" style="max-height:60px"/>'
        return '—'
    logo_preview.allow_tags = True
    logo_preview.short_description = '预览'
