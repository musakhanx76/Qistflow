from decimal import Decimal
from django.db.models import Q
from django.db import transaction, IntegrityError
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from catalog_customers.models import Customer, SerializedItem, Shop
from .models import InstallmentContract
from .services import PaymentService
from .serializers import (
    Customer360Serializer,
    CreateContractSerializer,
    ContractOverviewSerializer
)


class CustomerSearchView(APIView):
    """
    GET /api/v1/customers/search/?q=<query>&shop_id=<id>
    Returns customer details, active contracts, and repayment status.
    """
    def get(self, request):
        query = request.query_params.get('q', '').strip()
        shop_id = request.query_params.get('shop_id')

        if not query:
            return Response(
                {"error": "Query parameter 'q' is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        customers = Customer.objects.all()
        if shop_id:
            customers = customers.filter(shop_id=shop_id)

        customers = customers.filter(
            Q(phone_primary__icontains=query) |
            Q(national_id__icontains=query) |
            Q(full_name__icontains=query) |
            Q(customer_id__icontains=query)
        ).prefetch_related('contracts__schedules', 'contracts__serialized_item__product')

        serializer = Customer360Serializer(customers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RecordPaymentAPIView(APIView):
    """
    POST /api/v1/payments/collect/
    Allocates cash counter receipts across schedules via FIFO.
    """
    def post(self, request):
        contract_identifier = request.data.get('contract_id')
        amount_raw = request.data.get('amount')
        manual_receipt_no = request.data.get('manual_receipt_no')
        notes = request.data.get('collector_notes', '')

        if not all([contract_identifier, amount_raw, manual_receipt_no]):
            return Response(
                {"error": "contract_id (or contract_number), amount, and manual_receipt_no are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        contract = InstallmentContract.objects.filter(
            Q(contract_number=str(contract_identifier)) |
            (Q(id=contract_identifier) if str(contract_identifier).isdigit() else Q())
        ).first()

        if not contract:
            return Response(
                {"error": f"Contract '{contract_identifier}' not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            amount = Decimal(str(amount_raw))
        except Exception:
            return Response({"error": "Invalid amount format."}, status=status.HTTP_400_BAD_REQUEST)

        receipt_slip = str(manual_receipt_no).strip()

        try:
            payment = PaymentService.record_payment(
                contract=contract,
                amount=amount,
                manual_receipt_no=receipt_slip,
                notes=notes
            )
        except ValidationError as e:
            msg = e.message_dict if hasattr(e, 'message_dict') else (e.message if hasattr(e, 'message') else str(e))
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            return Response(
                {"error": f"Receipt slip '{receipt_slip}' has already been recorded for Contract {contract.contract_number}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({
            "message": "Payment recorded successfully.",
            "payment_id": payment.id,
            "contract_number": contract.contract_number,
            "contract_remaining_balance": str(contract.remaining_balance),
            "contract_status": contract.status
        }, status=status.HTTP_201_CREATED)

class CreateContractAPIView(APIView):
    """
    POST /api/v1/contracts/create/
    Creates a new installment contract, calculates schedules, and locks inventory.
    """
    @transaction.atomic
    def post(self, request):
        serializer = CreateContractSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # 1. Verify Shop
        try:
            shop = Shop.objects.get(id=data['shop_id'])
        except Shop.DoesNotExist:
            return Response(
                {"error": f"Shop with ID {data['shop_id']} does not exist."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 2. Verify Customer (matches DB id OR customer_id code)
        customer = Customer.objects.filter(
            Q(id=data['customer_id']) | Q(customer_id=str(data['customer_id'])),
            shop=shop
        ).first()

        if not customer:
            return Response(
                {"error": f"Customer '{data['customer_id']}' not found in Shop {shop.name}."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 3. Verify Serialized Item with database row lock
        item = SerializedItem.objects.select_for_update().filter(
            Q(id=data['serialized_item_id']) | Q(serial_number=str(data['serialized_item_id'])),
            product__shop=shop
        ).first()

        if not item:
            return Response(
                {"error": f"Serialized item '{data['serialized_item_id']}' not found in Shop {shop.name}."},
                status=status.HTTP_404_NOT_FOUND
            )

        if item.status != 'IN_STOCK':
            return Response(
                {"error": f"Item '{item.serial_number}' is not available (Current status: {item.status})."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Create Contract & Generate Schedules
        try:
            contract = InstallmentContract.objects.create(
                shop=shop,
                customer=customer,
                serialized_item=item,
                contract_number=data['contract_number'],
                tenure_months=data['tenure_months'],
                product_cash_price=data['product_cash_price'],
                down_payment=data['down_payment'],
                markup_percentage=data['markup_percentage'],
                status='ACTIVE'
            )
        except ValidationError as e:
            msg = e.message_dict if hasattr(e, 'message_dict') else (e.message if hasattr(e, 'message') else str(e))
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)

        output_serializer = ContractOverviewSerializer(contract)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)