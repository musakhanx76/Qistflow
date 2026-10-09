from django.urls import path
from .views import CustomerSearchView, RecordPaymentAPIView, CreateContractAPIView

urlpatterns = [
    path('customers/search/', CustomerSearchView.as_view(), name='api_customer_search'),
    path('payments/collect/', RecordPaymentAPIView.as_view(), name='api_payment_collect'),
    path('contracts/create/', CreateContractAPIView.as_view(), name='api_contract_create'),
]