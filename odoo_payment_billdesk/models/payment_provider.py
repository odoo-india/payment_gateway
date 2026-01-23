# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json as json_
import uuid

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.odoo_payment_billdesk import const as billdesk_const
from odoo.addons.odoo_payment_billdesk import utils as billdesk_utils


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[('billdesk', "BillDesk")], ondelete={'billdesk': 'set default'}
    )
    billdesk_merchant_id = fields.Char(
        string="Billdesk Merchant ID",
        required_if_provider='billdesk',
        copy=False,
    )
    billdesk_client_id = fields.Char(
        string="Billdesk Client ID", required_if_provider='billdesk', copy=False
    )
    billdesk_key_id = fields.Char(
        string="Billdesk Key Id", required_if_provider='billdesk', copy=False
    )
    billdesk_encryption_key = fields.Char(
        string="Billdesk Encryption Key", required_if_provider='billdesk', copy=False
    )
    billdesk_signing_key = fields.Char(
        string="Billdesk Signing Key", required_if_provider='billdesk', copy=False
    )

    #  === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'billdesk').update(
            {'support_refund': 'partial'}
        )

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'billdesk':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in billdesk_const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        if self.code != 'billdesk':
            return super()._get_default_payment_method_codes()
        return billdesk_const.DEFAULT_PAYMENT_METHOD_CODES

    # === REQUEST HELPERS === #

    def _send_api_request(
        self,
        method,
        endpoint,
        *,
        params=None,
        data=None,
        json=None,
        reference=None,
        **kwargs,
    ):
        if self.code == 'billdesk':
            data = billdesk_utils.billdesk_request(
                json_.dumps(data),
                self.billdesk_key_id,
                self.billdesk_encryption_key,
                self.billdesk_signing_key,
                self.billdesk_client_id,
            )
            if not data:
                raise ValidationError(
                    _("Error while encrypting request. Please ensure billdesk credentials are correctly set.")
                )
        return super()._send_api_request(
            method,
            endpoint,
            params=params,
            data=data,
            json=json,
            reference=reference,
            **kwargs,
        )

    def _build_request_url(self, endpoint, **kwargs):
        """Override of `payment` to build the request URl."""
        if self.code != 'billdesk':
            return super()._build_request_url(endpoint, **kwargs)
        if self.state == 'test':
            return f'https://uat1.billdesk.com/u2{endpoint}'
        return f'https://api.billdesk.com{endpoint}'

    def _build_request_headers(self, *args, **kwargs):
        """Override of `payment` to build the request headers."""
        if self.code != 'billdesk':
            return super()._build_request_headers(*args, **kwargs)

        return {
            'Content-Type': 'application/jose',
            'Accept': 'application/jose',
            'BD-Traceid': str(uuid.uuid4()),
            'BD-Timestamp': fields.Datetime.now().strftime('%Y%m%d%H%M%S'),
        }

    def _parse_response_content(self, response, **kwargs):
        """Override of `payment` to parse response content."""
        if self.code != 'billdesk':
            return super()._parse_response_content(response, **kwargs)
        response_content = billdesk_utils.billdesk_response(
            response.text, self.billdesk_encryption_key, self.billdesk_signing_key
        )
        if not response_content:
            raise ValidationError(_("Invalid response from billdesk"))
        return response_content

    def _parse_response_error(self, response):
        if self.code != 'billdesk':
            return super()._parse_response_error(response)
        if response.headers.get('Content-Type', '') == 'application/json':
            response_content = response.json()
        else:
            response_content = billdesk_utils.billdesk_response(
                response.text, self.billdesk_encryption_key, self.billdesk_signing_key
            )
        if not response_content:
            return "Invalid response from billdesk"
        return response_content.get('message', '')
