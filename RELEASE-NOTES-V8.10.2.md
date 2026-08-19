# BookingSystem2026 V8.10.2

Build: `2026.08.18-cash-payment-method-v8.10.2`

This cumulative release adds an explicit payment method to the existing payment
workflow. The administrator can record Bank transfer or Cash. The
method is displayed against the payment and carried through the protected
Accounts integration.

Cash still secures the booking and uses the existing payment-confirmation email
workflow. No historical payment, invoice number, client link or imported Studio
Ninja record is changed during deployment.

Deploy Accounts V1.4.1 before this Booking release, then run the normal manual
Accounts sync when a newly recorded payment needs transferring.
