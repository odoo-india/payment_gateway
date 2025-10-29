# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, models
from odoo.exceptions import ValidationError

from odoo.addons.odoo_payment_payu import const as payu_consts
from odoo.addons.odoo_payment_payu import utils as payu_utils
from odoo.addons.odoo_payment_payu.controllers.main import PayUController

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_processing_values(self, processing_values):
        """Return PayU-specific values including headers for frontend."""
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'payu':
            return res

        txn_env = 'test' if self.provider_id.state == 'test' else 'prod'
        payload_value = self._payu_prepare_txn_payload(processing_values)
        return {
            'txn_env': txn_env,
            'payload': payload_value,
        }

    def _payu_prepare_txn_payload(self, processing_values):
        """ Prepare the payload for the order request based on the transaction values.

        :return: The request payload.
        :rtype: dict
        """
        return_url = f'{self.provider_id.get_base_url()}{PayUController.RETURN_URL}'
        pm_code = (self.payment_method_id.primary_payment_method_id or self.payment_method_id).code
        payu_pm_code = payu_consts.PAYMENT_METHODS_MAPPING[pm_code]
        # Todo: Complete - Multicurrency
        showPaymentMode = '|'.join(payu_pm_code)
        payload = {
            'key': self.provider_id.payu_merchant_key,
            'txnid': self.reference,
            'amount': str(self.provider_id._payu_convert_amount_to_inr(self.amount, self.currency_id)),
            'productinfo': 'Odoo-Product',
            'firstname': self.partner_name,
            'phone': self.partner_phone,
            'email': self.partner_email,
            'surl': return_url,
            'furl': return_url,
            'udf1': 'payment',
            'enforce_paymethod': showPaymentMode,
            'salt': self.provider_id.payu_merchant_salt,  # Delete `salt` key after computing payload hash as it is not required in payload
        }
        payload['hash'] = payu_utils.generate_payu_hash(
            payload=payload,
            hash_sequence=payu_consts.PAYU_HASH_SEQUENCE.get('PAYMENT'),
        )
        return payload

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction based on the payment data."""
        if self.provider_code != 'payu':
            return super()._apply_updates(payment_data)

        # Update the provider reference.
        webhook_type = payment_data.get('udf1', '')

        if webhook_type != 'payment' and self.state not in ['draft', 'pending'] and self.operation == 'refund':
            self.env.ref('payment.cron_post_process_payment_tx')._trigger()
            return None

        # Update the payment method.
        allowed_to_modify = self.state not in ('done', 'authorized')
        if allowed_to_modify:
            provider_reference = payment_data.get('mihpayid')
            self.provider_reference = provider_reference

        entity_status = payment_data.get('status', '')
        if not entity_status:
            msg = 'Payu: Received data with missing status.'
            raise ValidationError(msg)

        # Update the payment state.
        STATUS_MAPPING = payu_consts.PAYMENT_STATUS_MAPPING  # if webhook_type == 'payment' else Payu_const.REFUND_STATUS_MAPPING
        if entity_status in STATUS_MAPPING['done']:
            self._set_done()
        elif entity_status in STATUS_MAPPING.get('pending', ''):
            self._set_pending()
        elif entity_status in STATUS_MAPPING.get('cancel', ''):
            self._set_canceled()
        elif entity_status in STATUS_MAPPING['error']:
            _logger.warning(
                'The transaction with reference %s underwent an error. Reason: %s',
                self.reference, payment_data.get('error_message'),
            )
            self._set_error(
                'An error occurred during the processing of your payment. Please try again.',
            )
        else:  # Classify unsupported payment status as the `error` tx state.
            _logger.warning(
                'Received data for transaction with reference %s with invalid payment status: %s',
                self.reference, entity_status,
            )
            self._set_error(
                f'Payu: Received data with invalid status: {entity_status}',
            )
        return None

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        """ Override of `payment` to find the transaction based on Payu data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The normalized notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        """

        if provider_code != 'payu':
            return super()._search_by_reference(provider_code, payment_data)
        reference = payment_data.get('txnid', '')
        return self.search([('reference', '=', reference), ('provider_code', '=', 'payu')])

    def _extract_amount_data(self, payment_data):
        """Override of payment to extract the amount and currency from the payment data."""
        if self.provider_code != 'payu':
            return super()._extract_amount_data(payment_data)

        """
        TODO: Improve the mechanism for extracting and validating the transaction amount.

        Context:
        PayU only processes payments in INR. To accommodate this, we manually convert the
        transaction amount to INR before initiating the payment. Consequently, the webhook
        response from PayU is unknow as it was not able to test in testing env.

        Problem:
        The base transaction model validates the provider’s amount and currency against
        the original transaction data. Since the webhook returns the amount in which format is unknown,
        this validation fails, and the transaction is incorrectly marked as an error — despite being successfully completed.

        Temporary Solution:
        Return None to skip amount validation for the Easebuzz provider until a more
        robust validation mechanism is implemented.
        """

        return None

    def _send_refund_request(self):
        """ Override of `payment` to send a refund request to PayU.

        Note: self.ensure_one()

        :param float amount_to_refund: The amount to refund.
        :return: The refund transaction created to process the refund request.
        :rtype: recordset of `payment.transaction`
        """
        if self.provider_code != 'payu':
            return super()._send_refund_request()

        payload = {
            'key': self.provider_id.payu_merchant_key,
            'command': 'cancel_refund_transaction',
            'var1': self.source_transaction_id.provider_reference,
            'var2': self.reference,
            'var3': -(self.provider_id._payu_convert_amount_to_inr(self.amount, self.currency_id)),
            'salt': self.provider_id.payu_merchant_salt,
        }

        hash_payload = payu_utils.generate_payu_hash(payload=payload, hash_sequence=payu_consts.PAYU_HASH_SEQUENCE.get('REFUND'))
        payload['hash'] = hash_payload

        try:
            self._send_api_request('POST', '/merchant/postservice?form=2', data=payload, mode='refund')
        except ValidationError as e:
            self._set_error(str(e))
