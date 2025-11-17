# Part of Odoo. See LICENSE file for full copyright and licensing details.
import json

from odoo import _, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger

from odoo.addons.payment import utils as payment_utils
from odoo.addons.odoo_payment_phonepe import const as phonepe_const
from odoo.addons.odoo_payment_phonepe.controllers.main import PhonepeController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _compute_reference(self, provider_code, prefix=None, separator='-', **kwargs):
        """Override of `payment` to ensure that PhonePe' requirements for references are satisfied.

        Phonepe requirements for references are:
        - For payment, the reference should pass `^[a-zA-Z0-9_|-]{1,63}$` regex
        - For refund, the reference length should be less than or equal to 63 characters

        :param str provider_code: The code of the provider handling the transaction.
        :param str prefix: The custom prefix used to compute the full reference.
        :param str separator: The custom separator used to separate the prefix from the suffix.
        :return: The unique reference for the transaction.
        :rtype: str
        """
        is_refund = prefix and prefix.startswith('R-')
        if provider_code != 'phonepe' or is_refund:
            return super()._compute_reference(provider_code, prefix, separator, **kwargs)
        prefix = payment_utils.singularize_reference_prefix(prefix='pp-', separator='')
        return super()._compute_reference(
            provider_code, prefix=prefix, separator='', **kwargs
        )

    def _send_refund_request(self):
        """ Override of `payment` to send a refund request to Phonepe.

        Note: self.ensure_one()

        :param float amount_to_refund: The amount to refund.
        :return: The refund transaction created to process the refund request.
        :rtype: recordset of `payment.transaction`
        """
        if self.provider_code != 'phonepe':
            return super()._send_refund_request()

        # Make the refund request to Phonepe.
        converted_amount = payment_utils.to_minor_currency_units(
            -self.amount, self.currency_id
        )  # The amount is negative for refund transactions.

        payload = {
            'merchantRefundId': self.reference,
            'originalMerchantOrderId': self.source_transaction_id.reference,
            'amount': converted_amount,
        }
        self._send_api_request('POST', '/payments/v2/refund', data=json.dumps(payload))

    def _get_specific_processing_values(self, processing_values):
        """ Override of `payment` to return phonepe-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the
                                       transaction.
        :return: The provider-specific processing values.
        :rtype: dict
        """
        if self.provider_code != 'phonepe':
            return super()._get_specific_processing_values(processing_values)
        token_url = self._phonepe_create_payment_order().get('redirectUrl', '')
        return {
            'token_url': token_url,
            'type': 'IFRAME',
        }

    def _phonepe_create_payment_order(self):
        """ Create and return an Order object to initiate the payment.

        :return: The created Order.
        :rtype: dict
        """
        payload = self._phonepe_prepare_order_payload()
        order_data = self._send_api_request('POST', '/checkout/v2/pay', data=json.dumps(payload))
        return order_data

    def _phonepe_prepare_order_payload(self):
        """ Prepare the payload for the order request based on the transaction values.

        :return: The request payload.
        :rtype: dict
        """
        converted_amount = payment_utils.to_minor_currency_units(self.amount, self.currency_id)
        pm_code = (self.payment_method_id.primary_payment_method_id or self.payment_method_id).code
        phonepe_pm_code = phonepe_const.PAYMENT_METHOD_CODES_MAPPING[pm_code]
        enablePaymentModes = [{'type': pm_code} for pm_code in phonepe_pm_code]
        if pm_code == 'card':
            enablePaymentModes[0].update({
                'cardTypes': [
                    'CREDIT_CARD',
                    'DEBIT_CARD'
                ]
            })
        payload = {
            'merchantOrderId': self.reference,  # It should be unique as it is used for pooling the payment status
            'amount': converted_amount,
            'metaInfo': {
                'reference': self.reference,
            },
            'paymentFlow': {
                'type': 'PG_CHECKOUT',
                'merchantUrls': {
                    'redirectUrl': f'{self.provider_id.get_base_url()}{PhonepeController.RETURN_URL}'
                },
                'paymentModeConfig': {
                    "enabledPaymentModes": enablePaymentModes
                }
            },
        }
        return payload

    def _search_by_reference(self, provider_code, payment_data):
        """ Override of `payment` to find the transaction based on phonepe data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict payment_data: The normalized notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        if provider_code != 'phonepe':
            return super()._search_by_reference(provider_code, payment_data)

        webhook_type = payment_data.get('webhook_type', 'payment')
        reference_key = 'merchantOrderId' if webhook_type == 'payment' else 'merchantRefundId'
        reference = payment_data.get(reference_key)
        if not reference:
            raise ValidationError(_("Phonepe: Received data with missing reference."))
        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'phonepe')])

        if not tx:
            raise ValidationError(
                _("Phonepe: No transaction found matching reference %s.", reference),
            )

        return tx

    def _apply_updates(self, payment_data):
        """ Override of `payment` to process the transaction based on Phonepe data.

        Note: self.ensure_one()

        :param dict payment_data: The notification data sent by the provider
        :return: None
        """
        if self.provider_code != 'phonepe':
            return super()._apply_updates(payment_data)

        webhook_type = payment_data.get('webhook_type', 'payment')

        # Update the provider reference.
        if webhook_type == 'payment':
            provider_reference = payment_data.get('orderId')
        else:  # refund
            provider_reference = payment_data.get('refundId')
        if not provider_reference:
            raise ValidationError(_("Phonepe: Received data with missing id."))
        allowed_to_modify = self.state not in ('done', 'authorized')
        if allowed_to_modify:
            self.provider_reference = provider_reference

        # Update the payment method.
        payment_method_type = payment_data.get('paymentDetails', [{}])[0].get('paymentMode', '')
        payment_method = self.env['payment.method']._get_from_code(
            payment_method_type, mapping=phonepe_const.PAYMENT_METHODS_MAPPING
        )
        if allowed_to_modify and payment_method:
            self.payment_method_id = payment_method

        # Update the payment state.
        entity_status = payment_data.get('state')
        if not entity_status:
            raise ValidationError(_("Phonepe: Received data with missing status."))

        if entity_status in phonepe_const.PAYMENT_STATUS_MAPPING['done']:
            self._set_done()

            # Immediately post-process the transaction if it is a refund, as the post-processing
            # will not be triggered by a customer browsing the transaction from the portal.
            if self.operation == 'refund':
                self.env.ref('payment.cron_post_process_payment_tx')._trigger()
        elif entity_status in phonepe_const.PAYMENT_STATUS_MAPPING['error']:
            _logger.warning(
                "The transaction with reference %s underwent an error. Reason: %s",
                self.reference, payment_data.get('errorCode')
            )
            self._set_error("An error occurred during the processing of your payment. Please try again.")
        else:  # Classify unsupported payment status as the `error` tx state.
            _logger.warning(
                "Received data for transaction with reference %s with invalid payment status: %s",
                self.reference, entity_status
            )
            self._set_error(f"Phonepe: Received data with invalid status: {entity_status}")

    def _extract_amount_data(self, payment_data):
        """Override of payment to extract the amount and currency from the payment data."""
        if self.provider_code != 'phonepe':
            return super()._extract_amount_data(payment_data)

        # Amount not sent in the payment data when redirecting to the return route.
        if 'amount' not in payment_data:
            return

        amount = payment_utils.to_major_currency_units(float(payment_data['amount']), self.currency_id)
        return {
            'amount': amount,
            'currency_code': 'INR',
        }
