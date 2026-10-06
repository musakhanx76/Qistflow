from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Payment, InstallmentContract, InstallmentSchedule


class PaymentService:
    @staticmethod
    @transaction.atomic
    def record_payment(contract: InstallmentContract, amount: Decimal, manual_receipt_no: str, payment_date=None, notes=None) -> Payment:
        if amount <= Decimal('0.00'):
            raise ValidationError("Payment amount must be greater than zero.")

        if amount > contract.remaining_balance:
            raise ValidationError(
                f"Payment amount ({amount}) exceeds remaining contract balance ({contract.remaining_balance})."
            )

        payment = Payment.objects.create(
            contract=contract,
            amount_paid=amount,
            manual_receipt_no=manual_receipt_no,
            collector_notes=notes,
            **({'payment_date': payment_date} if payment_date else {})
        )

        unallocated_funds = amount
        pending_schedules = contract.schedules.filter(
            status__in=['PENDING', 'PARTIAL', 'OVERDUE']
        ).order_by('installment_number')

        for schedule in pending_schedules:
            if unallocated_funds <= Decimal('0.00'):
                break

            if unallocated_funds >= schedule.remaining_due:
                unallocated_funds -= schedule.remaining_due
                schedule.paid_amount += schedule.remaining_due
                schedule.remaining_due = Decimal('0.00')
                schedule.status = 'PAID'
            else:
                schedule.paid_amount += unallocated_funds
                schedule.remaining_due -= unallocated_funds
                schedule.status = 'PARTIAL'
                unallocated_funds = Decimal('0.00')

            schedule.save()

        # 4. Update contract remaining balance
        contract.remaining_balance -= amount

        # 5. Check if overdue schedules have been cleared (Curing the contract)
        has_remaining_overdue = contract.schedules.filter(status='OVERDUE').exists()
        if not has_remaining_overdue and contract.status == 'DEFAULTED':
            contract.status = 'ACTIVE'

        # 6. Contract completion check & title transfer
        if contract.remaining_balance == Decimal('0.00'):
            contract.status = 'COMPLETED'
            contract.serialized_item.status = 'SETTLED_OWNED'
            contract.serialized_item.save(update_fields=['status'])

        contract.save()
        return payment

    @staticmethod
    @transaction.atomic
    def settle_contract_early(contract: InstallmentContract, cash_collected: Decimal, discount_amount: Decimal, manual_receipt_no: str, notes=None) -> Payment:
        """
        Closes a contract early by accepting a cash lump sum and writing off 
        an agreed markup discount.
        """
        total_settlement = cash_collected + discount_amount
        if total_settlement != contract.remaining_balance:
            raise ValidationError(
                f"Settlement sum (Cash: {cash_collected} + Discount: {discount_amount} = {total_settlement}) "
                f"must exactly match remaining balance ({contract.remaining_balance})."
            )

        # 1. Record the actual cash collected on paper slip
        settlement_notes = f"EARLY SETTLEMENT: Rs. {discount_amount} discount applied. {notes or ''}"
        payment = Payment.objects.create(
            contract=contract,
            amount_paid=cash_collected,
            manual_receipt_no=manual_receipt_no,
            collector_notes=settlement_notes
        )

        # 2. Mark all remaining schedules as PAID
        contract.schedules.filter(status__in=['PENDING', 'PARTIAL', 'OVERDUE']).update(
            remaining_due=Decimal('0.00'),
            status='PAID'
        )

        # 3. Finalize contract and inventory title
        contract.remaining_balance = Decimal('0.00')
        contract.status = 'COMPLETED'
        contract.save()

        contract.serialized_item.status = 'SETTLED_OWNED'
        contract.serialized_item.save(update_fields=['status'])

        return payment