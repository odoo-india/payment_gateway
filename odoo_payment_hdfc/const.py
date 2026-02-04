
# Part of Odoo. See LICENSE file for full copyright and licensing details.

PROD_BASE_URL = 'upiv2.hdfcbank.com'
TEST_BASE_URL = 'upitestv2.hdfcbank.com'
HDFC_INV_REF_PREFIX = "HDFC//INV/"

# The currencies supported by HDFC - (RN only INR is supported)
SUPPORTED_CURRENCIES = ['INR']

# Mapping of transaction states to HDFC payment statuses.
PAYMENT_STATUS_MAPPING = {
    'pending': ['PENDING'],
    'done': ['SUCCESS'],
    'cancel': ['REJECTED'],
    'error': ['EXPIRED'],
}

# The codes of the payment methods to activate when HDFC is activated.
DEFAULT_PAYMENT_METHOD_CODES = {
    # Primary payment methods.
    'upi',
}

PAYMENT_METHODS_MAPPING = {
    'upi': ['upi'],
}

HDFC_HASH_SEQUENCE = {
    'REFUND': 'merchant_id|new_order_no|original_order_no|original_txn_ref_no|original_cust_ref_no|remarks|refund_amount|currency|payment_type|txn_type|additional_1|additional_2|additional_3|additional_4|additional_5|additional_6|additional_7|additional_8|additional_9|additional_10',
}
