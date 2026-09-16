# AIMS — báo cáo Design Patterns

**Bản dùng để đổi tên khi nộp:** `StudentID_StudentName_DesignPatterns.pdf`  
**Ngày chốt:** 16/09/2026

## Thiết kế đã cải thiện

1. **Strategy — shipping:** `WeightStrategy`, `ActualWeightStrategy` và `AimsShippingPolicy` tách cách chọn trọng lượng tính phí khỏi tariff/order endpoint. Kịch bản volumetric weight là input phân tích, chưa được triển khai.
2. **Adapter + Dependency Injection — notification:** `NotificationRuntime(channel=...)` gọi `DeliveryChannel.send`. `LoggingDeliveryChannel` là adapter lab và không được coi là email đã gửi. SMTP/SMS/Zalo/push chưa triển khai.
3. **Transactional Outbox:** order/payment/inventory ghi event cùng transaction DB. Publisher retry, timeout và claim row bằng `FOR UPDATE SKIP LOCKED`; chỉ đặt `published_at` sau Kafka ack. Consumer vẫn phải idempotent vì delivery là at-least-once.
4. **Facade/API Gateway:** browser gọi một API boundary; route map tới service owner, tránh phụ thuộc DNS nội bộ.
5. **Registry/Factory (đề xuất):** product-type validators và payment gateways nên đăng ký implementation; không thêm feature tương lai trong scope refactor này.

## Vì sao pattern phù hợp với thay đổi tương lai

| Requirement change dùng để đánh giá | Pattern/hướng áp dụng | Tác động tới core hiện tại |
|---|---|---|
| Thay cách tính chargeable weight | Strategy | Thêm implementation, giữ `AimsShippingPolicy`/endpoint |
| Thêm payment provider | Adapter + Factory/Registry | Thêm adapter; không thêm nhánh vào refund workflow |
| Thêm notification channel | Adapter + routing policy | Thêm channel; Kafka/RabbitMQ consumer không đổi |
| Thêm product type | Validator registry/factory | Thêm schema/validator module; không sửa bảng `if` trung tâm |

## Class và sequence diagram

- Shipping class: `docs/design/aims_shipping_class.puml`, `.svg`, `.png`.
- Checkout sequence: `docs/design/aims_checkout_sequence.puml`, `.svg`, `.png`.

Checkout sequence phản ánh implementation live: Gateway → Cart/Order → shipping policy → transactional outbox → Kafka → Inventory → Payment/RabbitMQ → PaymentCompleted → Order/Notification. Acceptance `1789529432` chứng minh reserve, payment transition và lifecycle commit/release.

Repo có `.asta` cũ trong `ArchitecturalDesign`, nhưng workstation không có Astah GUI/CLI để cập nhật hợp lệ. Các hình mới là PlantUML export tái sinh được, **không giả mạo là Astah export**. Trước khi nộp yêu cầu Astah, import/dựng hai sơ đồ này trong Astah, lưu project `.asta` và export ảnh từ chính Astah.
