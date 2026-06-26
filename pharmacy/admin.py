from django.contrib import admin
from .models import Drug, Supplier, Sale, SaleItem, Dispense

@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ('name', 'drug_code', 'category', 'form', 'stock_quantity', 'reorder_level', 'unit_price', 'selling_price', 'is_controlled', 'tenant')
    list_filter = ('category', 'form', 'is_controlled', 'status', 'tenant')
    search_fields = ('name', 'drug_code', 'generic_name', 'brand_name', 'nafdac_number')
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone', 'email', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name', 'contact_person', 'phone', 'email')

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'sold_by', 'total_amount', 'payment_method', 'payment_status', 'status', 'sold_at', 'tenant')
    list_filter = ('payment_method', 'payment_status', 'status', 'tenant', 'sold_at')
    search_fields = ('patient__get_full_name', 'sold_by__get_full_name')
    readonly_fields = ['sold_at']

@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'drug', 'quantity', 'unit_price', 'total_price')
    list_filter = ('sale', 'drug')
    search_fields = ('drug__name',)

@admin.register(Dispense)
class DispenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'drug', 'patient', 'quantity', 'total_price', 'dispensed_by', 'dispensed_date', 'tenant')
    list_filter = ('tenant', 'dispensed_date')
    search_fields = ('drug__name', 'patient__get_full_name', 'instructions')
