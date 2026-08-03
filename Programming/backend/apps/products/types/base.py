"""Strategy abstraction for AIMS product subtypes.

Each media subtype (Book / CD / DVD / Newspaper) owns its model, reverse
accessor, allowed / required / enum fields, and the validate / normalize / sync /
serialize behaviour. This replaces the per-type knowledge that used to be
duplicated across ``services.TYPE_DETAIL_CONFIG``,
``serializers.serialize_type_details`` and ``selectors._with_type_details``.

Design note: **Strategy + Registry pattern**. Adding a new product type means
adding one ``ProductTypeStrategy`` subclass and registering it — no edits to
create / update / delete / serialize / prefetch (Open/Closed Principle). See the
Design Patterns report.

Strategies import ONLY from ``apps.products.models`` (and Django) so they stay
free of the services / serializers layers — this keeps the dependency direction
clean and avoids circular imports.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models


def is_blank(value) -> bool:
    """A value counts as 'not provided' when it is None or whitespace-only text."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _normalize_token(value) -> str:
    """Lower-case and drop non-alphanumerics so 'Hard Cover' == 'hardcover'."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


class ProductTypeStrategy:
    """Base strategy. Concrete subtypes set the class attributes below; the
    default, field-driven method implementations cover all current types, so a
    new type usually needs no method overrides."""

    product_type: str = ""                      # ProductType value, e.g. ProductType.BOOK
    model: type[models.Model] | None = None     # the extension model, e.g. Book
    related_name: str = ""                       # reverse accessor on Product, e.g. "book_details"
    allowed_fields: frozenset[str] = frozenset()
    required_fields: tuple[str, ...] = ()
    enum_fields: dict[str, list[str]] = {}       # field -> list of canonical labels

    def validate_required(self, details: dict | None, *, require_all: bool) -> list[str]:
        """Return the required field names that are missing.

        On create / type-change (``require_all=True``) every required field must
        be present and non-blank. On a partial same-type update only reject
        required fields that are explicitly provided but blank. (Returns the
        missing list; the caller decides how to raise — keeps this class free of
        the HTTP/error-shape contract.)
        """
        details = details or {}
        missing: list[str] = []
        for field in self.required_fields:
            provided = field in details
            if require_all and not provided:
                missing.append(field)
            elif provided and is_blank(details.get(field)):
                missing.append(field)
        return missing

    def normalize_enums(self, details: dict) -> list[str]:
        """Validate closed-enumeration fields and normalise accepted values to
        their canonical label IN PLACE. Return a list of error messages (empty
        when valid). Blank values are left for the required-field check."""
        errors: list[str] = []
        for field, allowed in self.enum_fields.items():
            if field not in details or is_blank(details.get(field)):
                continue
            key = _normalize_token(details[field])
            match = next((option for option in allowed if _normalize_token(option) == key), None)
            if match is None:
                errors.append(f"{field} must be one of: {', '.join(allowed)}.")
            else:
                details[field] = match
        return errors

    def sync(self, *, product, details: dict | None) -> None:
        """Create or update this product's subtype row from ``details``.

        Filters to ``allowed_fields``, normalises enums, then upserts. Raises
        ``ValidationError({"type_details": [...]})`` on a bad enum value to
        preserve the exact pre-refactor error shape.
        """
        clean = {key: value for key, value in (details or {}).items() if key in self.allowed_fields}
        errors = self.normalize_enums(clean)
        if errors:
            raise ValidationError({"type_details": errors})
        self.model.objects.update_or_create(product=product, defaults=clean)

    def serialize(self, product) -> dict:
        """Return the subtype detail dict for API output (dates as ISO strings);
        ``{}`` when the subtype row is absent."""
        if not hasattr(product, self.related_name):
            return {}
        related = getattr(product, self.related_name)
        details: dict = {}
        for field in related._meta.fields:
            if field.name in {"id", "product"}:
                continue
            value = getattr(related, field.name)
            details[field.name] = value.isoformat() if hasattr(value, "isoformat") else value
        return details
