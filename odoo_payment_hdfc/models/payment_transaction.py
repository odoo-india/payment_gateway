# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import logging
from io import BytesIO

import qrcode
from odoo import api, fields, models
from odoo.addons.odoo_payment_hdfc import const as hdfc_consts
from odoo.addons.odoo_payment_hdfc import utils as hdfc_utils
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    cust_ref_no = fields.Char(
        string='Customer Unique Reference Number',
        readonly=True,
    )

    def _get_specific_processing_values(self, processing_values):
        """Return HDFC-specific values including the QR to frontend."""
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'hdfc':
            return res
        txn_env = 'test' if self.provider_id.state == 'test' else 'prod'
        qr_payload = self._hdfc_prepare_txn_payload()

        res.update({
            'txn_env': txn_env,
            'payload': qr_payload,
        })
        return res

    def _hdfc_prepare_txn_payload(self):
        """Prepare the payload containing QR data passed to frontend."""
        qr = self._hdfc_generate_dynamic_qr()
        return {
            'qr_image': qr['qr_base64'],
        }

    def _hdfc_generate_dynamic_qr(self):
        """Generate a dynamic UPI QR for HDFC using transaction data."""

        qr_string = hdfc_utils.generate_qr_code(
            self.provider_id,
            txn_ref=self.reference,
            txn_note='',
            amount=self.amount
        )

        qr_img = qrcode.make(qr_string, border=0)
        buffer = BytesIO()
        qr_img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

        return {
            'qr_base64': f'data:image/png;base64,{qr_base64}'
        }

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction based on the payment data.
            Sample payment_data: {
                'txn_id': '6409196',
                'order_no': 'S00003-15',
                'amount': '500.00',
                'txn_auth_date': '2025:12:17 04:39:27',
                'status': 'SUCCESS',
                'status_desc': 'Transaction success',
                'resp_code': '00',
                'approval_no': 'NA',
                'payer_vpa': 'sumit039@hdfcbank',
                'rrn': '535101448062',
                'ref_id': 'NA',
                'payer_bank': [
                    'Mybene',
                    '857679479890124',
                    'AABE0876543',
                    'NA'
                ],
                'txn_meta': [
                    'PAY',
                    'https://upitest.hdfcbank.com',
                    'NA',
                    'HDFC400E09AC55DB44EE803B797122DE136',
                    'NA',
                    ''
                ],
                'payee_vpa': 'odooin@hdfcbank',
                'payer_acc_type': 'NA',
                'payer_name': 'NA'
            }
        """
        if self.provider_code != 'hdfc':
            return super()._apply_updates(payment_data)
        # Update the provider reference.
        if 'txn_meta' in payment_data and payment_data.get('txn_meta')[0] == 'PAY':
            webhook_type = 'payment'
        else:
            webhook_type = 'refund'

        # Update the payment method.
        allowed_to_modify = self.state not in ('done', 'authorized')
        if allowed_to_modify:
            self.provider_reference = payment_data.get('txn_id').strip()

        entity_status = payment_data.get('status', '').strip()
        if not entity_status:
            msg = 'HDFC: Received data with missing status.'
            raise ValidationError(msg)

        # Update the payment state.
        STATUS_MAPPING = hdfc_consts.PAYMENT_STATUS_MAPPING
        if entity_status in STATUS_MAPPING['done']:
            self.cust_ref_no = payment_data.get('rrn', '').strip()
            self._set_done()
            # Immediately post-process the transaction if it is a refund, as the post-processing
            # will not be triggered by a customer browsing the transaction from the portal.
            if webhook_type == 'refund':
                self.env.ref('payment.cron_post_process_payment_tx')._trigger()
        elif entity_status in STATUS_MAPPING.get('pending', ''):
            self._set_pending()
        elif entity_status in STATUS_MAPPING.get('cancel', ''):
            self._set_canceled()
        elif entity_status in STATUS_MAPPING['error']:
            _logger.warning(
                'The transaction with reference %s underwent an error. Reason: %s',
                self.reference, payment_data,
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
                f'HDFC: Received data with invalid status: {entity_status}',
            )
        return None

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        """ Override of `payment` to find the transaction based on HDFC data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The normalized notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        """
        if provider_code != 'hdfc':
            return super()._search_by_reference(provider_code, payment_data)

        reference = payment_data.get('order_no').strip()
        return self.search([('reference', '=', reference), ('provider_code', '=', 'hdfc')])

    def _extract_amount_data(self, payment_data):
        """Override of payment to extract the amount and currency from the payment data."""
        if self.provider_code != 'hdfc':
            return super()._extract_amount_data(payment_data)

        return {
            'amount': float(payment_data.get('amount').strip()),  # HDFC only supports payment API
            'currency_code': 'INR',  # HDFC doesn't provide currency code in webhook data. And this is constant as INR for all.
        }

    def _send_refund_request(self):
        """ Override of `payment` to send a refund request to HDFC.

        Note: self.ensure_one()

        :param float amount_to_refund: The amount to refund.
        :return: The refund transaction created to process the refund request.
        :rtype: recordset of `payment.transaction`
        """
        if self.provider_code != 'hdfc':
            return super()._send_refund_request()

        payload = {
            # Not part of Payload
            'merchant_key': self.provider_id.hdfc_merchant_key,
            # Part of Payload
            'merchant_id': self.provider_id.hdfc_merchant_id,
            'new_order_no': self.reference,
            'original_order_no': self.source_transaction_id.reference,
            'original_txn_ref_no': self.source_transaction_id.provider_reference,
            'original_cust_ref_no': self.source_transaction_id.cust_ref_no,
            'remarks': 'Refund',
            'refund_amount': -(self.amount),
            'currency': 'INR',
            'payment_type': 'P2P',
            'txn_type': 'PAY',
            'additional_10': 'NA'
        }
        hash_payload = hdfc_utils.generate_hdfc_refund_string(payload=payload, hash_sequence=hdfc_consts.HDFC_HASH_SEQUENCE.get('REFUND'))
        payload['requestMsg'] = hash_payload
        request_payload = {
            'pgMerchantId': self.provider_id.hdfc_merchant_id,
            'requestMsg': hash_payload
        }
        try:
            response = self._send_api_request('POST', '/upi/refundReqSvc', json=request_payload, mode='refund')
            if response.get('status') == 'SUCCESS':
                # Find the corresponding payment transaction
                tx_sudo = self._search_by_reference('hdfc', response)
                if not tx_sudo:
                    _logger.warning('No matching HDFC transaction found for payload: %s', response.get('order_no'))

                # Process the verified transaction
                try:
                    tx_sudo._process('hdfc', response)
                    _logger.info('HDFC transaction processed successfully (Ref: %s)', tx_sudo.reference)
                except Exception:
                    _logger.exception('Failed to process HDFC transaction')
        except ValidationError as e:
            self._set_error(str(e))
