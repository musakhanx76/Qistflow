from django.contrib import admin
from .models import Shop, Customer, Guarantor, Product, SerializedItem

class GuarantorInline(admin.TabularInline):
    model = Guarantor
    extra = 1

class SerializedItemInline(admin.TabularInline):
    model = SerializedItem
    extra = 2

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('customer_id', 'full_name', 'phone_primary', 'national_id', 'shop')
    search_fields = ('customer_id', 'full_name', 'phone_primary', 'national_id')
    inlines = [GuarantorInline]

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('brand', 'model_name', 'category', 'cash_price', 'shop')
    list_filter = ('category', 'brand')
    search_fields = ('model_name', 'brand')
    inlines = [SerializedItemInline]

admin.site.register(Shop)
admin.site.register(SerializedItem)