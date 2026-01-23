# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo import api, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger

from odoo.addons.odoo_payment_paytm import const
from odoo.addons.odoo_payment_paytm import utils as paytm_utils

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):

    _inherit = 'payment.transaction'

    def _paytm_prepare_initiate_payment_payload(self):
        pm_code = (self.payment_method_id.primary_payment_method_id or self.payment_method_id).code
        paytm_pm_code = const.PAYMENT_METHOD_CODES_MAPPING.get(pm_code)
        enablePaymentModes = [{'mode': pm} for pm in paytm_pm_code]

        web_url = self.provider_id.get_base_url()
        callback_url = f'{web_url}/payment/paytm/return'

        payload = {
            'body': {
                'requestType': 'Payment',
                'mid': self.provider_id.paytm_merchant_id,
                'websiteName': 'WEBSTAGING' if self.provider_id.state == 'test' else 'DEFAULT',
                'orderId': self.reference,
                'txnAmount': {
                    'value': str(self.amount),
                    'currency': self.currency_id.name,
                },
                'userInfo': {
                    'custId': str(self.partner_id.id),
                },
                'enablePaymentMode': enablePaymentModes,
                'callbackUrl': callback_url,
            }
        }

        checksum = paytm_utils.generateSignature(
            json.dumps(payload['body']), self.provider_id.paytm_merchant_key
        )

        payload['head'] = {
            'signature': checksum
        }

        return payload

    def _paytm_initiate_payment_order(self):
        req_payload = self._paytm_prepare_initiate_payment_payload()
        url_params = {
            'mid': self.provider_id.paytm_merchant_id,
            'orderId': self.reference,
        }
        order_data = {}
        try:
            order_data = self._send_api_request('POST', '/theia/api/v1/initiateTransaction', json=req_payload, params=url_params)
        except ValidationError as e:
            self._set_error(str(e))
        return order_data

    def _get_specific_processing_values(self, processing_values):
        """ Override of `payment` to return paytm-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction.
        :return: The provider-specific processing values.
        :rtype: dict
        """
        if self.provider_code != 'paytm':
            return super()._get_specific_processing_values(processing_values)

        order_data = self._paytm_initiate_payment_order()

        txn_token = order_data.get('body', {}).get('txnToken')
        res = {
            'merchant_id': self.provider_id.paytm_merchant_id,
            'orderId': self.reference,
            'amount': str(self.amount),
            'tokenType': 'TXN_TOKEN',
            'token': txn_token,
            'tx_env': 'TEST' if self.provider_id.state == 'test' else 'PROD',
        }
        return res

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        """ Override of `payment` to find the transaction based on Paytm data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The normalized notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        """

        if provider_code != 'paytm':
            return super()._search_by_reference(provider_code, payment_data)

        reference = payment_data.get('ORDERID')
        if reference:
            tx = self.search([('reference', '=', reference), ('provider_code', '=', 'paytm')])
        else:
            refund_reference = payment_data.get('body', {}).get('refundId')
            if refund_reference:
                tx = self.search([('provider_reference', '=', refund_reference), ('provider_code', '=', 'paytm')])
            else:
                _logger.warning('No ORDERID or refundId found in paytm notification data: %s', payment_data)
        if not tx:
            _logger.warning('No transaction found for paytm notification with reference %s', reference)
        return tx

    def _extract_amount_data(self, payment_data):
        """Override of `payment` to extract the amount and currency from the payment data."""
        if self.provider_code != 'paytm':
            return super()._extract_amount_data(payment_data)

        amount = payment_data.get('ORDERID')
        currency = payment_data.get('CURRENCY')

        if amount and currency:
            try:
                return {
                    'amount': float(amount),
                    'currency_code': currency,
                }
            except (ValueError, TypeError):
                return None
        return None

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction based on the payment or refund data."""
        if self.provider_code != 'paytm':
            return super()._apply_updates(payment_data)

        body = payment_data.get('body', {})
        # if payment_data is 'ORDERID key exists' it means this is from payment status webhook
        if payment_data.get('ORDERID'):
            # orderId exists in payment_data it means this payment_data is from webhook
            payment_mode = payment_data.get('PAYMENTMODE')
            payment_mode_code = const.PAYMENT_METHODS_MAPPING.get(payment_mode, '')
            payment_method = self.env['payment.method']._get_from_code(payment_mode_code)
            if payment_method:
                self.payment_method_id = payment_method

            tracking_id = payment_data.get('TXNID')
            if tracking_id:
                self.provider_reference = tracking_id

            status = payment_data.get('STATUS')

            if status == 'TXN_SUCCESS':
                self._set_done()
            elif status == 'TXN_FAILURE':
                message = payment_data.get('RESPMSG')
                self._set_error(message)
            elif status == 'PENDING':
                message = payment_data.get('RESPMSG')
                self._set_pending(state_message=message)
            else:
                message = f"Unknown status received from Paytm: {status}"
                self._set_error(message)

        elif payment_data.get('refund_initiated'):
            # There is no such key from 'refund/apply' API response to identify it is refund response
            # So we are adding custom key 'refund_initiated' in _send_refund_request method
            # This is response from 'refund/apply' API
            result_info = body.get('resultInfo', {})
            code = result_info.get('resultCode')
            message = result_info.get('resultMsg')
            refund_tracking_id = body.get('refundId')
            if refund_tracking_id:
                self.provider_reference = refund_tracking_id
            self._set_pending(state_message=f"Refund request is pending: {message} (code: {code})")

        # Failure from 'Success Refund Webhook'
        elif body.get('rejectRefundReasonCode') and body.get('status') == 'FAILED':
            # this is failure response from 'Success Refund Webhook'
            code = body.get('rejectRefundReasonCode')
            message = body.get('rejectRefundReasonMessage')
            self._set_error(f"Refund request failed: {message} (code: {code})")

        # Success from 'Success Refund Webhook'
        elif body.get('userCreditInitiateTimestamp'):
            # this is success response from 'Success Refund Webhook'
            self._set_done()
            self.env.ref('payment.cron_post_process_payment_tx')._trigger()

        else:
            _logger.warning("Received unknown payment data from Paytm: %s", payment_data)
            self._set_error(f"Received unknown payment data from Paytm. Data: {payment_data}")

    def _send_refund_request(self):
        """Override of `payment` to send refund request to Paytm."""
        if self.provider_code != 'paytm':
            return super()._send_refund_request()

        payload = {
            'body': {
                'mid': self.provider_id.paytm_merchant_id,
                'txnType': 'REFUND',
                'orderId': self.source_transaction_id.reference,
                'txnId': self.source_transaction_id.provider_reference,
                'refId': self.reference,
                'refundAmount': str(-self.amount),
            }
        }

        checksum = paytm_utils.generateSignature(
            json.dumps(payload['body']), self.provider_id.paytm_merchant_key
        )

        payload['head'] = {
            'signature': checksum
        }

        try:
            response_content = self.provider_id._send_api_request(
                'POST', '/refund/apply', json=payload
            )
            response_content['refund_initiated'] = True
            self._process('paytm', response_content)
        except ValidationError as e:
            self._set_error(str(e))
