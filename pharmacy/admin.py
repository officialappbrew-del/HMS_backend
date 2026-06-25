from django.contrib import admin
from .models import Drug, Dispense

@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ('name', 'drug_code', 'category', 'stock_quantity', 'reorder_level', 'unit_price', 'is_controlled', 'tenant')
    list_filter = ('category', 'form', 'is_controlled', 'tenant')
    search_fields = ('name', 'drug_code', 'generic_name', 'brand_name', 'nafdac_number')

@admin.register(Dispense)
class DispenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'drug', 'patient', 'quantity', 'total_price', 'dispensed_by', 'dispensed_date', 'tenant')
    list_filter = ('tenant', 'dispensed_date')
    search_fields = ('drug__name', 'patient__get_full_name', 'instructions')
