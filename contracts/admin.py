from django.contrib import admin
from .models import InstallmentContract, InstallmentSchedule, Payment


class InstallmentScheduleInline(admin.TabularInline):
    model = InstallmentSchedule
    extra = 0
    readonly_fields = ('installment_number', 'due_date', 'expected_amount', 'paid_amount', 'remaining_due', 'status')
    can_delete = False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ('amount_paid', 'payment_date', 'manual_receipt_no', 'created_at')


@admin.register(InstallmentContract)
class InstallmentContractAdmin(admin.ModelAdmin):
    list_display = (
        'contract_number', 
        'customer', 
        'tenure_months', 
        'monthly_installment', 
        'remaining_balance', 
        'status'
    )
    list_filter = ('status', 'tenure_months')
    search_fields = ('contract_number', 'customer__full_name', 'customer__customer_id')
    readonly_fields = (
        'financed_principal', 
        'markup_amount', 
        'total_financed_payable', 
        'monthly_installment', 
        'remaining_balance'
    )
    inlines = [InstallmentScheduleInline, PaymentInline]


@admin.register(InstallmentSchedule)
class InstallmentScheduleAdmin(admin.ModelAdmin):
    list_display = ('contract', 'installment_number', 'due_date', 'expected_amount', 'paid_amount', 'status')
    list_filter = ('status', 'due_date')
    ordering = ('contract', 'installment_number')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('manual_receipt_no', 'contract', 'amount_paid', 'payment_date')
    search_fields = ('manual_receipt_no', 'contract__contract_number')