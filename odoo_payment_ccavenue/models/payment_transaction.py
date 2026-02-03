# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo import models
from odoo.tools.urls import urljoin as url_join

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger

from odoo.addons.odoo_payment_ccavenue import const
from odoo.addons.odoo_payment_ccavenue.utils import (
    encrypt_ccavenue_data,
    prepare_ccavenue_query_string,
)

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _compute_reference(self, provider_code, prefix=None, separator='-', **kwargs):
        """Override of `payment` to ensure that ccavenue's requirements for references are satisfied.

        ccavenue's requirements for transaction are as follows:
        - References can only be made of alphanumeric characters only.
          The prefix is generated with 'CC'. This prevents the prefix from being
          generated based on document names that may contain non-allowed characters
          (eg: INV/2020/...).

        :param str provider_code: The code of the provider handling the transaction.
        :param str prefix: The custom prefix used to compute the full reference.
        :param str separator: The custom separator used to separate the prefix from the suffix.
        :return: The unique reference for the transaction.
        :rtype: str
        """
        if provider_code != 'ccavenue':
            return super()._compute_reference(provider_code, prefix=prefix, separator=separator, **kwargs)
        is_refund = prefix and prefix.startswith('R-')
        prefix = 'CC' if not is_refund else 'RCC'
        seperator = ''
        prefix = payment_utils.singularize_reference_prefix(prefix=prefix, separator=seperator)
        return super()._compute_reference(provider_code, prefix=prefix, separator=separator, **kwargs)

    def _ccavenue_prepare_order_payload(self):
        """
        Prepare the order payload for CCAvenue payment gateway.

        :return: The dict containing the order payload.
        :rtype: dict
        """
        web_url = self.provider_id.get_base_url()
        redirect_url = f'{web_url}/payment/ccavenue/return'  # ccavenue will redirect here after payment
        cancel_url = f'{web_url}/payment/ccavenue/cancel'  # ccavenue will redirect here if payment is cancelled

        payload = {
            'merchant_id': self.provider_id.ccavenue_merchant_id,
            'order_id': self.reference,
            'currency': self.currency_id.name,
            'amount': f'{self.amount:.2f}',
            'redirect_url': redirect_url,
            'cancel_url': cancel_url,
            'language': 'EN',
            'billing_name': self.partner_name,
            'billing_address': self.partner_address,
            'billing_city': self.partner_city,
            'billing_state': self.partner_state_id.name,
            'billing_zip': self.partner_zip,
            'billing_country': self.partner_country_id.name,
            'billing_tel': self.partner_phone,
            'billing_email': self.partner_email,
        }

        return payload

    def _ccavenue_prepare_order_request(self):
        """
        Prepare the encrypted order request for CCAvenue payment gateway.

        :return: The encrypted request string.
        :rtype: str
        """
        payload = self._ccavenue_prepare_order_payload()
        query_string = prepare_ccavenue_query_string(payload)
        encrypted_request = encrypt_ccavenue_data(
            query_string, self.provider_id.ccavenue_working_key
        )

        return encrypted_request

    def _get_specific_rendering_values(self, processing_values):
        """
        Override of payment to return CCAvenue-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values for the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        if self.provider_code != 'ccavenue':
            return super()._get_specific_rendering_values(processing_values)

        encrypted_request = self._ccavenue_prepare_order_request()

        if self.provider_id.state == 'test':
            base_url = const.CCAVENUE_TEST_URL
        else:
            base_url = const.CCAVENUE_LIVE_URL

        endpoint = 'transaction/transaction.do'
        api_url = f'{url_join(base_url, endpoint)}?command=initiateTransaction'

        return {
            'api_url': api_url,
            'encrypted_request': encrypted_request,
            'access_code': self.provider_id.ccavenue_access_code,
        }

    def _extract_reference(self, provider_code, payment_data):
        """Override of `payment` to extract the reference from the payment data."""
        if provider_code != 'ccavenue':
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get('order_id')  # reference id / tx reference

    def _extract_amount_data(self, payment_data):
        """Override of `payment` to extract the amount and currency from the payment data."""
        if self.provider_code != 'ccavenue':
            return super()._extract_amount_data(payment_data)

        amount = payment_data.get('amount')
        currency = payment_data.get('currency')

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
        if self.provider_code != 'ccavenue':
            return super()._apply_updates(payment_data)

        allowed_to_modify = self.state not in ('done', 'authorized')
        # Handle Refund status polling
        if 'refund_list' in payment_data:
            # CCAvenue returns a list of refunds per order;
            # Staging API typically shows only our refund - the docs, being optimistic, suggest multiple partial refunds could exist.
            # Even though in staging refundOrder only allows one refund per order (repeat attempts raise duplicate parameter errors),
            # handle multiple entries gracefully in case the API decides to surprise us.

            refund_list = payment_data.get('refund_list', [])
            if not refund_list:
                _logger.warning(
                    'CCAvenue: Refund polling response contains empty refund_list for transaction %s',
                    self.reference
                )
                return

            refund_details = refund_list[0]

            if refund_details.get('refund_mer_ref_no') == self.source_transaction_id.reference:
                refund_status = refund_details.get('refund_status')

                if refund_status == 'TS-REFC':  # Refund Confirmed
                    self._set_done(state_message="CCAvenue: Refund successfully processed.")
                    self.env.ref('payment.cron_post_process_payment_tx')._trigger()

                elif refund_status in ['TS-REFF', 'TS-REFD']:  # Refund Failed or Declined
                    self._set_error(
                        f"CCAvenue: Refund failed with status: {refund_status}. "
                        f"Bank Ref: {refund_details.get('refund_bank_ref_no')}"
                    )
                elif refund_status == 'TS-REFA':  # Refund Awaited
                    # The state is already 'pending', so we do nothing and wait for the next poll.
                    _logger.info(
                        'Polling CCAvenue refund for tx %s: status is still Awaited (TS-REFA).',
                        self.reference
                    )
            else:
                _logger.warning(
                    'Could not find refund details for transaction %s in the polled response.',
                    self.reference
                )
            return

        # Process either payment or refund initiated data
        status = payment_data.get('order_status')  # status related to payment order
        if status is None:
            status = payment_data.get('refund_status')  # status related to refund initiated
        if status is None:
            status = payment_data.get('status')  # status related to api call error

        tracking_id = payment_data.get('tracking_id')

        # Update the provider reference
        if tracking_id and allowed_to_modify:
            self.provider_reference = tracking_id

        # Payment mode update (for payment only)
        payment_mode = payment_data.get('payment_mode')
        payment_mode_code = const.PAYMENT_METHODS_CODE_MAPPING.get(payment_mode, '')
        payment_method = self.env['payment.method']._get_from_code(payment_mode_code)
        if payment_method and allowed_to_modify:
            self.payment_method_id = payment_method

        # Payment processing
        if status == 'Success':
            self._set_done()
        elif status == 'Failure':
            # In ccavenue `failure_message` field is specifically provided
            error_msg = payment_data.get('failure_message') or payment_data.get('status_message')
            self._set_canceled(state_message=f"CCAvenue: Failure - {error_msg}")
        elif status == 'Aborted':
            self._set_canceled(state_message="CCAvenue: Payment was aborted by the user.")
        elif status == 'Invalid':
            self._set_error("CCAvenue: Invalid transaction.")
        elif status == 'Timeout':
            self._set_error("CCAvenue: Payment timed out.")

        # Refund Initiated processing
        elif status == 0:  # CCAvenue refund initiated success
            self._set_pending()
        elif status == 1:  # Refund initiated error
            error_code = payment_data.get('error_code', 'Unknown')
            error_msg = payment_data.get('reason', 'Unknown error occurred')
            self._set_error(f"CCAvenue Refund initiate Error: {error_msg} (code: {error_code})")

        # '1' indicates an API call error (plain-text response from API calls)
        elif status == '1':  # Refund api error
            error_code = payment_data.get('enc_error_code', 'Unknown')
            error_msg = payment_data.get('enc_response', 'Unknown error from CCAvenue API')
            self._set_error(f"CCAvenue Refund API Error: {error_msg} (code: {error_code}) ")
        else:
            _logger.warning(
                'Received unrecognized payment/refund state %s for transaction with reference %s',
                status,
                self.reference,
            )
            self._set_error(f"CCAvenue: Unrecognized payment/refund status. status: {status}")

    def _send_refund_request(self):
        """Override of `payment` to send a refund request to CCAvenue."""
        if self.provider_code != 'ccavenue':
            return super()._send_refund_request()

        refund_data = {
            'reference_no': self.source_transaction_id.provider_reference,
            'refund_amount': f'{-self.amount:.2f}',  # The amount is negative for refund transactions
            'refund_ref_no': self.source_transaction_id.reference
        }

        # Encrypting data
        encrypted_data = encrypt_ccavenue_data(json.dumps(refund_data), self.provider_id.ccavenue_working_key)

        params = {
            'access_code': self.provider_id.ccavenue_access_code,
            'command': 'refundOrder',
            'request_type': 'JSON',
            'response_type': 'JSON',
            'enc_request': encrypted_data,
            'version': '1.1',
        }

        # Initiates the refund request
        response = self._send_api_request('POST', '/apis/servlet/DoWebTrans', params=params)

        # Process the refund initiate response
        self._process('ccavenue', response)

    # cron method to poll refund status of initiated refunds
    def _ccavenue_poll_refund_status(self):
        """Poll the refund status for CCAvenue Refund transactions in 'pending' state."""
        transactions = self.search([('provider_code', '=', 'ccavenue'), ('state', '=', 'pending'), ('operation', '=', 'refund')])

        for tx in transactions.sudo():
            refund_data = {
                'reference_no': tx.source_transaction_id.provider_reference,
            }

            # Encrypting data
            encrypted_data = encrypt_ccavenue_data(json.dumps(refund_data), tx.provider_id.ccavenue_working_key)

            params = {
                'access_code': tx.provider_id.ccavenue_access_code,
                'command': 'getRefundDetails',
                'request_type': 'JSON',
                'response_type': 'JSON',
                'enc_request': encrypted_data,
                'version': '1.1',
            }

            response = tx._send_api_request('POST', '/apis/servlet/DoWebTrans', params=params)
            tx._process('ccavenue', response)
