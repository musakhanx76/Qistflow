from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from dateutil.relativedelta import relativedelta

from django.db import models, transaction
from django.core.exceptions import ValidationError
from catalog_customers.models import Customer, SerializedItem, Shop


class InstallmentContract(models.Model):
    TENURE_CHOICES = [
        (3, '3 Months'),
        (6, '6 Months'),
        (12, '12 Months'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Fully Paid'),
        ('DEFAULTED', 'Defaulted / Recovery'),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='contracts')
    contract_number = models.CharField(max_length=50, unique=True, db_index=True)  # e.g., QF-2026-0001
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='contracts')
    serialized_item = models.OneToOneField(
        SerializedItem, 
        on_delete=models.PROTECT, 
        related_name='contract'
    )

    start_date = models.DateField(default=date.today)
    tenure_months = models.PositiveSmallIntegerField(choices=TENURE_CHOICES)
    
    # Financial Breakdown
    product_cash_price = models.DecimalField(max_digits=12, decimal_places=2)
    down_payment = models.DecimalField(max_digits=12, decimal_places=2)
    financed_principal = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    
    markup_percentage = models.DecimalField(max_digits=5, decimal_places=2)  # e.g., 20.00 for 20%
    markup_amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    
    total_financed_payable = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    monthly_installment = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    
    remaining_balance = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.down_payment is not None and self.product_cash_price is not None:
            if self.down_payment >= self.product_cash_price:
                raise ValidationError("Down payment cannot equal or exceed the product cash price.")
        
        # Only validate stock on creation
        if not self.pk and self.serialized_item_id:
            if self.serialized_item.status != 'IN_STOCK':
                raise ValidationError("The selected serialized unit is not in stock.")

    def calculate_financials(self):
        # Only calculate on the very first creation; never mutate an existing contract!
        if not self._state.adding and self.pk:
            return

        two_places = Decimal('0.01')
        markup_factor = self.markup_percentage / Decimal('100.0')
        self.financed_principal = self.product_cash_price - self.down_payment
        self.markup_amount = (self.financed_principal * markup_factor).quantize(
            two_places, rounding=ROUND_HALF_UP
        )
        self.total_financed_payable = self.financed_principal + self.markup_amount
        self.monthly_installment = (self.total_financed_payable / Decimal(self.tenure_months)).quantize(
            two_places, rounding=ROUND_HALF_UP
        )

        if self.remaining_balance is None:
            self.remaining_balance = self.total_financed_payable

    


    @transaction.atomic
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        self.full_clean()
        self.calculate_financials()
        super().save(*args, **kwargs)

        if is_new:
            # 1. Lock the inventory unit
            self.serialized_item.status = 'ALLOCATED_TO_INSTALLMENT'
            self.serialized_item.save(update_fields=['status'])

            # 2. Build the month-by-month payment schedule
            self.generate_schedule()

    def generate_schedule(self):
        """Generates exactly 3, 6, or 12 monthly schedule rows with penny-drift correction."""
        accumulated = Decimal('0.00')

        for month in range(1, self.tenure_months + 1):
            due_date = self.start_date + relativedelta(months=month)

            # Prevent rounding drift on the final month
            if month == self.tenure_months:
                installment_amount = self.total_financed_payable - accumulated
            else:
                installment_amount = self.monthly_installment
                accumulated += installment_amount

            InstallmentSchedule.objects.create(
                contract=self,
                installment_number=month,
                due_date=due_date,
                expected_amount=installment_amount,
                remaining_due=installment_amount,
                status='PENDING'
            )

    def __str__(self):
        return f"{self.contract_number} - {self.customer.full_name} ({self.get_tenure_months_display()})"


    @property
    def true_monthly_installment(self):
        # Fetch the very first month's schedule row
        first_row = self.schedules.filter(installment_number=1).first()
    
        if first_row:
            # The schedule is the boss: return whatever Month 1 actually expects
            return first_row.expected_amount
    
        # Fallback only if schedules haven't been generated yet
        return self.monthly_installment


class InstallmentSchedule(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partially Paid'),
        ('PAID', 'Fully Paid'),
        ('OVERDUE', 'Overdue'),
    ]

    contract = models.ForeignKey(InstallmentContract, on_delete=models.CASCADE, related_name='schedules')
    installment_number = models.PositiveSmallIntegerField()
    due_date = models.DateField(db_index=True)
    expected_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    remaining_due = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)

    class Meta:
        # Group by contract FIRST, then order month 1 to 12
        ordering = ['contract', 'installment_number']
        

    def __str__(self):
        return f"{self.contract.contract_number} - Month {self.installment_number} (Due: {self.remaining_due})"


class Payment(models.Model):
    contract = models.ForeignKey(
        'InstallmentContract', 
        on_delete=models.PROTECT, 
        related_name='payments'
    )
    schedule = models.ForeignKey(
        'InstallmentSchedule', 
        on_delete=models.PROTECT, 
        related_name='payments',
        null=True, 
        blank=True
    )
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=date.today)
    manual_receipt_no = models.CharField(max_length=60, db_index=True)
    collector_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['contract', 'manual_receipt_no'],
                name='unique_contract_receipt_slip'
            )
        ]

    def clean(self):
        super().clean()

        # 1. Non-zero validation
        if self.amount_paid is not None and self.amount_paid <= Decimal('0.00'):
            raise ValidationError({'amount_paid': 'Payment amount must be greater than zero.'})

        # 2. Overpayment protection
        if self.contract and self.amount_paid is not None:
            if self.amount_paid > self.contract.remaining_balance:
                raise ValidationError({
                    'amount_paid': f"Amount exceeds remaining contract balance (Rs. {self.contract.remaining_balance})."
                })

        # 3. Friendly duplicate receipt check
        if self.contract and self.manual_receipt_no:
            duplicate_query = Payment.objects.filter(
                contract=self.contract,
                manual_receipt_no=self.manual_receipt_no.strip()
            )
            if self.pk:
                duplicate_query = duplicate_query.exclude(pk=self.pk)
            if duplicate_query.exists():
                raise ValidationError({
                    'manual_receipt_no': f"Receipt slip '{self.manual_receipt_no}' has already been recorded for Contract {self.contract.contract_number}."
                })

    def delete(self, *args, **kwargs):
        # Ledger Shield: Prevent silent out-of-sync balances
        raise ValidationError(
            "Ledger entries are immutable. Payments cannot be directly deleted as it corrupts schedule allocations."
        )

    def __str__(self):
        return f"Slip {self.manual_receipt_no}: Paid {self.amount_paid} for {self.contract.contract_number}"