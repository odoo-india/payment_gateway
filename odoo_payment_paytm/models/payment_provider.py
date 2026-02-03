# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo import fields, models
from odoo.exceptions import ValidationError

from odoo.addons.odoo_payment_paytm import const
from odoo.addons.odoo_payment_paytm import utils as paytm_utils


class PaymentProvider(models.Model):
    """Inherit  Payment Provider to add paytm as a provider."""

    _inherit = 'payment.provider'

    code = fields.Selection(
        ondelete={'paytm': 'set default'},
        selection_add=[('paytm', 'Paytm')],
    )

    paytm_merchant_id = fields.Char(
        copy=False,
        groups='base.group_system',
        help="Paytm Merchant ID",
        required_if_provider='paytm',
        string="Paytm Merchant ID",
    )

    paytm_merchant_key = fields.Char(
        copy=False,
        groups='base.group_system',
        help="Paytm Merchant Key",
        required_if_provider='paytm',
        string="Paytm Merchant Key",
    )

    def _compute_feature_support_fields(self):
        """Override of `payment` to enable additional features."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'paytm').update({
            'support_refund': 'partial'
        })

    def _get_default_payment_method_codes(self):
        """Return the default payment method codes to activate when this provider is activated."""
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'paytm':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _get_supported_currencies(self):
        """Override of `payment` to return the supported currencies."""
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'paytm':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _build_request_url(self, endpoint, **kwargs):
        """Override of `payment` to build the request URL."""
        if self.code != 'paytm':
            return super()._build_request_url(endpoint, **kwargs)

        base_url = const.PAYTM_STAGING_URL if self.state == 'test' else const.PAYTM_LIVE_URL
        return f"{base_url}{endpoint}"

    def _build_request_headers(self, method, endpoint, payload, **kwargs):
        if self.code != 'paytm':
            return super()._build_request_headers(method, endpoint, payload, **kwargs)

        return {'Content-Type': 'application/json'}

    def _parse_response_content(self, response, **kwargs):
        if self.code != 'paytm':
            return super()._parse_response_content(response, **kwargs)
        response_content = response.json()

        result_info = response_content.get('body', {}).get('resultInfo', {})
        # 'S' (resultStatus) is from 'initiateTransaction' API
        if result_info.get('resultStatus') == 'S':
            return response_content
        # 'PENDING' and '601' is from '/refund/apply' API (it means refund applied successfully and is pending)
        if result_info.get('resultStatus') == 'PENDING' and result_info.get('resultCode') == '601':
            is_valid_signature = paytm_utils.verifySignature(
                params=json.dumps(response_content.get('body', {}), separators=(',', ':')),
                key=self.paytm_merchant_key,
                checksum=response_content.get('head', {}).get('signature')
            )
            if not is_valid_signature:
                raise ValidationError("The payment provider rejected the request due to an invalid signature.")
            return response_content
        raise ValidationError(
            f"The payment provider rejected the request with the following error: {result_info.get('resultMsg')} (code: {result_info.get('resultCode')})"
        )
