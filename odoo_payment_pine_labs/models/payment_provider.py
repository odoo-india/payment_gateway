# Part of Odoo. See LICENSE file for full copyright and licensing details.

import dateutil.parser
import base64
import hmac
import hashlib

from odoo import fields, models

from odoo.addons.odoo_payment_pine_labs import const as pine_labs_const


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[('pine_labs', 'Pine Labs')], ondelete={'pine_labs': 'set default'}
    )
    pine_labs_client_id = fields.Char(
        string="Pinelabs Client Id",
        required_if_provider="pine_labs",
        copy=False,
    )
    pine_labs_client_secret = fields.Char(
        string="Pinelabs Client Secret",
        required_if_provider="pine_labs",
        groups="base.group_system",
        copy=False,
    )
    pine_labs_access_token = fields.Char(
        string="PineLabs Access Token",
        groups="base.group_system",
        copy=False,
    )
    pine_labs_access_token_expiry = fields.Datetime(
        string="PineLabs Access Token Expiry",
        groups="base.group_system",
        copy=False,
    )

    # === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'pine_labs').update({
            'support_refund': 'partial',
        })

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'pine_labs':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in pine_labs_const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'pine_labs':
            return default_codes
        return pine_labs_const.DEFAULT_PAYMENT_METHOD_CODES

    # === API REQUEST === #

    def _pine_labs_get_access_token(self):
        """ Get the access token, refreshing it if necessary."""
        if not self.pine_labs_access_token or (self.pine_labs_access_token_expiry and self.pine_labs_access_token_expiry < fields.Datetime.now()):
            self._pine_labs_refresh_access_token()
        return self.pine_labs_access_token

    def _pine_labs_refresh_access_token(self):
        """ Refresh the access token.

        Note: `self.ensure_one()`

        :return: dict
        """
        self.ensure_one()

        payload = {
            "client_id": self.pine_labs_client_id,
            "client_secret": self.pine_labs_client_secret,
            "grant_type": "client_credentials"
        }
        response_content = self._send_api_request(
            'POST',
            '/auth/v1/token',
            json=payload
        )
        self.write({
            'pine_labs_access_token': response_content['access_token'],
            'pine_labs_access_token_expiry': dateutil.parser.parse(response_content['expires_at']).replace(tzinfo=None),
        })
        return response_content['access_token']

    def _build_request_url(self, endpoint, **kwargs):
        if self.code != 'pine_labs':
            return super()._build_request_url(
                endpoint, **kwargs
            )
        if self.state == 'test':
            return f'https://pluraluat.v2.pinepg.in/api{endpoint}'
        return f'https://api.pluralpay.in/api{endpoint}'

    def _build_request_headers(self, method, endpoint, payload, **kwargs):
        if self.code != 'pine_labs':
            return super()._build_request_headers(
                method, endpoint, payload, **kwargs
            )
        headers = {
            'Content-Type': 'application/json',
            'accept': 'application/json',
        }
        if endpoint != '/auth/v1/token' and (access_token := self._pine_labs_get_access_token()):
            headers.update({'Authorization': f'Bearer {access_token}'})
        return headers

    def _parse_response_error(self, response):
        """Override of `payment` to parse the error message."""
        if self.code != 'pine_labs':
            return super()._parse_response_error(response)
        return response.json().get('error_message', '')

    def _pine_labs_calculate_signature(self, signed_content):
        """ Calculate the HMAC SHA256 signature of the given content.

        Note: self.ensure_one()

        :param str signed_content: The content to be signed.
        :return: The calculated signature.
        :rtype: str
        """
        encoded_secret = base64.b64encode(self.pine_labs_client_secret.encode('utf-8'))
        secret_bytes = base64.b64decode(encoded_secret)
        computed_hmac = hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
        computed_signature = base64.b64encode(computed_hmac).decode('utf-8')
        return computed_signature
