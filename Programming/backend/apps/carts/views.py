from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import (
    CartItemCreateSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
)
from apps.carts.services import CartService


def _cart_token(request) -> str:
    token = request.headers.get("X-Cart-Token", "").strip()
    if not token:
        raise ValidationError({"cartToken": "X-Cart-Token header is required."})
    return token


def _raise_validation(error: DjangoValidationError) -> None:
    if hasattr(error, "message_dict"):
        payload = {
            field: messages[0] if isinstance(messages, list) and len(messages) == 1 else messages
            for field, messages in error.message_dict.items()
        }
        raise ValidationError(payload)
    raise ValidationError(error.messages)


class CartDetailView(APIView):
    def get(self, request):
        cart = CartService.get_cart(_cart_token(request))
        return Response(CartSerializer(cart).data)


class CartItemCreateView(APIView):
    def post(self, request):
        serializer = CartItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cart = CartService.add_item(
                cart_token=_cart_token(request),
                product_id=str(serializer.validated_data["productId"]),
                quantity=serializer.validated_data["quantity"],
            )
        except ObjectDoesNotExist as error:
            raise NotFound("Product not found.") from error
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    def patch(self, request, item_id):
        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cart = CartService.update_item(
                cart_token=_cart_token(request),
                cart_item_id=item_id,
                quantity=serializer.validated_data["quantity"],
            )
        except ObjectDoesNotExist as error:
            raise NotFound("Cart item not found.") from error
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(CartSerializer(cart).data)

    def delete(self, request, item_id):
        try:
            cart = CartService.remove_item(_cart_token(request), item_id)
        except ObjectDoesNotExist as error:
            raise NotFound("Cart item not found.") from error
        return Response(CartSerializer(cart).data)
