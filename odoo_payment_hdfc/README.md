# HDFC Payment Gateway Integration (UPI)

This module integrates **HDFC UPI Payment Gateway** with Odoo, enabling customers to pay via **dynamic QR codes** on website checkout and directly from **invoice PDFs**.

## Supported Features

- UPI Payments via HDFC Payment Gateway
- Dynamic QR Code generation for UPI payments
- Scan & Pay using any UPI app (GPay, PhonePe, Paytm, BHIM, etc.)
- QR Code payment directly from **Invoice PDF**
- Website checkout integration with UPI payment option
- Customer Portal payment support
- Real-time payment status updates via **webhooks**
- Automatic transaction post-processing in Odoo
- Support for partial and full refunds (subject to HDFC enablement)
- Multi-company support in Odoo
- Test (UAT) and Production environment support

## Testing Instructions

HDFC does not provide generic public test credentials.
For UAT (testing) and Production environments, credentials are issued by HDFC after merchant onboarding.

### UAT / Sandbox

- Merchant ID: Provided by HDFC
- Merchant VPA (UPI ID): Provided by HDFC
- Encryption Key: Provided by HDFC
- Callback / Webhook URL: Your Odoo database URL followed by `/payment/HDFC/webhook`
  - Example: `https://example.odoo.com/payment/HDFC/webhook`
