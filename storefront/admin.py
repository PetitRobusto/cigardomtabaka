from django.contrib import admin

from .models import ProductListing, StorePage, StoreSettings, StoreTranslation
from .publishing import request_refresh


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not StoreSettings.objects.exists()


@admin.register(ProductListing)
class ProductListingAdmin(admin.ModelAdmin):
    list_display = ['cigar', 'published', 'withdrawn', 'updated_at']
    list_filter = ['published', 'withdrawn']
    search_fields = ['cigar__name', 'cigar__english_name', 'cigar__brand']
    autocomplete_fields = ['cigar']


@admin.register(StoreTranslation)
class StoreTranslationAdmin(admin.ModelAdmin):
    list_display = ['title', 'kind', 'key', 'locale', 'published', 'updated_at']
    list_filter = ['locale', 'kind', 'published']
    search_fields = ['title', 'key', 'aliases']
    autocomplete_fields = ['cigar']

    def get_readonly_fields(self, request, obj=None):
        return ['key', 'kind', 'cigar'] if obj and obj.kind == 'product' else []


@admin.register(StorePage)
class StorePageAdmin(admin.ModelAdmin):
    list_display = ['path', 'active', 'changed_at', 'rendered_at', 'attempts', 'error']
    list_filter = ['active']
    search_fields = ['path', 'error']
    readonly_fields = [field.name for field in StorePage._meta.fields]
    exclude = ['html']
    actions = ['refresh']

    @admin.action(description='请求重新校验并刷新商城页面')
    def refresh(self, request, queryset):
        request_refresh()
        self.message_user(request, '已请求刷新。worker 将合并并处理内容变更。')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
