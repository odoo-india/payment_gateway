# Part of Odoo. See LICENSE file for full copyright and licensing details.

# The codes of the payment methods to activate when paytm is activated.
DEFAULT_PAYMENT_METHOD_CODES = {
    # Primary payment methods.
    'card',
    'netbanking',
    'upi',
    # Brand payment methods.
    'visa',
    'mastercard',
}

PAYTM_STAGING_URL = 'https://securestage.paytmpayments.com'
PAYTM_LIVE_URL = 'https://secure.paytmpayments.com'

SUPPORTED_CURRENCIES = [
    'INR',
]

PAYMENT_METHOD_CODES_MAPPING = {
    'netbanking': ['NET_BANKING'],
    'card': ['CREDIT_CARD', 'DEBIT_CARD'],
    'upi': ['UPI'],
}

PAYMENT_METHODS_MAPPING = {
    'NB': 'netbanking',
    'CC': 'card',
    'DC': 'card',
    'UPI': 'upi',
}
