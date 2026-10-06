from django.contrib import admin
from django.core.exceptions import ValidationError
from .models import InstallmentContract, InstallmentSchedule, Payment
from .services import PaymentService


class InstallmentScheduleInline(admin.TabularInline):
    model = InstallmentSchedule
    extra = 0
    readonly_fields = ('installment_number', 'due_date', 'expected_amount', 'paid_amount', 'remaining_due', 'status')
    can_delete = False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ('manual_receipt_no', 'amount_paid', 'payment_date', 'collector_notes')
    readonly_fields = ('created_at',)


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
    list_display = (
        'contract', 
        'installment_number', 
        'due_date', 
        'expected_amount', 
        'paid_amount', 
        'remaining_due', 
        'status'
    )
    list_filter = ('status', 'due_date')
    search_fields = ('contract__contract_number', 'contract__customer__full_name')
    ordering = ('contract', 'installment_number')  # Groups rows by contract, then month 1..N


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('manual_receipt_no', 'contract', 'amount_paid', 'payment_date', 'created_at')
    search_fields = ('manual_receipt_no', 'contract__contract_number')
    autocomplete_fields = ['contract']
    fields = ('contract', 'amount_paid', 'manual_receipt_no', 'payment_date', 'collector_notes')

    def has_delete_permission(self, request, obj=None):
        # Prevents cashiers/admins from deleting cash ledger slips
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            try:
                payment = PaymentService.record_payment(
                    contract=obj.contract,
                    amount=obj.amount_paid,
                    manual_receipt_no=obj.manual_receipt_no,
                    payment_date=obj.payment_date,
                    notes=obj.collector_notes
                )
                obj.pk = payment.pk
                obj.id = payment.id
            except ValidationError as e:
                self.message_user(request, f"Payment failed: {e.message}", level='ERROR')
        else:
            super().save_model(request, obj, form, change)