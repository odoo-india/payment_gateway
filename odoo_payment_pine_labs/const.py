# Part of Odoo. See LICENSE file for full copyright and licensing details.

SUPPORTED_CURRENCIES = [
    'INR',
    'USD',
    'EUR',
    'ZAR',
    'TWD',
    'MYR',
    'AZN',
    'OMR',
    'KES',
    'SEK',
    'QAR',
    'CNY',
    'THB',
    'BDT',
    'KWD',
    'MXN',
    'PHP',
    'SGD',
    'CHF',
    'AUD',
    'ILS',
    'TRY',
    'TJS',
    'JOD',
    'HKD',
    'AED',
    'SCR',
    'DKK',
    'CAD',
    'NOK',
    'MUR',
    'LKR',
    'CZK',
    'BHD',
    'KZT',
    'SAR',
    'MVR',
    'KRW',
    'JPY',
    'PLN',
    'GBP',
    'NZD',
    'BRL',
]

DEFAULT_PAYMENT_METHOD_CODES = {
    'card',
    'netbanking',
    'upi',
}

PAYMENT_METHOD_CODES_MAPPING = {
    'card': ['CARD'],
    'emi_india': ['CREDIT_EMI', 'DEBIT_EMI'],
    'netbanking': ['NETBANKING'],
    'upi': ['UPI'],
    'wallets_india': ['WALLET'],
}

PAYMENT_METHODS_MAPPING = {
    'CARD': 'card',
    'CREDIT_EMI': 'emi_india',
    'DEBIT_EMI': 'emi_india',
    'NETBANKING': 'netbanking',
    'UPI': 'upi',
    'WALLET': 'wallets_india',
}

PAYMENT_STATUS_MAPPING = {
    'done': ('PROCESSED',),
    'cancel': ('CANCELLED',),
    'error': ('FAILED', 'ATTEMPTED'),
}

# Events that are handled by the webhook.
HANDLED_WEBHOOK_EVENTS = [
    'ORDER_PROCESSED',
    'ORDER_CANCELLED',
    'PAYMENT_FAILED',
    'ORDER_FAILED',
    'REFUND_PROCESSED',
    'REFUND_FAILED',
]
