# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo import fields, models

from odoo.addons.odoo_payment_ccavenue import const
from odoo.addons.odoo_payment_ccavenue.utils import (
    decrypt_ccavenue_data,
    parse_ccavenue_response
)


class PaymentProvider(models.Model):
    """Inherit  Payment Provider to add CCAvenue as a provider."""

    _inherit = 'payment.provider'

    code = fields.Selection(
        help='The code of payment provider',
        ondelete={'ccavenue': 'set default'},
        selection_add=[('ccavenue', 'CCAvenue')],
        string='code',
    )
    ccavenue_merchant_id = fields.Char(
        copy=False,
        groups='base.group_system',
        help='CCAvenue Merchant ID',
        required_if_provider='ccavenue',
        string='CCAvenue Merchant ID',
    )
    ccavenue_access_code = fields.Char(
        copy=False,
        groups='base.group_system',
        help='CCAvenue Access Code',
        required_if_provider='ccavenue',
        string='CCAvenue Access Code',
    )
    ccavenue_working_key = fields.Char(
        copy=False,
        groups='base.group_system',
        help='CCAvenue Working Key for encryption',
        required_if_provider='ccavenue',
        string='CCAvenue Working Key',
    )

    def _compute_feature_support_fields(self):
        """Override of `payment` to enable additional features."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'ccavenue').update({
            'support_refund': 'partial'
        })

    def _get_default_payment_method_codes(self):
        """Return the default payment method codes to activate when this provider is activated."""
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'ccavenue':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _get_supported_currencies(self):
        """Override of `payment` to return the supported currencies."""
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'ccavenue':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _build_request_url(self, endpoint, *, is_proxy_request=False, **kwargs):
        """Override of `payment` to build the request URL."""
        if self.code != 'ccavenue':
            return super()._build_request_url(
                endpoint, is_proxy_request=is_proxy_request, **kwargs
            )

        if self.state == 'test':
            return f"{const.CCAVENUE_API_TEST_URL}{endpoint}"
        return f"{const.CCAVENUE_API_LIVE_URL}{endpoint}"

    def _parse_response_content(self, response, **kwargs):
        """Override of `payment` to parse the response content."""
        if self.code != 'ccavenue':
            return super()._parse_response_content(response, **kwargs)

        # Parse and decrypt the response as Response from CCAvenue is encrypted
        parsed_response = parse_ccavenue_response(response.text)
        # As per docs, status '1' denotes failed API call and enc_response will contain plain error message
        if parsed_response.get('status') == '1':
            return parsed_response
        enc_response = parsed_response.get('enc_response')
        decrypted_response = decrypt_ccavenue_data(enc_response, self.ccavenue_working_key)
        json_response = json.loads(decrypted_response)

        return json_response
