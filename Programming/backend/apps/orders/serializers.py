from decimal import Decimal

from rest_framework import serializers

from apps.orders.models import DeliveryInfo, Invoice, Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    orderItemId = serializers.UUIDField(source="order_item_id", read_only=True)
    productId = serializers.UUIDField(source="product.product_id", read_only=True)
    productTitle = serializers.CharField(source="product_title", read_only=True)
    unitPrice = serializers.DecimalField(source="unit_price", max_digits=14, decimal_places=2, read_only=True)
    lineAmountExclVat = serializers.DecimalField(source="line_amount_excl_vat", max_digits=14, decimal_places=2, read_only=True)
    lineAmountInclVat = serializers.DecimalField(source="line_amount_incl_vat", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "orderItemId",
            "productId",
            "productTitle",
            "unitPrice",
            "quantity",
            "lineAmountExclVat",
            "lineAmountInclVat",
        ]


class DeliveryInfoSerializer(serializers.ModelSerializer):
    deliveryInfoId = serializers.UUIDField(source="delivery_info_id", read_only=True)
    customerName = serializers.CharField(source="customer_name", read_only=True)
    phoneNumber = serializers.CharField(source="phone_number", read_only=True)
    deliveryProvince = serializers.CharField(source="delivery_province", read_only=True)
    deliveryAddress = serializers.CharField(source="delivery_address", read_only=True)
    deliveryMethod = serializers.CharField(source="delivery_method", read_only=True)
    deliveryInstructions = serializers.CharField(source="delivery_instructions", read_only=True)
    shippingFee = serializers.DecimalField(source="shipping_fee", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = DeliveryInfo
        fields = [
            "deliveryInfoId",
            "customerName",
            "phoneNumber",
            "email",
            "deliveryProvince",
            "deliveryAddress",
            "deliveryMethod",
            "deliveryInstructions",
            "shippingFee",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    invoiceId = serializers.UUIDField(source="invoice_id", read_only=True)
    orderId = serializers.UUIDField(source="order.order_id", read_only=True)
    orderToken = serializers.UUIDField(source="order.order_view_token", read_only=True)
    status = serializers.CharField(source="order.status", read_only=True)
    items = OrderItemSerializer(source="order.items", many=True, read_only=True)
    deliveryInfo = DeliveryInfoSerializer(source="order.delivery_info", read_only=True)
    subtotalExclVat = serializers.DecimalField(source="total_product_price_excl_vat", max_digits=14, decimal_places=2, read_only=True)
    vatAmount = serializers.DecimalField(source="vat_amount", max_digits=14, decimal_places=2, read_only=True)
    totalInclVat = serializers.DecimalField(source="total_product_price_incl_vat", max_digits=14, decimal_places=2, read_only=True)
    deliveryFee = serializers.DecimalField(source="delivery_fee", max_digits=14, decimal_places=2, read_only=True)
    totalAmountToPay = serializers.DecimalField(source="total_amount_to_pay", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "invoiceId",
            "orderId",
            "orderToken",
            "status",
            "items",
            "deliveryInfo",
            "subtotalExclVat",
            "vatAmount",
            "totalInclVat",
            "deliveryFee",
            "totalAmountToPay",
        ]


class OrderSerializer(serializers.ModelSerializer):
    orderId = serializers.UUIDField(source="order_id", read_only=True)
    orderToken = serializers.UUIDField(source="order_view_token", read_only=True)
    cancelToken = serializers.UUIDField(source="cancel_token", read_only=True)
    totalAmount = serializers.DecimalField(source="total_amount", max_digits=14, decimal_places=2, read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    deliveryInfo = serializers.SerializerMethodField()
    invoice = serializers.SerializerMethodField()
    refundSummary = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "orderId",
            "orderToken",
            "cancelToken",
            "status",
            "totalAmount",
            "items",
            "deliveryInfo",
            "invoice",
            "refundSummary",
            "createdAt",
            "updatedAt",
        ]

    def get_deliveryInfo(self, order: Order) -> dict | None:
        if not hasattr(order, "delivery_info"):
            return None
        return DeliveryInfoSerializer(order.delivery_info).data

    def get_invoice(self, order: Order) -> dict | None:
        if not hasattr(order, "invoice"):
            return None
        invoice = order.invoice
        return {
            "invoiceId": str(invoice.invoice_id),
            "subtotalExclVat": f"{Decimal(invoice.total_product_price_excl_vat):.2f}",
            "vatAmount": f"{Decimal(invoice.vat_amount):.2f}",
            "totalInclVat": f"{Decimal(invoice.total_product_price_incl_vat):.2f}",
            "deliveryFee": f"{Decimal(invoice.delivery_fee):.2f}",
            "totalAmountToPay": f"{Decimal(invoice.total_amount_to_pay):.2f}",
        }

    def get_refundSummary(self, order: Order) -> dict | None:
        from apps.payments.models import PaymentTransaction

        payment = (
            PaymentTransaction.objects.filter(order=order)
            .prefetch_related("refunds")
            .order_by("-transaction_datetime")
            .first()
        )
        if payment is None:
            return None

        refund = payment.refunds.order_by("-created_at").first()
        payload = {
            "paymentMethod": payment.gateway,
            "paymentStatus": payment.status,
            "paymentAmount": f"{Decimal(payment.amount):.2f}",
            "paymentCurrency": payment.currency,
            "captureId": payment.capture_id,
            "refundId": payment.refund_id,
        }
        if refund is None:
            return payload

        payload.update(
            {
                "refundStatus": refund.refund_status,
                "refundMethod": refund.refund_method,
                "refundAmount": f"{Decimal(refund.refund_amount):.2f}",
                "refundCurrency": "VND",
                "refundReason": refund.refund_reason,
                "manualRefundNote": refund.manual_refund_note,
                "processedBy": refund.processed_by.username if refund.processed_by else None,
                "processedAt": refund.processed_at.isoformat() if refund.processed_at else None,
                "createdAt": refund.created_at.isoformat() if refund.created_at else None,
            }
        )
        return payload


class ManagerOrderSerializer(OrderSerializer):
    """Order view for the manager review queue: adds who/when it was processed."""

    processedAt = serializers.DateTimeField(source="processed_at", read_only=True)
    processedBy = serializers.CharField(source="processed_by.username", read_only=True, default=None)

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + ["processedAt", "processedBy"]


class DeliveryInfoInputSerializer(serializers.Serializer):
    customerName = serializers.CharField(max_length=30, allow_blank=True)
    phoneNumber = serializers.CharField(max_length=30, allow_blank=True)
    email = serializers.CharField(allow_blank=True)
    deliveryProvince = serializers.CharField(max_length=100, allow_blank=True)
    deliveryAddress = serializers.CharField(max_length=100, allow_blank=True)
    deliveryMethod = serializers.ChoiceField(choices=["STANDARD", "EXPRESS"], required=False, default="STANDARD")
    deliveryInstructions = serializers.CharField(required=False, allow_blank=True)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        return {
            "name": values["customerName"],
            "phone": values["phoneNumber"],
            "email": values["email"],
            "province": values["deliveryProvince"],
            "address": values["deliveryAddress"],
            "delivery_method": values.get("deliveryMethod", "STANDARD"),
            "delivery_instructions": values.get("deliveryInstructions", ""),
        }


class OrderConfirmSerializer(serializers.Serializer):
    orderId = serializers.UUIDField()


class DeliveryPreviewInputSerializer(serializers.Serializer):
    province = serializers.CharField(max_length=100)
    deliveryMethod = serializers.ChoiceField(choices=["STANDARD", "EXPRESS"], required=False, default="STANDARD")
