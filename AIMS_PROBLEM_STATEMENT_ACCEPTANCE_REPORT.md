# AIMS — kiểm thử theo problem statement

**Nguồn yêu cầu:** đề AIMS/Capstone Lecturer NGUYEN Thi Thu Trang và tài liệu bổ sung SOLID/Design Patterns do người dùng cung cấp. **Môi trường:** kubeadm lab mô phỏng production, namespace `production`, chốt lại ngày 16/09/2026. Đây là status kiểm thử, không phải chứng chỉ production readiness.

## 1. Cách tái chạy

Script [`Programming/k8s/scripts/run-aims-acceptance.sh`](Programming/k8s/scripts/run-aims-acceptance.sh) dùng Keycloak service-account credential trong Kubernetes Secret, tạo một tài khoản tạm có ADMIN/PRODUCT_MANAGER, chạy [`test-aims-problem-statement.py`](Programming/k8s/scripts/test-aims-problem-statement.py), rồi xóa ba user tổng hợp chính xác theo run ID. Script tạo sản phẩm và ba **đơn thanh toán sandbox**; không chạy trên dữ liệu thật. Lệnh trên control-plane:

```bash
cd /home/dat/An-Internet-Media-Store
bash Programming/k8s/scripts/run-aims-acceptance.sh
```

Không in token, password, API secret vào log. Nếu bị ngắt giữa chừng, tìm sản phẩm có `title` bắt đầu `AIMS Acceptance Book ` và `barcode` bắt đầu `ACCEPT-`; dọn qua manager API để giữ audit trail, không xóa rộng theo tên gần đúng.

## 2. Ma trận yêu cầu chức năng

| Nhóm yêu cầu | Kiểm tra/hiện trạng | Kết luận |
|---|---|---|
| Danh sách 20 sản phẩm, tìm kiếm theo title/category, lọc giá, xem chi tiết | Gateway catalog/search HTTP200; danh sách customer <=20; chưa chứng minh ngẫu nhiên thống kê | Đạt phần lớn |
| Product Manager chỉ CRUD media BOOK/NEWSPAPER/CD/DVD, giá 30–150% original, dữ liệu type-specific, history | BOOK valid/invalid price qua API; history create/stock/delete; 3 type còn lại, giới hạn delete 10/batch và 20/ngày chưa nghiệm thu live | Một phần |
| Stock nhận hàng/giảm hàng có lý do; không xóa product còn tồn | Lỗi giảm stock âm trong `INSERT ... ON CONFLICT` đã sửa; PostgreSQL integration và live acceptance đều chứng minh giảm `5 → 0`, sau đó xóa được product | Đạt luồng kiểm thử |
| Admin tài khoản/role đa vai, block/unblock/reset, least privilege | Keycloak ADMIN/PRODUCT_MANAGER claim được kiểm; create/list/roles/block/unblock/reset qua API đạt. Email change notification, audit tới người dùng chưa chứng minh | Một phần |
| Customer guest cart, subtotal không VAT, cảnh báo stock thiếu, sửa/xóa item | Add cart và subtotal đạt; update/remove/stock shortage cần thêm live assertion | Một phần |
| Draft order, delivery validation, VAT 10%, phí theo địa điểm/trọng lượng, miễn phí tối đa 25.000đ khi subtotal >100.000đ | Ha Noi 12.000đ: VAT 1.200đ, delivery 22.000đ, payable 35.200đ; invalid delivery 422; unit test tariff/free shipping đạt. Các tỉnh, weight bands, >100.000đ chưa nghiệm thu live | Một phần |
| VietQR sandbox QR, PayPal Sandbox card/refund | VietQR QR payload và server-authoritative invoice amount đạt; PayPal/VietQR runtime credentials báo configured. PayPal browser approve/capture/refund chưa chạy end-to-end | Một phần |
| Kafka OrderCreated → InventoryReserved → PaymentCompleted, RabbitMQ task ack/DLQ, order PENDING_PROCESSING | Acceptance run `1789529432`: cả ba order reserve stock, VietQR callback phát PaymentCompleted, order sang PENDING_PROCESSING; order/payment outbox cuối run đều 0 unpublished | Đạt luồng kiểm thử |
| Manager approve/reject 30 pending/page, cancel trước approve, refund PayPal tự động/VietQR thủ công | Live test chứng minh approve, customer cancel, manager reject, VietQR `MANUAL_REQUIRED`, manager mark-refunded, và inventory commit/release. Pagination 30 có code nhưng chưa chạy dataset >30; PayPal refund vẫn chưa E2E | Một phần |
| Email invoice/transaction và approve/reject/cancel link | Notification consumer Kafka→RabbitMQ có ack/DLQ, nhưng `LoggingDeliveryChannel` chỉ log, **chưa gửi SMTP email** | Chưa đạt |

## 3. Các yêu cầu phi chức năng

| Chỉ tiêu đề bài | Bằng chứng hiện có | Kết luận |
|---|---|---|
| 1.000 khách đồng thời | k6 smoke nhỏ; chưa chạy 1.000 VU với dữ liệu và SLO đo chính xác | Chưa chứng minh |
| 300 giờ không failure | Pod/rollout Ready chỉ là snapshot; chưa chạy soak 300 giờ | Chưa chứng minh |
| Resume <1 giờ sau sự cố | Velero backup/DR và HA resource có cấu hình; chưa làm fault injection + RTO end-to-end | Chưa chứng minh |
| Response <=2 giây bình thường, <=5 giây peak | Chưa có kết quả p95/p99 dưới profile tải đề bài | Chưa chứng minh |

## 4. Regression đã thực hiện

- `order-service` shipping strategy + VAT: 7 unit tests pass.
- `payment-service`: 6 unit tests pass.
- `api-gateway` Redis limiter: 4 unit tests pass.
- `notification-service` injected channel: 5 unit tests pass.
- `inventory-service` cùng PostgreSQL 17 tạm: 4 tests pass, gồm negative adjustment.
- Live acceptance run cũ `1789471712` đã phát hiện Redis fail-open, outbox unpublished và inventory decrement lỗi. Các bản sửa nằm ở `65aafca`, `e17578a`, được CI build/scan/SBOM/sign/attest và promotion `c8ea0ae` đưa vào cụm.
- Live acceptance run mới `1789529432` tại revision `c8ea0ae` trả `ACCEPTANCE PASS`: identity/admin/catalog/cart/invoice, Redis, Kafka, RabbitMQ-mediated workflow, inventory, VietQR sandbox, approve/cancel/reject và manual refund đều đạt. Sau test: ArgoCD `Synced/Healthy`, 0 pod non-Running, 0 active synthetic acceptance product, 0 `accept-*` test user.

Không quy đổi test pass thành “mọi chức năng hoàn thành”. Các gap ở bảng trên là backlog cần implement hoặc nghiệm thu riêng.
