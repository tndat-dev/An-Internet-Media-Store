# Design Patterns Và Nguyên Tắc Thiết Kế Trong PayPal Flow

## 0. Kết luận ngắn trước

Nếu bạn chỉ cần một câu để thuyết minh: code này đang đi theo hướng tách rõ boundary, dùng service để giữ nghiệp vụ, gateway để chạm PayPal, registry để chọn provider, và entity để lưu state giao dịch.

## 1. Các pattern đang có trong code

### Thin Controller

- Áp dụng ở `apps/payments/views.py`.
- View chỉ validate, gọi service và trả response.
- Điều này giúp controller không phình thành nơi chứa business rule.
- Trong flow này, `views.py` chỉ nên là lớp tiếp nhận request và xuất response.

### Service Layer

- `PaymentService`, `PaymentLifecycleService`, `PaymentCompletionService` và `OrderPlacementService` là các lớp service.
- Mỗi lớp giữ một phần nghiệp vụ rõ ràng.
- UI và DRF view không nên tự quyết định state transition.
- Đây là lý do bạn sẽ thấy `PaymentService`, `PaymentLifecycleService`, `PaymentCompletionService`, `OrderPlacementService` thay vì nhồi hết vào một view.

### DTO / Data Transfer Object

- `InitiatePaymentRequest`, `CapturePaymentRequest`, `InitiatePaymentResponse`, `CapturePaymentResponse` là DTO ở backend.
- `InitiatePayPalPaymentRequest`, `CapturePayPalPaymentResponse` là DTO ở frontend.
- DTO làm cho contract giữa các lớp rõ ràng và nhẹ.
- Dấu hiệu nhận biết DTO là các class/dataclass chỉ mang dữ liệu, không mang orchestration.

### Factory / Registry

- `PaymentProviderRegistry` quyết định provider nào được dùng cho từng capability.
- Đây là điểm mở rộng hợp lý khi thêm gateway mới.
- Nếu cần thêm Stripe hoặc gateway khác, registry là một trong những nơi đầu tiên phải chỉnh.

### Strategy theo capability interface

- `PaymentInitiator`, `PaymentCapturer`, `RefundProcessor` trong `gateways/base.py` là các interface năng lực.
- `PaymentService` chỉ phụ thuộc vào capability, không phụ thuộc trực tiếp vào PayPal.
- Cách này gần với Strategy, nhưng ở mức capability interface.
- `PaymentService` không cần biết provider nào đang được chọn; nó chỉ cần một đối tượng đáp ứng capability.

### Gateway / Adapter

- `PayPalGateway` bọc toàn bộ chi tiết PayPal REST API.
- Nó chuyển request nội bộ của AIMS sang payload PayPal và chuyển response PayPal về DTO của hệ thống.
- Đây là lớp bạn thay nếu đổi nhà cung cấp thanh toán.
- Đây cũng là lớp có rủi ro integration cao nhất vì gắn trực tiếp với payload và HTTP contract bên ngoài.

### State Transition Service

- `PaymentLifecycleService` là nơi đổi trạng thái giao dịch.
- `PaymentTransaction.mark_success()` và `mark_refunded()` là các helper dữ liệu đi kèm.
- Không để view tự set status trực tiếp.
- Đây là điểm quan trọng nhất để tránh trạng thái bị set rải rác khắp nơi.

### Facade-ish completion seam

- `PaymentCompletionService` gom hai việc: cập nhật trạng thái payment và kích hoạt hoàn tất đơn hàng.
- Nó hoạt động như một seam nghiệp vụ ở điểm thanh toán thành công.
- Về mặt đọc code, đây là cửa ngõ để bạn hiểu payment success thực sự làm những gì tiếp theo.

### Pure Display Component

- `PaymentResult` chỉ render.
- Nó không biết PayPal, không biết capture API, không biết order fulfillment.
- Nếu component nào bắt đầu gọi API hoặc set business state, nó không còn là pure display component nữa.

## 2. Vì sao các pattern này phù hợp với use case này

- Thanh toán có nhiều boundary ngoài: frontend, backend, PayPal.
- Nếu không tách lớp, logic rất dễ dồn hết vào component hoặc view.
- Khi tách theo pattern, bạn có thể kiểm thử từng phần độc lập.
- Provider đổi từ PayPal sang gateway khác thì phần thay đổi chủ yếu nằm ở registry và gateway.
- Flow này có nhiều ngoại vi nên tách lớp là cách duy trì testability tốt nhất.

## 2.1 Bảng đọc nhanh

| Pattern | Nằm ở đâu | Mục đích | Khi đọc nên chú ý |
| --- | --- | --- | --- |
| Thin Controller | `views.py` | Nhận request và trả response | Có đang chứa business rule không |
| Service Layer | `services.py`, `completion_service.py`, `lifecycle_service.py` | Orchestration nghiệp vụ | Service nào sở hữu state transition |
| DTO | `services.py`, `types/payment.ts`, `serializers.py` | Trao đổi dữ liệu nhẹ | Field nào thực sự đi qua boundary |
| Registry/Factory | `provider_registry.py` | Chọn provider theo capability | Gateway nào được tạo ra |
| Gateway/Adapter | `gateways/paypal.py` | Chuyển AIMS payload sang PayPal payload | PayPal-specific logic nằm ở đâu |
| Entity | `models.py` | Lưu trạng thái bền vững | Field nào là source of truth |
| Seam | `completion_service.py` | Nối payment sang order | Khi success thì order thay đổi gì |

## 3. Các nguyên tắc thiết kế đang được ưu tiên

### SRP

- Mỗi view hoặc component nên làm đúng một việc.
- `PaymentResult` là ví dụ tốt.
- `PayPalGateway` cũng tương đối đúng hướng vì nó chỉ tập trung vào PayPal.
- SRP ở đây là nguyên tắc được dùng nhiều nhất để giải thích cách tách file.

### DIP

- `PaymentService` phụ thuộc vào interface, không phụ thuộc trực tiếp vào API cụ thể.
- Đây là lý do cần `PaymentProviderRegistry`.
- Nếu đọc đúng DIP ở flow này, bạn sẽ thấy service chỉ nói chuyện qua capability interfaces.

### OCP

- Thêm gateway mới nên ít phải sửa service trung tâm.
- Tuy vậy, một số nơi vẫn còn switch theo gateway, nên OCP chưa hoàn hảo tuyệt đối.
- Đây là điểm cần nói trung thực khi thuyết minh: code đi theo OCP, nhưng chưa triệt để ở mọi chỗ.

### Data Coupling

- Các lớp trao đổi primitive hoặc DTO thay vì object lớn không cần thiết.
- Điều này giúp trace dễ hơn và test gọn hơn.
- Đây là kiểu coupling đáng ưu tiên cho flow integration như payment.

### Procedural Cohesion ở page

- `PayPalPaymentInner` là một page orchestration, nên procedural cohesion là chấp nhận được.
- Page có nhiều bước tuần tự nhưng business logic vẫn được đẩy xuống API/service.

### Communicational Cohesion ở entity

- `PaymentTransaction` gom các field cùng phục vụ một transaction.
- Đây là một dạng cohesion phù hợp cho model dữ liệu.

## 4. Nơi code cố tình chạm vào integration boundary

- `PayPalPaymentButton` load PayPal JS SDK trực tiếp vì đó là boundary UI với nhà cung cấp ngoài.
- `PayPalGateway` gọi PayPal REST API trực tiếp vì đó là boundary backend với provider.
- `PaymentCompletionService` gọi `fulfill_paid_order(...)` vì đó là seam giữa payment và order domain.
- `PaymentProviderRegistry` và `PayPalGateway` là hai điểm boundary cần nhớ nhất khi bạn mô tả kiến trúc.

## 5. Những điểm chưa hoàn hảo nhưng cần biết

- `views.py` vẫn còn chịu trách nhiệm khá nhiều việc: validate, load order, create transaction, map response.
- `PayPalGateway` gộp cả token management, mock mode và HTTP mapping, nên nó chưa tách nhỏ tối đa.
- `OCP` chưa tuyệt đối vì một số nơi vẫn còn nhánh chọn provider theo gateway.
- `PaymentCompletionService` là seam đúng, nhưng payment success vẫn còn phụ thuộc vào order domain nên cần đọc cả `apps/orders/services.py`.

## 6. Điểm cần nhớ khi đọc code

- Nếu logic liên quan đến thay đổi trạng thái, tìm service trước.
- Nếu logic liên quan đến gọi PayPal, tìm gateway trước.
- Nếu logic liên quan đến request/response API, tìm serializer và view trước.
- Nếu logic chỉ để hiển thị, nó nên nằm ở component thuần.

## 7. Câu trả lời ngắn để thuyết minh trước lớp

Nếu ai hỏi "code này đang theo design pattern nào?", bạn có thể trả lời:

- View chỉ làm controller mỏng.
- Payment workflow được gom vào service layer.
- Provider được chọn qua registry/factory.
- PayPal REST API được bọc bởi gateway/adapter.
- Trạng thái giao dịch được cập nhật trong lifecycle service.
- Hoàn tất đơn hàng được tách thành seam riêng sau khi payment thành công.

## 8. Những chỗ dễ bị nhầm

- `PaymentService` không phải gateway.
- `PaymentProviderRegistry` không xử lý nghiệp vụ thanh toán, chỉ chọn implementation.
- `PaymentTransaction` là entity lưu dữ liệu, không phải nơi chứa orchestration.
- `PaymentResult` là component UI, không phải business logic.

## 9. Kết luận ngắn

Nếu bạn muốn đọc code nhanh, hãy nhớ mô hình sau:

- View/Component = giao tiếp
- Service = nghiệp vụ
- Registry/Factory = chọn provider
- Gateway = chạm hệ thống ngoài
- Entity = lưu trạng thái
- Completion seam = chuyển payment thành order processing
