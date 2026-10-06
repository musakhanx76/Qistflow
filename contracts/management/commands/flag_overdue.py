from datetime import date
from django.core.management.base import BaseCommand
from contracts.models import InstallmentSchedule, InstallmentContract


class Command(BaseCommand):
    help = "Scans installment schedules past their due date and transitions them to OVERDUE status."

    def handle(self, *args, **options):
        today = date.today()

        # 1. Update delinquent schedules
        delinquent_schedules = InstallmentSchedule.objects.filter(
            status__in=['PENDING', 'PARTIAL'],
            due_date__lt=today,
            remaining_due__gt=0
        )
        updated_schedules_count = delinquent_schedules.update(status='OVERDUE')

        # 2. Flag contracts that contain overdue schedules
        overdue_contract_ids = InstallmentSchedule.objects.filter(
            status='OVERDUE'
        ).values_list('contract_id', flat=True).distinct()

        updated_contracts_count = InstallmentContract.objects.filter(
            id__in=overdue_contract_ids,
            status='ACTIVE'
        ).update(status='DEFAULTED')

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully flagged {updated_schedules_count} schedule(s) as OVERDUE "
                f"across {updated_contracts_count} contract(s)."
            )
        )