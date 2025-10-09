# Part of Odoo. See LICENSE file for full copyright and licensing details.

from typing import Literal

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.odoo_payment_easebuzz import const as easebuzz_const


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[('easebuzz', 'Easebuzz')], ondelete={'easebuzz': 'set default'}
    )
    easebuzz_key = fields.Char(
        string="Easebuzz Key",
        required_if_provider="easebuzz",
        copy=False,
    )
    easebuzz_salt = fields.Char(
        string="Easebuzz Salt",
        required_if_provider="easebuzz",
        copy=False
    )

    #  === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'easebuzz').update({
            'support_refund': 'partial'
        })

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'easebuzz':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in easebuzz_const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'easebuzz':
            return default_codes
        return easebuzz_const.DEFAULT_PAYMENT_METHOD_CODES

    @api.model
    def _easebuzz_convert_amount_to_inr(self, amount, from_currency):
        res_currency_inr = self.env['res.currency'].search([('name', '=', 'INR')])
        return from_currency._convert(amount, res_currency_inr, company=self.company_id)

    # === REQUEST HELPERS === #

    def _build_request_url(self, endpoint, *, mode: Literal['payment', 'refund'] = 'payment', **kwargs):
        """ Override of `payment` to build the request URl. """
        if self.code != 'easebuzz':
            return super()._build_request_url(endpoint, mode=mode, **kwargs)
        if self.state == 'test':
            subdomain = 'testpay' if mode == 'payment' else 'testdashboard'
        else:
            subdomain = 'pay' if mode == 'payment' else 'dashboard'
        return f'https://{subdomain}.easebuzz.in{endpoint}'

    def _build_request_headers(self, *args, mode: Literal['payment', 'refund'] = 'payment', **kwargs):
        """ Override of `payment` to build the request headers. """
        if self.code != 'easebuzz':
            return super()._build_request_headers(*args, mode=mode, **kwargs)

        return {'Content-Type': 'application/x-www-form-urlencoded' if mode == 'payment' else 'application/json'}

    def _parse_response_content(self, response, *, mode: Literal['payment', 'refund'] = 'payment', **kwargs):
        """ Override of `payment` to parse response content. """
        if self.code != 'easebuzz':
            return super()._parse_response_content(response, mode=mode, **kwargs)

        response_content = response.json()
        if response_content.get('status') == 0:
            # Raise error when the response status is 0 as Easebuzz always provide 200 status code
            raise ValidationError(
                _("The payment provider rejected the request.\n%s", response_content.get('error_desc'))
            )
        return response_content

    def _parse_response_error(self, response):
        if self.code != 'easebuzz':
            return super()._parse_response_error(response)
        return response.json().get('error_desc')
