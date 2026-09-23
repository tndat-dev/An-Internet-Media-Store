"""Seed a small AIMS demo catalog and its matching inventory.

Run this file inside the catalog-service container with argument ``catalog``
and inside inventory-service with argument ``inventory``. Re-running it is safe.
"""

from __future__ import annotations

import os
import sys
import uuid
from decimal import Decimal

import psycopg
from psycopg.types.json import Jsonb


PRODUCTS = [
    {
        "id": "10000000-0000-4000-8000-000000000001",
        "title": "Clean Architecture",
        "type": "BOOK",
        "category": "Software Engineering",
        "price": "42000.00",
        "original": "45000.00",
        "barcode": "AIMS-BOOK-001",
        "stock": 18,
        "description": "A practical guide to organizing software systems for long-term maintainability.",
        "image": "https://images.unsplash.com/photo-1544947950-fa07a98d237f?auto=format&fit=crop&w=640&q=80",
        "details": {"authors": ["Robert C. Martin"], "cover_type": "Paperback", "publisher": "Prentice Hall", "publication_date": "2017-09-20"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000002",
        "title": "Designing Data-Intensive Applications",
        "type": "BOOK",
        "category": "Distributed Systems",
        "price": "49000.00",
        "original": "55000.00",
        "barcode": "AIMS-BOOK-002",
        "stock": 14,
        "description": "Reliable, scalable, and maintainable data system design.",
        "image": "https://images.unsplash.com/photo-1532012197267-da84d127e765?auto=format&fit=crop&w=640&q=80",
        "details": {"authors": ["Martin Kleppmann"], "cover_type": "Paperback", "publisher": "O'Reilly Media", "publication_date": "2017-03-16"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000003",
        "title": "Kubernetes: Up and Running",
        "type": "BOOK",
        "category": "Cloud Native",
        "price": "36000.00",
        "original": "42000.00",
        "barcode": "AIMS-BOOK-003",
        "stock": 20,
        "description": "Build and operate reliable distributed systems with Kubernetes.",
        "image": "https://images.unsplash.com/photo-1495446815901-a7297e633e8d?auto=format&fit=crop&w=640&q=80",
        "details": {"authors": ["Brendan Burns", "Joe Beda", "Kelsey Hightower"], "cover_type": "Paperback", "publisher": "O'Reilly Media", "publication_date": "2022-08-16"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000004",
        "title": "Deep Learning with Python",
        "type": "BOOK",
        "category": "Artificial Intelligence",
        "price": "51000.00",
        "original": "58000.00",
        "barcode": "AIMS-BOOK-004",
        "stock": 12,
        "description": "Hands-on deep learning concepts and applications with Python.",
        "image": "https://images.unsplash.com/photo-1512820790803-83ca734da794?auto=format&fit=crop&w=640&q=80",
        "details": {"authors": ["François Chollet"], "cover_type": "Paperback", "publisher": "Manning", "publication_date": "2021-12-21"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000005",
        "title": "The Pragmatic Programmer",
        "type": "BOOK",
        "category": "Software Engineering",
        "price": "39000.00",
        "original": "46000.00",
        "barcode": "AIMS-BOOK-005",
        "stock": 25,
        "description": "Timeless techniques for becoming an effective software developer.",
        "image": "https://images.unsplash.com/photo-1516979187457-637abb4f9353?auto=format&fit=crop&w=640&q=80",
        "details": {"authors": ["David Thomas", "Andrew Hunt"], "cover_type": "Hardcover", "publisher": "Addison-Wesley", "publication_date": "2019-09-13"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000006",
        "title": "Cloud Native Monthly — September",
        "type": "NEWSPAPER",
        "category": "Technology News",
        "price": "7500.00",
        "original": "8000.00",
        "barcode": "AIMS-NEWS-001",
        "stock": 40,
        "description": "Monthly coverage of Kubernetes, platform engineering, and cloud security.",
        "image": "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=640&q=80",
        "details": {"editor_in_chief": "AIMS Editorial", "publisher": "AIMS Media", "publication_date": "2026-09-01"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000007",
        "title": "Jazz for Coding",
        "type": "CD",
        "category": "Music",
        "price": "16000.00",
        "original": "18000.00",
        "barcode": "AIMS-CD-001",
        "stock": 16,
        "description": "A calm instrumental jazz collection for focused work.",
        "image": "https://images.unsplash.com/photo-1461360228754-6e81c478b882?auto=format&fit=crop&w=640&q=80",
        "details": {"artists": ["AIMS Jazz Ensemble"], "record_label": "AIMS Records", "tracklist": ["Morning Build", "Blue Deployment", "Night Commit"], "genre": "Jazz"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000008",
        "title": "Classical Focus",
        "type": "CD",
        "category": "Music",
        "price": "18000.00",
        "original": "21000.00",
        "barcode": "AIMS-CD-002",
        "stock": 10,
        "description": "Orchestral pieces selected for study and concentration.",
        "image": "https://images.unsplash.com/photo-1483412033650-1015ddeb83d1?auto=format&fit=crop&w=640&q=80",
        "details": {"artists": ["AIMS Chamber Orchestra"], "record_label": "AIMS Records", "tracklist": ["Adagio", "Nocturne", "Finale"], "genre": "Classical"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000009",
        "title": "Planet Earth: Ocean Worlds",
        "type": "DVD",
        "category": "Documentary",
        "price": "24000.00",
        "original": "28000.00",
        "barcode": "AIMS-DVD-001",
        "stock": 11,
        "description": "A high-definition journey through the world's oceans.",
        "image": "https://images.unsplash.com/photo-1498623116890-37e912163d5d?auto=format&fit=crop&w=640&q=80",
        "details": {"disc_type": "Blu-ray", "director": "AIMS Nature Unit", "runtime_minutes": 118, "studio": "AIMS Studio", "language": "English", "subtitles": ["English", "Vietnamese"]},
    },
    {
        "id": "10000000-0000-4000-8000-000000000010",
        "title": "The Distributed System",
        "type": "DVD",
        "category": "Education",
        "price": "29000.00",
        "original": "34000.00",
        "barcode": "AIMS-DVD-002",
        "stock": 9,
        "description": "An educational film about modern distributed computing.",
        "image": "https://images.unsplash.com/photo-1485846234645-a62644f84728?auto=format&fit=crop&w=640&q=80",
        "details": {"disc_type": "DVD", "director": "Dat Nguyen", "runtime_minutes": 96, "studio": "AIMS Studio", "language": "Vietnamese", "subtitles": ["English"]},
    },
    {
        "id": "10000000-0000-4000-8000-000000000011",
        "title": "Site Reliability Engineering",
        "type": "BOOK",
        "category": "DevOps",
        "price": "44000.00",
        "original": "50000.00",
        "barcode": "AIMS-BOOK-006",
        "stock": 17,
        "description": "Engineering practices for running dependable production systems.",
        "image": "https://images.unsplash.com/photo-1524995997946-a1c2e315a42f?auto=format&fit=crop&w=640&q=80",
        "details": {"authors": ["Betsy Beyer", "Chris Jones", "Jennifer Petoff", "Niall Richard Murphy"], "cover_type": "Paperback", "publisher": "O'Reilly Media", "publication_date": "2016-04-16"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000012",
        "title": "OCI Architecture Review",
        "type": "NEWSPAPER",
        "category": "Cloud Architecture",
        "price": "6000.00",
        "original": "7000.00",
        "barcode": "AIMS-NEWS-002",
        "stock": 35,
        "description": "Landing zones, hub-spoke networking, OKE, and cloud security patterns.",
        "image": "https://images.unsplash.com/photo-1495020689067-958852a7765e?auto=format&fit=crop&w=640&q=80",
        "details": {"editor_in_chief": "AIMS Cloud Team", "publisher": "AIMS Media", "publication_date": "2026-09-15"},
    },
]


def seed_catalog() -> int:
    url = os.environ["CATALOG_DATABASE_URL"]
    with psycopg.connect(url) as connection:
        for product in PRODUCTS:
            connection.execute(
                """
                INSERT INTO catalog_service.products(
                  product_id,title,product_type,category,price,original_value,height,width,length,
                  weight,barcode,stock_quantity,description,image_url,status,type_details
                ) VALUES (%s,%s,%s,%s,%s,%s,24,18,3,0.6,%s,%s,%s,%s,'ACTIVE',%s)
                ON CONFLICT(product_id) DO UPDATE SET
                  title=excluded.title, product_type=excluded.product_type, category=excluded.category,
                  price=excluded.price, original_value=excluded.original_value, barcode=excluded.barcode,
                  stock_quantity=excluded.stock_quantity, description=excluded.description,
                  image_url=excluded.image_url, status='ACTIVE', type_details=excluded.type_details,
                  updated_at=now()
                """,
                (
                    uuid.UUID(product["id"]), product["title"], product["type"], product["category"],
                    Decimal(product["price"]), Decimal(product["original"]), product["barcode"],
                    product["stock"], product["description"], product["image"], Jsonb(product["details"]),
                ),
            )
    return len(PRODUCTS)


def seed_inventory() -> int:
    url = os.environ["INVENTORY_DATABASE_URL"]
    with psycopg.connect(url) as connection:
        for product in PRODUCTS:
            connection.execute(
                """
                INSERT INTO inventory_service.stock(product_id,available,reserved)
                VALUES (%s,%s,0)
                ON CONFLICT(product_id) DO UPDATE SET available=excluded.available,updated_at=now()
                """,
                (product["id"], product["stock"]),
            )
    return len(PRODUCTS)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"catalog", "inventory"}:
        raise SystemExit("Usage: python seed_catalog.py catalog|inventory")
    mode = sys.argv[1]
    count = seed_catalog() if mode == "catalog" else seed_inventory()
    print(f"Seeded {count} {mode} records")
