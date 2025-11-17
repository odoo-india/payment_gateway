# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pprint

from odoo import _, api, models

from odoo.exceptions import ValidationError
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.odoo_payment_pine_labs import const as pine_labs_const


_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_processing_values(self, processing_values):
        """ Override of `payment` to return pinelabs-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the
                                       transaction.
        :return: The provider-specific processing values.
        :rtype: dict
        """
        if self.provider_code != 'pine_labs':
            return super()._get_specific_processing_values(processing_values)

        if self.operation in ('validation', 'offline'):
            return {}
        # TODO: Handle the senarios where order should not be created for specific type of operation.

        token_url = self._pine_labs_create_order().get('redirect_url')
        return {
            'pine_labs_token_url': token_url,
            'load_url': f"https://checkout{'-staging' if self.provider_id.state == 'test' else ''}.pluralonline.com/v3/web-sdk-checkout.js",
        }

    def _pine_labs_create_order(self):
        """ Create and return an Order object to initiate the payment.

        :return: The created Order.
        :rtype: dict
        """
        payload = self._pine_labs_prepare_order_payload()
        order_data = {}
        try:
            order_data = self.provider_id._send_api_request(
                'POST',
                '/checkout/v1/orders',
                json=payload
            )
        except ValidationError as e:
            self._set_error(str(e))
        return order_data

    def _pine_labs_prepare_order_payload(self):
        """ Prepare the payload for the order request based on the transaction values.

        :return: The request payload.
        :rtype: dict
        """
        converted_amount = payment_utils.to_minor_currency_units(self.amount, self.currency_id)
        pm_code = (self.payment_method_id.primary_payment_method_id or self.payment_method_id).code
        pine_labs_pm_code = pine_labs_const.PAYMENT_METHOD_CODES_MAPPING[pm_code]
        enablePaymentModes = [{'allowed_payment_methods': pm_code} for pm_code in pine_labs_pm_code]
        payload = {
            "merchant_order_reference": self.reference,
            "order_amount": {
                "value": self.amount * 100 if self.provider_id.state == 'test' else converted_amount,
                "currency": self.currency_id.name,
            },
            "integration_mode": "IFRAME",
            "pre_auth": False,
            "allowed_payment_methods": [enablePaymentModes[0]['allowed_payment_methods']],
            "purchase_details": {
                "customer": {
                    "email_id": self.partner_email if self.partner_email else "",
                    "first_name": self.partner_name.split(' ', 1)[0],
                    "last_name": self.partner_name.split(' ', 1)[1] if len(self.partner_name.split(' ', 1)) > 1 else "",
                    "customer_id": self.partner_id.id,
                    "mobile_number": self.partner_phone if self.partner_phone else "",
                    "country_code": self.partner_country_id.phone_code,
                    "billing_address": {
                        "address1": self.partner_id.street if self.partner_id.street else '',
                        "address2": self.partner_id.street2 if self.partner_id.street2 else '',
                        "address3": '',
                        "pincode": self.partner_id.zip if self.partner_id.zip else 0,
                        "city": self.partner_id.city if self.partner_id.city else '',
                        "state": self.partner_id.state_id.name if self.partner_id.state_id else '',
                        "country": self.partner_country_id.name if self.partner_country_id else '',
                    },
                }
            }
        }
        return payload

    def _send_refund_request(self):
        """ Override of `payment` to send a refund request to Pinelabs.

        Note: self.ensure_one()

        :return: The refund transaction created to process the refund request.
        :rtype: recordset of `payment.transaction`
        """
        if self.provider_code != 'pine_labs':
            return super()._send_refund_request()

        _logger.info(
            "Sending '/pay/v1/refunds/%s' request for refund with reference %s",
            self.source_transaction_id.provider_reference,
            self.reference
        )
        converted_amount = payment_utils.to_minor_currency_units(
            self.amount, self.currency_id
        )
        payload = {
            'order_amount': {
                'value': -self.amount * 100 if self.provider_id.state == 'test' else converted_amount,
                'currency': self.source_transaction_id.currency_id.name
            },
            "merchant_order_reference": self.reference,
        }
        response_content = self.provider_id._send_api_request(
            'POST',
            f'/pay/v1/refunds/{self.source_transaction_id.provider_reference}',
            json=payload
        )
        _logger.info(
            "Response of '/pay/v1/refunds/%s' request for refund with reference %s:\n%s",
            self.source_transaction_id.provider_reference,
            self.source_transaction_id.reference,
            pprint.pformat(response_content)
        )

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        """Override of `payment` to extract the reference from the payment data."""
        if provider_code != 'pine_labs':
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get('merchant_order_reference')

    def _extract_amount_data(self, payment_data):
        """Override of payment to extract the amount and currency from the payment data."""
        if self.provider_code != 'pine_labs':
            return super()._extract_amount_data(payment_data)

        order_amount = payment_data.get('order_amount', {})
        if 'value' not in order_amount or 'currency' not in payment_data:
            return

        amount = payment_utils.to_major_currency_units(
            order_amount['value'], self.currency_id
        )
        return {
            'amount': amount,
            'currency_code': order_amount['currency'],
        }

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction based on the payment data."""
        if self.provider_code != 'pine_labs':
            return super()._apply_updates(payment_data)

        allowed_to_modify = self.state not in ('done', 'authorized')
        if allowed_to_modify:
            self.provider_reference = payment_data.get('order_id')

        # Update the payment method.
        payment_method_type = payment_data.get('payments', [])[0].get('payment_method', '')
        payment_method = self.env['payment.method'].search([('code', '=', pine_labs_const.PAYMENT_METHODS_MAPPING.get(payment_method_type))], limit=1)

        if allowed_to_modify and payment_method:
            self.payment_method_id = payment_method

        # Update the payment state.
        entity_status = payment_data.get('status')
        if not entity_status:
            self._set_error(_("Received data with missing status."))

        if entity_status in pine_labs_const.PAYMENT_STATUS_MAPPING['done']:
            self._set_done()
        elif entity_status in pine_labs_const.PAYMENT_STATUS_MAPPING['error']:
            _logger.warning(
                "Pinelabs transaction with referance %s caught an error.",
                self.reference,
            )
            self._set_error(
                _("An error occurred during the processing of your payment. Please try again.")
            )
        else:  # Classify unsupported payment status as the `error` tx state.
            _logger.warning(
                "Received data for transaction %s with invalid payment status: %s.",
                self.reference, entity_status
            )
            self._set_error(
                "Pinelabs: " + _("Received data with invalid status: %s", entity_status)
            )
