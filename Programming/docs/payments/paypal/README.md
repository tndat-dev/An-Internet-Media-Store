# Pay Order by Credit Card (PayPal)

Tài liệu này giúp bạn đọc đúng luồng "Pay Order by Credit Card" trong AIMS. Trong code hiện tại, "credit card" được xử lý qua PayPal-hosted checkout, nên dữ liệu thẻ không đi vào backend của AIMS.

## Trả lời ngắn các câu hỏi quan trọng

- "Credit card" ở đây có phải AIMS tự xử lý thẻ không? Không. Người dùng nhập thẻ trong PayPal checkout, AIMS chỉ nhận order id và kết quả capture.
- Luồng thành công kết thúc ở đâu? Sau khi capture thành công, backend cập nhật `PaymentTransaction` sang `SUCCESS`, gọi seam hoàn tất order, rồi order sang `PENDING_PROCESSING`.
- File nào nên đọc trước? Bắt đầu từ `read-diagrams.md`, sau đó `read-code.md`, rồi `design-patterns.md`.
- Có entity credit card riêng không? Không có. Code dùng `PaymentTransaction` làm trung tâm của giao dịch.
- Nếu muốn lần runtime flow nhanh nhất thì xem gì? `PayOrderByCreditCard.puml`, `Programming/frontend/src/features/payment/components/PayPalPaymentButton.tsx`, và `Programming/backend/apps/payments/views.py`.

## Nên đọc theo thứ tự này

1. `[read-diagrams.md](read-diagrams.md)` để hiểu bức tranh tổng thể.
2. `[read-code.md](read-code.md)` để lần theo luồng thật trong frontend và backend.
3. `[design-patterns.md](design-patterns.md)` để nhận diện các pattern và nguyên tắc thiết kế đang dùng.

## Tài liệu gốc liên quan

- `[Use case spec](../../../../RequirementAnalysis/UCSpec/pdf/PayOrderByCreditCard_updated.pdf)`
- `[Activity diagram](../../../../RequirementAnalysis/ActivityDiagram/images/PayOrderByCreditCard.png)`
- `[Sequence diagram](../../../../ArchitecturalDesign/SequenceDiagram/images/PayOrderByCreditCard.png)`
- `[Communication diagram](../../../../ArchitecturalDesign/CommunicationDiagram/images/PayOrderByCreditCard.png)`
- `[Analysis class diagram](../../../../ArchitecturalDesign/AnalysisClassDiagram/IndividualUC/PayOrderByCreditCard.png)`
- `[Detailed design class diagram source](../../../../PayOrderByCreditCard%20(1).puml)`
- `[Sequence diagram source](../../../../PayOrderByCreditCard.puml)`

## Tóm tắt nhanh

Luồng chuẩn là: chọn phương thức thanh toán -> mở PayPal checkout -> tạo PayPal order -> người dùng approve -> capture payment -> cập nhật `PaymentTransaction` -> gọi seam hoàn tất đơn hàng -> chuyển order sang `PENDING_PROCESSING` -> hiển thị kết quả thanh toán.

## Tóm tắt theo vai trò file

- `read-diagrams.md`: dùng khi bạn muốn hiểu "luồng chạy".
- `read-code.md`: dùng khi bạn muốn biết "code nào thực thi bước nào".
- `design-patterns.md`: dùng khi bạn muốn thuyết minh vì sao code được tách thành view, service, gateway, registry và entity.
- `Programming/frontend/src/features/payment/**`: phần UI và API client.
- `Programming/backend/apps/payments/**`: phần business orchestration, persistence và provider integration.
