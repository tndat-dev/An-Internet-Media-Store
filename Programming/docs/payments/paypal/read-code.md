# Cách Đọc Code Cho PayPal Payment Flow

## 1. Đi theo luồng từ frontend tới backend

Cách dễ nhất là đọc theo thứ tự runtime:

1. `Programming/frontend/src/app/checkout/payment/page.tsx`
2. `Programming/frontend/src/features/payment/components/PayPalPaymentButton.tsx`
3. `Programming/frontend/src/features/payment/services/paymentApi.ts`
4. `Programming/backend/apps/payments/urls.py`
5. `Programming/backend/apps/payments/views.py`
6. `Programming/backend/apps/payments/services.py`
7. `Programming/backend/apps/payments/provider_registry.py`
8. `Programming/backend/apps/payments/gateways/paypal.py`
9. `Programming/backend/apps/payments/models.py`
10. `Programming/backend/apps/payments/lifecycle_service.py`
11. `Programming/backend/apps/payments/completion_service.py`
12. `Programming/backend/apps/orders/services.py`

## 1.1 Bản đồ runtime ngắn gọn

Khi user bấm Pay trên PayPal button:

1. Frontend gọi `initiatePayPalPayment`.
2. Backend tạo PayPal order và lưu `PaymentTransaction`.
3. PayPal mở hosted checkout.
4. Khi approve, frontend gọi `capturePayPalPayment`.
5. Backend capture và hoàn tất payment.
6. Order được fulfilled và đưa sang `PENDING_PROCESSING`.

Khi user cancel:

1. PayPal redirect về `cancelUrl`.
2. Frontend chuyển trạng thái sang cancelled.
3. Không có capture và không có fulfillment.

## 2. Frontend: màn hình nào làm gì

### `src/app/checkout/payment/page.tsx`

- Là màn hình chọn phương thức thanh toán.
- Tạo link sang PayPal page.
- Chỉ làm orchestration giao diện.
- Page này không quyết định nghiệp vụ thanh toán; nó chỉ nối từ payment method screen sang PayPal payment screen.

### `src/features/payment/components/PayPalPaymentButton.tsx`

- Load PayPal JS SDK.
- Gọi `initiatePayPalPayment(...)` để tạo order.
- Gọi `capturePayPalPayment(...)` sau khi người dùng approve.
- Redirect sang trang kết quả hoặc trang hủy.

Đây là integration boundary phía frontend.
- Nếu không có `NEXT_PUBLIC_PAYPAL_CLIENT_ID`, component dùng fallback redirect để vẫn tạo được order qua backend.
- `onApprove` là nơi frontend nhận callback từ PayPal JS SDK rồi mới gọi backend capture.

### `src/features/payment/services/paymentApi.ts`

- Đóng gói các HTTP call vào backend.
- Chỉ expose các hàm typed như `initiatePayPalPayment` và `capturePayPalPayment`.
- Giúp component không phải biết chi tiết fetch URL.
- Đây là lớp thích hợp nhất để đọc contract request/response khi bạn muốn biết API đang gửi gì.

### `src/features/payment/components/PaymentResult.tsx`

- Chỉ render trạng thái kết quả.
- Không gọi API.
- Dùng lại được cho nhiều gateway nếu cùng shape dữ liệu.
- Đây là display-only component. Nếu muốn sửa text hiển thị sau thanh toán, thường là sửa ở đây.

### `src/features/payment/types/payment.ts`

- Chứa request/response DTO của payment.
- Đây là nơi bạn kiểm tra contract dữ liệu giữa frontend và backend.
- Các field như `provider_order_id`, `capture_id`, `transaction_id`, `order_total_vnd` là những field cần theo dõi khi debug.

## 3. Backend: controller, service, gateway, entity

### `apps/payments/urls.py`

- Định tuyến ba endpoint chính:
  - `/api/payments/paypal/initiate/`
  - `/api/payments/paypal/capture/`
  - `/api/payments/paypal/refund/`
- Route status dùng lại endpoint `/api/payments/<transaction_id>/status/` cho màn hình kết quả.

### `apps/payments/views.py`

- Nhận request từ frontend.
- Validate bằng serializer.
- Lấy order.
- Gọi service layer.
- Tạo hoặc cập nhật `PaymentTransaction`.
- Trả response an toàn cho frontend.

Đây là lớp controller mỏng, không nên đọc như nơi chứa business logic chính.
- Trong file này, `_get_payment_service()` là điểm tạo dependency cho PayPal flow.
- `PayPalPaymentView` tạo transaction PENDING ngay sau khi create order thành công.
- `PayPalCaptureView` là nơi nối payment thành công với `PaymentCompletionService`.

### `apps/payments/serializers.py`

- Định nghĩa contract input/output cho DRF.
- `InitiatePayPalPaymentSerializer` kiểm tra `order_id`, `return_url`, `cancel_url`.
- `CapturePayPalPaymentSerializer` kiểm tra `provider_order_id` và `internal_order_id`.
- `PaymentTransactionSerializer` là shape dữ liệu trả ra cho UI.
- Nếu bạn muốn biết backend chấp nhận field nào, đọc serializer trước khi đọc view.

### `apps/payments/services.py`

- `PaymentService` là lớp orchestration.
- Nó không biết PayPal cụ thể ở đâu, chỉ gọi abstraction như initiator/capturer/refund service.
- Đây là lớp bạn đọc để hiểu flow nghiệp vụ tổng quát.
- Hàm `capture_payment` là nút trung tâm của bước approve -> capture.

### `apps/payments/provider_registry.py`

- Chọn provider theo `PaymentGatewayChoice`.
- Trả về `PayPalGateway` hoặc service khác khi cần.
- Đây là factory/registry boundary.
- Nơi này trả lời câu hỏi: "Nếu gateway là PayPal thì lớp nào được khởi tạo?"

### `apps/payments/gateways/paypal.py`

- Chứa mọi chi tiết PayPal REST API.
- Tạo order.
- Capture order.
- Refund capture.
- Xử lý token OAuth và lỗi HTTP.

Nếu muốn hiểu hệ thống nói chuyện với PayPal thế nào, hãy đọc file này kỹ nhất.
- `MOCK` mode trong constructor là điểm rất quan trọng khi chạy demo hoặc test không có sandbox credential.

### `apps/payments/models.py`

- `PaymentTransaction` lưu trạng thái giao dịch.
- `RefundTransaction` lưu log hoàn tiền.
- `gateway`, `provider_order_id`, `capture_id`, `refund_id`, `provider_payload` là các trường quan trọng để trace.
- `provider_payload` giữ metadata riêng của provider, ví dụ PayPal amount/currency và source amount VND.

### `apps/payments/lifecycle_service.py`

- Quản lý state transition của `PaymentTransaction`.
- Có các hàm như `mark_success`, `mark_failed`, `mark_refunded`.
- Đây là nơi không nên để logic API hay UI.
- Nếu muốn thay đổi cách set trạng thái giao dịch, sửa ở đây thay vì sửa trực tiếp trong view.

### `apps/payments/completion_service.py`

- Hoàn tất payment thành công.
- Gọi lifecycle service.
- Sau đó gọi `fulfill_paid_order(...)`.
- Đây là seam nối payment domain sang order domain.

### `apps/orders/services.py`

- Chứa seam hoàn tất đơn hàng.
- `fulfill_paid_order` / `mark_order_paid` chuyển order sang `PENDING_PROCESSING` và xử lý các thay đổi liên quan đến đơn.
- Đây là phần chứng minh payment thành công không chỉ đổi payment status mà còn phải làm order tiến thêm một bước.

## 4. Chuỗi gọi thực tế

### Khi tạo payment

Frontend button -> `paymentApi.initiatePayPalPayment` -> `PayPalPaymentView` -> `PaymentService.initiate_payment` -> `PayPalGateway.create_payment` -> PayPal REST API.

Trong code, response hợp lệ sẽ trả về `provider_order_id`, `approval_url`, `transaction_id`, `amount`, `currency`, `source_amount_vnd`.

### Khi capture payment

Frontend callback -> `paymentApi.capturePayPalPayment` -> `PayPalCaptureView` -> `PaymentService.capture_payment` -> `PayPalGateway.capture_payment` -> `PaymentCompletionService.complete_successful_payment` -> `fulfill_paid_order`.

Sau capture, `PaymentTransactionSerializer` được dùng để render dữ liệu trả về cho frontend.

### Khi cancel payment

Frontend nhận `cancelUrl` -> route về page payment card với flag `cancelled=true` -> `PaymentResult(status="cancelled")`.

## 5. Dữ liệu quan trọng cần theo dõi

- `order_id`: ID logic của order trong AIMS.
- `provider_order_id`: ID order ở PayPal.
- `transaction_id`: ID của `PaymentTransaction` trong AIMS.
- `capture_id`: ID capture trả về từ PayPal.
- `amount` / `source_amount_vnd`: số tiền thanh toán và số tiền gốc trong hệ thống.
- `status`: trạng thái giao dịch.

Nếu bạn debug một ca lỗi, hãy in theo thứ tự: `order_id` -> `provider_order_id` -> `transaction_id` -> `capture_id` -> `status`.

## 6. Chỗ dễ nhầm

- `PayPalPaymentButton` gọi backend trực tiếp khi tạo/capture, nhưng business rule vẫn nằm ở backend.
- `PaymentResult` chỉ hiển thị kết quả, không xác định trạng thái.
- Tên "card" trong UI không có nghĩa là AIMS tự quản lý dữ liệu thẻ.
- Nếu một luồng đang nói về refund, hãy đọc thêm `refund_service.py` và `refund_policies.py` sau khi đã hiểu initiate/capture.

## 7. Các câu hỏi thường gặp và câu trả lời trực tiếp

### Vì sao backend tạo transaction trước khi customer approve?

Để capture sau đó có bản ghi nội bộ để bám vào. Đây là cách giữ đồng bộ giữa AIMS và PayPal.

### Nếu create payment thành công nhưng capture thất bại thì sao?

`PaymentTransaction` vẫn có thể tồn tại ở trạng thái pending hoặc fail tùy nhánh xử lý, và frontend sẽ hiển thị failed để user thử lại.

### Vì sao có `PaymentCompletionService` thay vì gọi `fulfill_paid_order` trực tiếp trong view?

Để tách trách nhiệm: view lo transport, service lo business workflow, order service lo fulfillment.

### Trang kết quả lấy dữ liệu ở đâu?

Từ query params sau redirect và từ status endpoint để hiển thị trạng thái giao dịch.
