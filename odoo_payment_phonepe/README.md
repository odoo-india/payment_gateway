# Phonepe

## Technical Details

API: [Phonepe Create Payment API](https://developer.phonepe.com/payment-gateway/website-integration/standard-checkout/api-integration/api-reference/create-payment)
Payment Checkout: [Phonepe Payment Checkout](https://developer.phonepe.com/payment-gateway/website-integration/standard-checkout/api-integration/api-reference/invoke-iframe-paypage)

## Supported Features

- Direct Payment Flow
- Refund Flow
- Webhook Notification

## Testing Instructions

Testing Credentials: [https://developer.phonepe.com/payment-gateway/uat-testing-go-live/uat-sandbox](https://developer.phonepe.com/payment-gateway/uat-testing-go-live/uat-sandbox)

### Visa Credit Card

**Card Number**: `4208 5851 9011 6667`

**Card Expiry**: `06/2027`

**Card CVV**: `123`

**Verification OTP**: `123456`

### UPI

Scan the QR with any QR scanner and a link will appear open the link any browser and choose the status `Success`, `Failure` or `Pending`.

OR

**UPI ID**: `success@ybl` or `failed@ybl` or `pending@ybl`
