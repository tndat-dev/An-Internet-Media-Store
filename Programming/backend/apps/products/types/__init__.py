"""Product subtype strategies + registry (Strategy + Registry pattern).

Importing this package self-registers all four subtype strategies. ``services``,
``serializers`` and ``selectors`` import this module, and those load at app
import time (via ``urls`` -> ``views``), so the registry is always populated
before any request — the products app has no ``AppConfig.ready`` hook to rely on.
"""

from apps.products.types.registry import ProductTypeRegistry
from apps.products.types import book, cd, dvd, newspaper  # noqa: F401  (import triggers register())

__all__ = ["ProductTypeRegistry"]
