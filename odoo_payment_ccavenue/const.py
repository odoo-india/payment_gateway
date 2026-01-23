# Part of Odoo. See LICENSE file for full copyright and licensing details.

# The codes of the payment methods to activate when ccavenue is activated.
DEFAULT_PAYMENT_METHOD_CODES = {
    # Primary payment methods.
    'card',
    'netbanking',
    'upi',
    # Brand payment methods.
    'visa',
    'mastercard',
}

CCAVENUE_LIVE_URL = 'https://secure.ccavenue.com'
CCAVENUE_TEST_URL = 'https://test.ccavenue.com'
CCAVENUE_API_LIVE_URL = 'https://api.ccavenue.com'
CCAVENUE_API_TEST_URL = 'https://apitest.ccavenue.com'

PAYMENT_METHODS_CODE_MAPPING = {
    'Net Banking': 'netbanking',
    'Credit Card': 'card',
    'Debit Card': 'card',
    'UPI': 'upi',
}

PAYMENT_STATUS_MAPPING = {
    'success': 'Success',
    'failure': 'Failure',
    'aborted': 'Aborted',
    'timeout': 'Timeout',
    'invalid': 'Invalid',
}

SUPPORTED_CURRENCIES = [
    'INR',
]
