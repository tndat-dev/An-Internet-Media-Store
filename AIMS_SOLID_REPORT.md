# AIMS — báo cáo SOLID

**Bản dùng để đổi tên khi nộp:** `StudentID_StudentName_SOLID.pdf`  
**Phạm vi:** refactor thiết kế hiện tại; không triển khai clothing, E-Book Reader AI, volumetric shipping, payment gateway mới hay SMS/Zalo/push.

## S — Single Responsibility Principle

`services/order-service/app/main.py::OrderRuntime` hiện còn sở hữu kết nối DB, Kafka producer/consumer, outbox và state transition. Một thay đổi broker hoặc persistence có thể làm lớp nghiệp vụ đổi theo. Hướng tiếp theo là tách `OrderRepository`, `OrderWorkflow`, `OutboxPublisher` và `PaymentEventConsumer`. Bước refactor đã làm là đưa chính sách giao hàng thuần domain sang `services/order-service/app/shipping.py`, để endpoint không còn sở hữu cả thuật toán trọng lượng/tariff.

## O — Open/Closed Principle

- `services/catalog-service/app/main.py::REQUIRED_TYPE_FIELDS` và `validate_product`: thêm loại sản phẩm buộc sửa bảng/nhánh trung tâm. Hướng giải quyết là `ProductTypeValidator` protocol và registry/factory; mỗi product type đăng ký validator riêng. Chưa thêm loại tương lai.
- `services/payment-service/app/main.py::refund_order`: `if VIETQR`/`if PAYPAL` khiến thêm gateway phải sửa core workflow. Hướng giải quyết là `PaymentGateway` và adapter provider.
- Shipping đã cải thiện: `AimsShippingPolicy` nhận `WeightStrategy`; thay cách xác định chargeable weight bằng implementation mới mà không sửa order endpoint hay tariff hiện tại.
- Notification đã cải thiện: `NotificationRuntime` nhận `DeliveryChannel`; Kafka/RabbitMQ consumer không cần sửa khi thay adapter log bằng adapter gửi thật.

## L — Liskov Substitution Principle

Không gắn nhãn vi phạm L cho một hierarchy không tồn tại. `WeightStrategy` là hợp đồng có thể thay thế; unit test inject fake strategy và policy vẫn trả đúng phí. Khi bổ sung implementation, mọi strategy phải trả `Decimal` chargeable weight hợp lệ và không làm thay đổi ý nghĩa input items.

## I — Interface Segregation Principle

Payment trong tương lai nên tách `PaymentGateway` khỏi `RefundableGateway`: VietQR không hỗ trợ refund API, nên không bị buộc implement phương thức refund giả. Tương tự, notification adapter chỉ cần `send(event)`; Kafka lifecycle không rò rỉ vào channel interface.

## D — Dependency Inversion Principle

- Đã làm: `AimsShippingPolicy` phụ thuộc `WeightStrategy` protocol; `NotificationRuntime` phụ thuộc `DeliveryChannel` protocol.
- Chưa làm: payment domain còn gọi PayPal/VietQR HTTP trực tiếp; catalog còn phụ thuộc danh sách concrete type. Các adapter/registry ở trên là hướng xử lý.

## Bằng chứng

- Shipping tests: 7 passed.
- Notification channel injection: 5 passed.
- Inventory/PostgreSQL integration: 4 passed.
- Acceptance live `1789529432`: PASS business flow tại GitOps promotion `c8ea0ae`.

Các comment SOLID nằm trực tiếp tại `shipping.py`, catalog type table, payment refund branch và notification channel. Báo cáo không tuyên bố các feature tương lai đã được thiết kế/implement.
