# Part of Odoo. See LICENSE file for full copyright and licensing details.

# The currencies supported by Billdesk
SUPPORTED_CURRENCIES = [
    'INR',
]

DEFAULT_PAYMENT_METHOD_CODES = {
    'netbanking',
    'card',
}

PAYMENT_METHOD_CODES_MAPPING = {
    'netbanking': ['nb'],
    'card': ['card'],
    'upi': ['upi'],
    'wallets_india': ['wallets'],
    'emi_india': ['emi'],
}

PAYMENT_METHODS_MAPPING = {
    'nb': 'netbanking',
    'card': 'card',
    'upi': 'upi',
    'wallets': 'wallets_india',
    'emi': 'emi_india',
}

PAYMENT_STATUS_MAPPING = {
    'done': ('0300',),
    'in progress': ('0002',),
    'error': ('0399',),
}

REFUND_STATUS_MAPPING = {
    'done': ('0799',),
    'cancel': ('0699',),
}
