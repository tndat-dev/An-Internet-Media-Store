# AIMS — SOLID, Design Patterns và kế hoạch refactor

**Phạm vi:** mã nguồn microservice trong `/home/tndat/An-Internet-Media-Store`, chốt ngày 16/09/2026. Đây là báo cáo thiết kế cho yêu cầu bổ sung của đề bài; không phải tuyên bố mọi extension đã được triển khai. Các ví dụ clothing, E-Book Reader AI, volumetric shipping, gateway mới và SMS/Zalo/push chỉ là kịch bản tương lai.

## 1. Bằng chứng trong mã nguồn và nguyên tắc SOLID

| Đoạn mã | Nguyên tắc / tình trạng | Vì sao sẽ khó mở rộng | Hướng giải quyết |
|---|---|---|---|
| [`services/order-service/app/main.py`](services/order-service/app/main.py), `OrderRuntime` | **S — Single Responsibility**, còn vi phạm một phần | Một lớp sở hữu DB schema, Kafka producer/consumer, outbox, đơn hàng và HTTP workflow. Sửa broker có thể ảnh hưởng state machine; sửa đơn hàng phải đọc nhiều plumbing. | Tách `OrderRepository`, `OrderWorkflow`, `OutboxPublisher`, `PaymentEventConsumer`; inject qua dependency của API. Bước hiện tại chỉ tách shipping policy khỏi HTTP module. |
| [`services/catalog-service/app/main.py`](services/catalog-service/app/main.py), `REQUIRED_TYPE_FIELDS` và `validate_product` | **O — Open/Closed**, chưa đạt | Thêm media E-Book Reader hoặc non-media clothing buộc sửa bảng type và nhánh validation trong core; dễ phá 4 loại đang bán. | `ProductTypeValidator` protocol và registry/factory; mỗi loại mới có module validator/schema riêng. Không thêm clothing/E-Book Reader ở bản này. |
| [`services/payment-service/app/main.py`](services/payment-service/app/main.py), `refund_order`, VietQR/PayPal endpoints | **O** và **D — Dependency Inversion**, chưa đạt | Gateway thứ ba làm logic hoàn tiền và API module có thêm `if provider`; domain lệ thuộc trực tiếp PayPal REST và VietQR HTTP. | `PaymentGateway` interface (`create`, `capture`, `refund`, `supports_refund`) + adapter từng provider; `PaymentService` phụ thuộc interface, registry quyết định provider. Không triển khai gateway mới. |
| [`services/notification-service/app/main.py`](services/notification-service/app/main.py), `deliver` | **O/D**, đã cải thiện seam, chưa hoàn chỉnh delivery | Log-only delivery trước đó nằm trực tiếp trong runtime; gửi email thật hoặc thêm channel sẽ kéo theo sửa consumer. | Đã inject `DeliveryChannel` protocol và `LoggingDeliveryChannel` vào runtime. Adapter SMTP và routing policy là bước sau; bản hiện tại **chưa gửi email thật**. |
| [`services/order-service/app/shipping.py`](services/order-service/app/shipping.py), `WeightStrategy` + `AimsShippingPolicy` | **O/D**, đã cải thiện | `order-service` trước đây tính trọng lượng/tariff trực tiếp trong `main.py`; sửa cách chọn chargeable weight có thể làm đổi HTTP endpoint và invoice. | Strategy hiện tại `ActualWeightStrategy` inject vào policy. Có thể bổ sung một strategy khác sau này mà không đổi tariff hay order endpoint. **Không** triển khai volumetric formula trong lần này. |

**L — Liskov Substitution:** hiện không có hierarchy subtype business đủ rõ để kết luận vi phạm. `WeightStrategy` được kiểm bằng fake strategy trong unit test; cả hai trả `Decimal` không âm theo hợp đồng. Không gán nhãn vi phạm L chỉ để đủ chữ SOLID.

**I — Interface Segregation:** hiện chưa có interface business nhiều phương thức để chứng minh vi phạm. Interface đề xuất `PaymentGateway` nên tách `RefundableGateway` khi một provider không hỗ trợ refund tự động (VietQR), để client thanh toán không bị buộc implement refund giả. Đây là hướng thiết kế, chưa được triển khai.

Các chú thích trong source đặt ngay tại phần shipping refactor và các điểm mở rộng có vấn đề; các row phía trên dùng đường dẫn chính xác để mỗi thành viên chọn use case mình phụ trách. Khi nộp học phần, thay `StudentID`/`StudentName` bằng thông tin cá nhân và xuất hai báo cáo PDF tên `StudentID_StudentName_SOLID.pdf` và `StudentID_StudentName_DesignPatterns.pdf`.

## 2. Thiết kế đã cải thiện và pattern

| Pattern | Đã làm / đề xuất | Lợi ích và giới hạn |
|---|---|---|
| **Strategy** | Đã làm: `WeightStrategy` + `ActualWeightStrategy` + `AimsShippingPolicy` | Quy tắc tariff ở một module thuần domain; weight policy có thể thay thế. Unit test chứng minh một strategy khác không phải sửa tariff. |
| **Transactional Outbox** | Đã làm: order/payment/inventory ghi event cùng DB transaction, publisher chỉ đánh dấu `published_at` sau Kafka ack; publisher được sửa có retry và `FOR UPDATE SKIP LOCKED` | Không mất event khi app crash giữa commit và publish; tránh nhiều replica cùng claim một row. Delivery vẫn *at least once*, consumer cần idempotency. |
| **Adapter** | Đã làm interface notification `DeliveryChannel` và adapter log; PayPal/VietQR HTTP chưa tách | Consumer không cần biết implementation delivery. Tuy nhiên log-only không được coi là email delivery; payment adapter còn là việc tiếp theo. |
| **Facade / API Gateway** | Đã làm: một external route map tới 10 service | Browser không cần biết DNS nội bộ, nhưng gateway không nên chứa nghiệp vụ từng domain. |
| **Registry/Factory** | Đề xuất cho product-type validator và payment gateway | Đăng ký implementation mới không sửa core routing/validation. Chưa triển khai vì đề bổ sung cấm thiết kế/implement tính năng tương lai. |

## 3. Ảnh thiết kế và chuỗi tương tác

- Class diagram shipping đã triển khai: [SVG](docs/design/aims_shipping_class.svg), [PNG](docs/design/aims_shipping_class.png), [PlantUML source](docs/design/aims_shipping_class.puml).
- Sequence diagram checkout hiện tại: [SVG](docs/design/aims_checkout_sequence.svg), [PNG](docs/design/aims_checkout_sequence.png), [PlantUML source](docs/design/aims_checkout_sequence.puml).

Đây là các export tái sinh được từ source text. Repo có các `.asta`/`.png` thiết kế cũ trong `ArchitecturalDesign/`, nhưng máy làm việc không có Astah CLI/app để sửa và export `.asta` tương ứng với refactor này. Vì vậy **chưa** đáp ứng yêu cầu nộp Astah project cập nhật; cần mở sơ đồ source này trong Astah GUI, dựng lại class/sequence và lưu `.asta`, rồi export hình từ Astah. Không gắn nhãn các ảnh PlantUML là “Astah export”.

## 4. Verification và việc còn lại

- Shipping strategy unit test: `PYTHONPATH=services/order-service pytest -q services/order-service/tests` → 7 passed.
- Notification channel injection unit test: `PYTHONPATH=services/notification-service pytest -q services/notification-service/tests` → 5 passed.
- Inventory adjustment integration với PostgreSQL 17 tạm: 4 passed, bao gồm stock `+5 → -5 → 0`.
- Order/payment publisher retry là sửa lỗi live acceptance phát hiện. CI đã ký/attest image, ArgoCD sync promotion `c8ea0ae`, và acceptance run `1789529432` chứng minh event publish, stock reservation, trạng thái đơn, refund/lifecycle; outbox cuối run có 0 unpublished row. Kết luận dựa trên business flow chứ không chỉ `pod Running`.
- Chưa chứng minh 1.000 concurrent users, 300 giờ liên tục, recovery <1 giờ, và đáp ứng latency 2/5 giây. Cần load/soak/chaos test riêng.
