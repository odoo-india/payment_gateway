# Part of Odoo. See LICENSE file for full copyright and licensing details.

BASE_URL = "https://sandbox.cashfree.com/pg"

API_VERSION = '2025-01-01'  # The API version of CashFree implemented in this module

SUPPORTED_CURRENCIES = [
    'INR',
    'AED',
    'AUD',
    'CAD',
    'CHF',
    'CNY',
    'EUR',
    'GBP',
    'HKD',
    'JPY',
    'NOK',
    'NZD',
    'QAR',
    'SAR',
    'SGD',
    'THB',
    'USD',
    'ZAR',
]

DEFAULT_PAYMENT_METHOD_CODES = {
    'upi',
    'netbanking',
    'card',
    'paytm',
    'paypal',
    'amazon_pay'
}

PAYMENT_METHOD_CODES_MAPPING = {
    'upi': 'upi',
    'card': 'cc, dc, ccc, ppc',
    'netbanking': 'nb'
}

PAYMENT_METHODS_MAPPING = {
    'upi': 'upi',
    'card': 'debit_card',
    'netbanking': 'net_banking',
}

PAYMENT_STATUS_MAPPING = {
    'done': ('SUCCESS'),
    'error': ('FAILED', 'CANCELLED', 'USER_DROPPED'),
    'pending': ('PENDING')
}

WEBHOOK_TYPE_MAPPING = {
    'payment': ("PAYMENT_SUCCESS_WEBHOOK", "PAYMENT_FAILED_WEBHOOK", "PAYMENT_USER_DROPPED_WEBHOOK"),
    'refund': ('REFUND_STATUS_WEBHOOK'),
}

# Events that are handled by the webhook.
HANDLED_WEBHOOK_EVENTS = [
    'PAYMENT_SUCCESS_WEBHOOK',
    'PAYMENT_FAILED_WEBHOOK',
    'PAYMENT_USER_DROPPED_WEBHOOK',
    'REFUND_STATUS_WEBHOOK',
    'AUTO_REFUND_STATUS_WEBHOOK',
]
