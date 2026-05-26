"""价格跟踪系统 — Admin 注册"""
from django.contrib import admin
from .models import PriceSource, PriceSnapshot, PriceAlert


@admin.register(PriceSource)
class PriceSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'currency', 'active', 'last_scraped', 'scrape_interval_hours']
    list_filter = ['active', 'currency']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(PriceSnapshot)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ['cigar', 'source', 'price', 'currency', 'price_cny', 'in_stock', 'scraped_at']
    list_filter = ['source', 'in_stock', 'currency']
    search_fields = ['cigar__name', 'cigar__brand', 'cigar__english_name']
    date_hierarchy = 'scraped_at'
    raw_id_fields = ['cigar']


@admin.register(PriceAlert)
class PriceAlertAdmin(admin.ModelAdmin):
    list_display = ['cigar', 'source', 'condition', 'target_price', 'enabled', 'last_triggered']
    list_filter = ['condition', 'enabled', 'source']
    search_fields = ['cigar__name']
    raw_id_fields = ['cigar']
