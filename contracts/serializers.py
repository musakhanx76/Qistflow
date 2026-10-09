from decimal import Decimal
from rest_framework import serializers
from .models import InstallmentContract, InstallmentSchedule, Payment
from catalog_customers.models import Customer, SerializedItem


class InstallmentScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstallmentSchedule
        fields = [
            'id',
            'installment_number',
            'due_date',
            'expected_amount',
            'paid_amount',
            'remaining_due',
            'status',
        ]


class ContractOverviewSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='serialized_item.product.model_name', read_only=True)
    serial_number = serializers.CharField(source='serialized_item.serial_number', read_only=True)
    schedules = InstallmentScheduleSerializer(many=True, read_only=True)

    class Meta:
        model = InstallmentContract
        fields = [
            'id',
            'contract_number',
            'product_name',
            'serial_number',
            'start_date',
            'tenure_months',
            'monthly_installment',
            'total_financed_payable',
            'remaining_balance',
            'status',
            'schedules',
        ]


class Customer360Serializer(serializers.ModelSerializer):
    contracts = ContractOverviewSerializer(many=True, read_only=True)
    total_active_debt = serializers.SerializerMethodField()
    overdue_count = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id',
            'customer_id',
            'full_name',
            'phone_primary',
            'national_id',
            'home_address',
            'total_active_debt',
            'overdue_count',
            'contracts',
        ]

    def get_total_active_debt(self, obj):
        return sum(c.remaining_balance for c in obj.contracts.filter(status='ACTIVE'))

    def get_overdue_count(self, obj):
        return InstallmentSchedule.objects.filter(
            contract__customer=obj,
            status='OVERDUE'
        ).count()


class CreateContractSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    customer_id = serializers.IntegerField()
    serialized_item_id = serializers.IntegerField()
    contract_number = serializers.CharField(max_length=50)
    tenure_months = serializers.IntegerField()
    product_cash_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    down_payment = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    markup_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))