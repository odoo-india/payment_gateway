# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib

from datetime import datetime, timedelta
from werkzeug.exceptions import Forbidden

from odoo import fields, models
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.odoo_payment_phonepe import const as phonepe_const

_logger = get_payment_logger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[('phonepe', 'PhonePe')], ondelete={'phonepe': 'set default'}
    )
    phonepe_client_id = fields.Char(
        string="Phonepe Client Id",
        required_if_provider="phonepe",
        groups="base.group_system",
        copy=False
    )
    phonepe_client_secret = fields.Char(
        string="Phonepe Client Secret",
        required_if_provider="phonepe",
        groups="base.group_system",
        copy=False
    )
    phonepe_merchant_id = fields.Char(
        string="Phonepe Merchant Id",
        required_if_provider="phonepe",
        groups="base.group_system",
        copy=False
    )
    phonepe_webhook_username = fields.Char(
        string="Phonepe Webhook Username",
        required_if_provider="phonepe",
        groups="base.group_system",
        copy=False
    )
    phonepe_webhook_password = fields.Char(
        string="Phonepe Webhook Password",
        required_if_provider="phonepe",
        groups="base.group_system",
        copy=False
    )

    # === PhonePe Access Token Fields === #
    phonepe_access_token = fields.Char(string="Phonepe Access Token", groups="base.group_system")
    phonepe_access_token_expiry = fields.Datetime(string="Phonepe Access Token Expiry", groups="base.group_system")

    # === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'phonepe').update({
            'support_refund': 'partial',
        })

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'phonepe':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in phonepe_const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'phonepe':
            return default_codes
        return phonepe_const.DEFAULT_PAYMENT_METHOD_CODES

    # === REQUEST HELPERS === #

    def _build_request_url(self, endpoint, *, is_proxy_request=False, **kwargs):
        """ Override of `payment` to build the request URl. """
        if self.code != 'phonepe':
            return super()._build_request_url(endpoint, is_proxy_request=is_proxy_request, **kwargs)
        request_mode = 'pg-sandbox' if self.state == 'test' else 'pg'
        url = 'https://api.phonepe.com/apis'

        if self.state == 'test':
            url = 'https://api-preprod.phonepe.com/apis'
        if is_proxy_request and self.state != 'test':
            request_mode = 'identity-manager'
        return f'{url}/{request_mode}{endpoint}'

    def _build_request_headers(self, *args, is_proxy_request=False, **kwargs):
        """ Override of `payment` to build the request headers. """
        if self.code != 'phonepe':
            return super()._build_request_headers(*args, is_proxy_request=is_proxy_request, **kwargs)

        if is_proxy_request:
            return {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-MERCHANT-ID': self.phonepe_merchant_id,
            }

        access_token = self._phonepe_get_access_token()
        if access_token:
            return {
                'Authorization': f'O-Bearer {access_token}',
                'Content-Type': 'application/json',
                'X-MERCHANT-ID': self.phonepe_merchant_id,
            }
        return None

    def _parse_response_error(self, response):
        if self.code != 'phonepe':
            return super()._parse_response_error(response)
        return response.json().get('message')

    def _phonepe_verify_signature(self, authorization_header):
        """
        Verifies the PhonePe callback by comparing the Authorization header to SHA-256(username:password).

        See https://developer.phonepe.com/payment-gateway/website-integration/standard-checkout/api-integration/api-reference/webhook/#nav-callback-validation-verification.

        :param str authorization_header: The 'Authorization' header received in the callback.
        :return: True if valid
        :rtype: bool
        :raise: Forbidden: If invalid authorization header
        """
        if not self.phonepe_webhook_username or not self.phonepe_webhook_password:
            _logger.warning("Missing webhook credentials for computing secret; aborting signature calculation")
            return
        secret = f"{self.phonepe_webhook_username}:{self.phonepe_webhook_password}"
        computed_hash = hashlib.sha256(secret.encode()).hexdigest()
        if computed_hash == authorization_header:
            return True
        else:
            _logger.warning("Invalid Authorization header: %s", authorization_header)
            raise Forbidden()

    def _phonepe_get_access_token(self):
        self.ensure_one()
        if not self.phonepe_access_token or (self.phonepe_access_token_expiry and self.phonepe_access_token_expiry < fields.Datetime.now()):
            self._phonepe_refresh_access_token()
        return self.phonepe_access_token

    def _phonepe_refresh_access_token(self):
        """ Refresh the access token.

        Note: `self.ensure_one()`

        :return: dict
        """
        self.ensure_one()
        payload = {
            'client_version': 1,
            "client_id": self.phonepe_client_id,
            "client_secret": self.phonepe_client_secret,
            "grant_type": "client_credentials"  # Constant value from phonepe
        }
        response_content = self._send_api_request('POST', '/v1/oauth/token', data=payload, is_proxy_request=True)
        if response_content.get('access_token'):
            if response_content.get('expires_in'):
                expiry = fields.Datetime.now() + timedelta(seconds=int(response_content['expires_in']))
            else:
                expiry = datetime.fromtimestamp(response_content['expires_at'])
            self.write({
                'phonepe_access_token': response_content['access_token'],
                'phonepe_access_token_expiry': expiry,
            })
        return response_content['access_token']
