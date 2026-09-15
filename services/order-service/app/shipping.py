"""AIMS shipping policy with a replaceable chargeable-weight strategy.

The current policy deliberately uses actual physical weight only. A future
volumetric-weight requirement can provide another WeightStrategy without
editing order endpoints or the existing tariff calculation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from math import ceil
from typing import Any, Protocol


class WeightStrategy(Protocol):
    def chargeable_weight(self, items: list[dict[str, Any]]) -> Decimal: ...


class ActualWeightStrategy:
    def chargeable_weight(self, items: list[dict[str, Any]]) -> Decimal:
        # Legacy snapshots have no unitWeight; bill at least the first band.
        return sum(
            (max(Decimal(str(item.get("unitWeight", "0.5"))), Decimal("0.5")) * int(item["quantity"]) for item in items),
            Decimal("0"),
        )


@dataclass(frozen=True)
class AimsShippingPolicy:
    weight_strategy: WeightStrategy = field(default_factory=ActualWeightStrategy)

    def calculate(self, province: str, items: list[dict[str, Any]], order_value: Decimal) -> Decimal:
        return self.fee(province, self.weight_strategy.chargeable_weight(items), order_value)

    @staticmethod
    def fee(province: str, weight_kg: Decimal, order_value: Decimal) -> Decimal:
        normalized = " ".join(province.strip().lower().replace(".", "").split())
        if not normalized:
            raise ValueError("Delivery province is required")
        major_cities = {
            "ha noi", "hanoi", "hà nội", "ho chi minh city", "ho chi minh",
            "hồ chí minh", "tp ho chi minh", "tp hồ chí minh", "hcm",
        }
        if normalized in major_cities:
            fee, base_weight = Decimal("22000"), Decimal("3.0")
        else:
            fee, base_weight = Decimal("30000"), Decimal("0.5")
        billable_weight = weight_kg if weight_kg > 0 else Decimal("0.5")
        if billable_weight > base_weight:
            fee += Decimal(ceil((billable_weight - base_weight) / Decimal("0.5"))) * Decimal("2500")
        if order_value > Decimal("100000"):
            fee = max(Decimal("0"), fee - Decimal("25000"))
        return fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


DEFAULT_SHIPPING_POLICY = AimsShippingPolicy()
