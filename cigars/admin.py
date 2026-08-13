from django.contrib import admin

from .models import (
    Cigar, CigarImage, Customer, User, Brand,
    PurchaseOrder, PurchaseOrderItem, PurchaseBatch,
    SalesOrder, SalesOrderItem,
    StockAllocation, StockMovement, OrderEvent, IdempotencyRecord,
    AdjustmentRecord, CigarPrice,
    GuideConfiguration, UserGuideProgress,
)


@admin.register(GuideConfiguration)
class GuideConfigurationAdmin(admin.ModelAdmin):
    fields = ('version', 'auto_show_enabled')

    def has_add_permission(self, request):
        return not GuideConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserGuideProgress)
class UserGuideProgressAdmin(admin.ModelAdmin):
    fields = ('user', 'completed_version', 'force_show_next_time', 'completed_at')
    readonly_fields = ('completed_version', 'completed_at')
    list_display = ('user', 'completed_version', 'force_show_next_time', 'completed_at')
    list_filter = ('force_show_next_time',)
    search_fields = ('user__username', 'user__first_name', 'user__telegram_id')


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
    list_display = [
        'cigar', 'quantity', 'positive_adjustment_quantity', 'physical_remaining', 'remaining',
        'original_cost_cny', 'positive_adjustment_cost_cny', 'remaining_cost_cny',
        'sold_cost_cny', 'adjustment_cost_cny', 'unit_cost_cny', 'purchased_at',
    ]
    list_filter = ['cigar__brand']


@admin.register(AdjustmentRecord)
class AdjustmentRecordAdmin(admin.ModelAdmin):
    list_display = ['type', 'cigar', 'quantity', 'unit_cost_cny', 'cost_cny', 'operator', 'created_at']
    list_filter = ['type']


@admin.register(StockAllocation)
class StockAllocationAdmin(admin.ModelAdmin):
    list_display = ['sales_order_item', 'purchase_batch', 'quantity', 'status', 'reserved_at']
    list_filter = ['status']
    search_fields = ['sales_order_item__sales_order__customer_name', 'purchase_batch__cigar__english_name']


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['movement_type', 'cigar', 'purchase_batch', 'sales_order', 'quantity',
                    'operator', 'agent_name', 'command_name', 'created_at']
    list_filter = ['movement_type', 'agent_name', 'command_name']
    search_fields = ['cigar__brand', 'cigar__english_name', 'sales_order__customer_name',
                     'operator__username', 'agent_name', 'idempotency_key', 'note']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = ['sales_order', 'command_name', 'operator', 'agent_name', 'created_at']
    list_filter = ['command_name', 'agent_name']
    search_fields = ['sales_order__customer_name', 'operator__username', 'agent_name', 'note']
    date_hierarchy = 'created_at'


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ['key', 'command_name', 'operator', 'agent_name', 'status_code', 'created_at']
    list_filter = ['command_name', 'agent_name', 'status_code']
    search_fields = ['key', 'command_name', 'operator__username', 'agent_name', 'agent_run_id']
    date_hierarchy = 'created_at'


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


@admin.register(CigarPrice)
class CigarPriceAdmin(admin.ModelAdmin):
    list_display = ['cigar', 'box_size', 'wholesale_price', 'retail_price', 'can_preorder', 'per_stick_price_display', 'sort_order', 'is_active', 'updated_at']
    list_editable = ['wholesale_price', 'retail_price', 'can_preorder', 'sort_order', 'is_active']
    list_filter = ['is_active', 'can_preorder', 'cigar__brand']
    search_fields = ['cigar__brand', 'cigar__name', 'cigar__english_name']
    autocomplete_fields = ['cigar']

    def per_stick_price_display(self, obj):
        return f'¥{obj.per_stick_price}'
    per_stick_price_display.short_description = '折算单价/支'
