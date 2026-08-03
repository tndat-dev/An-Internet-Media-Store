/*
 Shared checkout progress indicator (Cart -> Delivery -> Invoice -> Payment -> Result), 
 per the AIMS screen mockups. Each checkout page passes its current step.
 */
const STEPS = ["Cart", "Delivery", "Invoice", "Payment", "Result"] as const;

export type CheckoutStep = (typeof STEPS)[number];

export function OrderProgressStepper({ current }: { current: CheckoutStep }) {
  const currentIndex = STEPS.indexOf(current);

  return (
    <ol className="stepper" aria-label="Checkout progress">
      {STEPS.map((label, index) => {
        const state = index < currentIndex ? "done" : index === currentIndex ? "active" : "todo";
        return (
          <li key={label} className={`stepper-item stepper-${state}`}>
            <span className="stepper-dot" aria-hidden="true">
              {index < currentIndex ? "✓" : index + 1}
            </span>
            <span className="stepper-label">{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
