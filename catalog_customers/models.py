from django.db import models
from django.core.validators import RegexValidator

class Shop(models.Model):
    """Multi-tenant isolation: Each business has its own data."""
    name = models.CharField(max_length=150)
    owner_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='customers')
    customer_id = models.CharField(max_length=30, db_index=True)  # e.g., CUST-1001
    full_name = models.CharField(max_length=120)
    phone_primary = models.CharField(max_length=20, db_index=True)
    phone_secondary = models.CharField(max_length=20, blank=True, null=True)
    national_id = models.CharField(
        max_length=15, 
        db_index=True,
        validators=[
            RegexValidator(
                regex=r'^\d{5}-\d{7}-\d{1}$',
                message='National ID must be in the format XXXXX-XXXXXXX-X',
                code='invalid_national_id'
            )
        ],
        help_text="Format: XXXXX-XXXXXXX-X"
    )
    home_address = models.TextField()
    workplace_address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Enforce unique customer IDs and National IDs per shop
        constraints = [
            models.UniqueConstraint(fields=['shop', 'customer_id'], name='unique_customer_per_shop'),
            models.UniqueConstraint(fields=['shop', 'national_id'], name='unique_national_id_per_shop'),
        ]

    def __str__(self):
        return f"{self.customer_id} - {self.full_name}"


class Guarantor(models.Model):
    """Guarantor details are critical for appliance installment recovery."""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='guarantors')
    full_name = models.CharField(max_length=120)
    relationship = models.CharField(max_length=50)  # e.g., Brother, Neighbor, Employer
    phone = models.CharField(max_length=20)
    national_id = models.CharField(
        max_length=15,
        validators=[
            RegexValidator(
                regex=r'^\d{5}-\d{7}-\d{1}$',
                message='National ID must be in the format XXXXX-XXXXXXX-X',
                code='invalid_national_id'
            )
        ],
        help_text="Format: XXXXX-XXXXXXX-X"
    )
    home_address = models.TextField()

    def __str__(self):
        return f"Guarantor: {self.full_name} for {self.customer.full_name}"


class Product(models.Model):
    """Master product catalog (e.g., Haier Inverter AC 1.5 Ton)."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='products')
    brand = models.CharField(max_length=80)
    model_name = models.CharField(max_length=150)
    category = models.CharField(
        max_length=50,
        choices=[
            ('REFRIGERATOR', 'Refrigerator'),
            ('WASHING_MACHINE', 'Washing Machine'),
            ('OVEN', 'Microwave / Oven'),
            ('MOBILE', 'Mobile Phone'),
            ('AIR_CONDITIONER', 'Air Conditioner'),
            ('OTHER', 'Other Appliance'),
        ]
    )
    cost_price = models.DecimalField(max_digits=12, decimal_places=2)  # Purchase cost
    cash_price = models.DecimalField(max_digits=12, decimal_places=2)  # Standard cash selling price

    def __str__(self):
        return f"{self.brand} {self.model_name}"


class SerializedItem(models.Model):
    """Individual physical unit with its exact Serial Number or IMEI."""
    STATUS_CHOICES = [
        ('IN_STOCK', 'In Stock'),
        ('ALLOCATED_TO_INSTALLMENT', 'Sold on Installment'),
        ('SOLD_CASH', 'Sold Cash'),
        ('DEFECTIVE', 'Defective / Returned'),
    ]

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='serialized_units')
    serial_number = models.CharField(max_length=100, db_index=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='IN_STOCK')
    received_date = models.DateField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['product', 'serial_number'], name='unique_serial_per_product'),
        ]

    def __str__(self):
        return f"{self.product.model_name} (SN: {self.serial_number}) - {self.status}"