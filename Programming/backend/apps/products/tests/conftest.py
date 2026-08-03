"""
conftest.py — Custom table reporter for AIMS Unit Tests.
Optimized to parse and display a single unified table for PPV_xxx test cases.
"""

import pytest
import re
from tabulate import tabulate

_results: dict[str, list] = {}
_test_meta: dict[str, dict] = {}


def register_meta(tc_id, description, expected):
    """Lưu thông tin mô tả kịch bản để hiển thị lên bảng terminal."""
    _test_meta[tc_id] = {
        "description": description,
        "expected": "Valid (True)" if expected else "Invalid (False)"
    }


def pytest_runtest_logreport(report):
    """Hook của pytest chạy sau khi mỗi test case thực thi xong."""
    if report.when != "call":
        return

    node = report.nodeid  # Ví dụ: path/to/test.py::test_product_price_validation[PPV_001]
    status = "PASSED" if report.passed else "FAILED"

    # Trích xuất mã PPV_xxx nằm bên trong cặp dấu ngoặc vuông
    match = re.search(r"\[(PPV_\d+)\]", node)
    if not match:
        return

    tc_id = match.group(1)   # Lấy ra "PPV_001", "PPV_002", ...
    group = "PPV"            # Gom toàn bộ về một nhóm lớn

    meta = _test_meta.get(tc_id, {})
    description = meta.get("description", "")
    expected    = meta.get("expected", "")

    _results.setdefault(group, []).append((tc_id, description, expected, status))


def pytest_sessionfinish(session, exitstatus):
    if not _results:
        return

    rows = _results.get("PPV")
    if not rows:
        return

    rows.sort(key=lambda x: x[0])

    total   = len(rows)
    passed  = sum(1 for r in rows if r[3] == "PASSED")

    print("\n")
    print(f"  PRODUCT PRICE VALIDATION UNIT TEST RESULTS Sweep — ({passed}/{total} passed)")
    print(tabulate(
        [(r[0], r[1], r[2], r[3]) for r in rows],
        headers=["Test Case ID", "Scenario Description", "Expected Output", "Status"],
        tablefmt="simple",
        colalign=("left", "left", "left", "left"),
    ))
    print()