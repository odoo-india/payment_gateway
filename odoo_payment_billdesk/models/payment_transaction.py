# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, models
from odoo.http import request
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger

from odoo.addons.odoo_payment_billdesk import const as billdesk_const
from odoo.addons.odoo_payment_billdesk.controllers.main import BilldeskController

from datetime import datetime, timezone, timedelta
import time

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _compute_reference(self, provider_code, prefix=None, separator='-', **kwargs):
        """Override of `payment` to ensure that BillDesk references are unique.

        :param str provider_code: The code of the provider handling the transaction.
        :param str prefix: The custom prefix used to compute the full reference.
        :param str separator: The custom separator used to separate the prefix from the suffix.
        :return: The unique reference for the transaction.
        :rtype: str
        """
        if provider_code != 'billdesk':
            return super()._compute_reference(provider_code, prefix, separator, **kwargs)
        is_refund = prefix and prefix.startswith('R-')
        prefix = 'bd-' if not is_refund else 'R-bd-'
        prefix = payment_utils.singularize_reference_prefix(prefix=prefix, separator='')
        return super()._compute_reference(
            provider_code, prefix=prefix, separator='', **kwargs
        )

    def _get_specific_processing_values(self, processing_values):
        """Override of `payment` to return billdesk-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the
                                        transaction.
        :return: The provider-specific processing values.
        :rtype: dict
        """
        if self.provider_code != 'billdesk':
            return super()._get_specific_processing_values(processing_values)
        order, return_url = self._billdesk_create_payment_order()
        links = order.get('links', [])
        auth_token = ""
        if len(links) >= 2:
            auth_token = links[1].get('headers', {}).get('authorization', '')
        pm_code = (
            self.payment_method_id.primary_payment_method_id or self.payment_method_id
        ).code
        billdesk_payment_category = billdesk_const.PAYMENT_METHOD_CODES_MAPPING[pm_code]
        return {
            'auth_token': auth_token,
            'merchant_id': self.provider_id.billdesk_merchant_id,
            'bd_order_id': order.get('bdorderid', ''),
            'payment_categories': billdesk_payment_category,
            'return_url': return_url,
            'txn_env': 'test' if self.provider_id.state == 'test' else 'prod',
        }

    def _billdesk_create_payment_order(self):
        """Create and return an Order object to initiate the payment.

        :return: The created Order.
        :rtype: dict
        """
        web_url = self.provider_id.get_base_url()
        return_url = f"{web_url}{BilldeskController.RETURN_URL}"
        payload = self._billdesk_prepare_order_payload(return_url)
        order_data = {}
        try:
            order_data = self._send_api_request(
                'POST', '/payments/ve1_2/orders/create', data=payload
            )
        except ValidationError as e:
            self._set_error(str(e))
        return order_data, return_url

    def _billdesk_prepare_order_payload(self, return_url):
        """Prepare the payload for the order request based on the transaction values.

        :return: The request payload.
        :rtype: dict
        """
        order_date = (
            datetime.now(timezone(timedelta(seconds=-time.timezone)))
            .replace(microsecond=0)
            .isoformat()
        )
        payload = {
            "orderid": self.reference,
            "mercid": self.provider_id.billdesk_merchant_id,
            "order_date": order_date,
            "amount": self.amount,
            "currency": self.currency_id.iso_numeric,
            "itemcode": "DIRECT",  # Static from Billdesk
            "device": {
                "init_channel": "internet",
                "ip": request.httprequest.remote_addr,
                "user_agent": request.httprequest.headers.get("User-Agent", ""),
                "accept_header": request.httprequest.headers.get("Accept", ""),
            },
            "additional_info": {f"additonal_info{i}": "na" for i in range(1, 8)},
            "ru": return_url,
        }
        return payload

    def _send_refund_request(self):
        """ Override of `payment` to send refund request to Billdesk. """
        if self.provider_code != 'billdesk':
            return super()._send_refund_request()

        transaction_date = (
            datetime.now(timezone(timedelta(seconds=-time.timezone)))
            .replace(microsecond=0)
            .isoformat()
        )
        payload = {
            'transactionid': self.source_transaction_id.provider_reference,
            'orderid': self.source_transaction_id.reference,
            'mercid': self.provider_id.billdesk_merchant_id,
            'transaction_date': transaction_date,
            'txn_amount': self.source_transaction_id.amount,
            'refund_amount': -self.amount,
            'currency': self.source_transaction_id.currency_id.iso_numeric,
            'merc_refund_ref_no': self.reference,
        }

        try:
            payment_data = self._send_api_request('POST', '/payments/ve1_2/refunds/create', data=payload)
            self._process(provider_code='billdesk', payment_data=payment_data)
        except ValidationError as e:
            self._set_error(str(e))

    def _search_by_reference(self, provider_code, payment_data):
        """Override of `payment` to find the transaction based on Billdesk data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The normalized notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        """

        if provider_code != 'billdesk':
            return super()._search_by_reference(provider_code, payment_data)
        reference = payment_data.get('orderid', '')
        tx = self.search(
            [('reference', '=', reference), ('provider_code', '=', 'billdesk')]
        )
        return tx

    def _extract_amount_data(self, payment_data):
        """Override of payment to extract the amount and currency from the payment data."""
        if self.provider_code != 'billdesk':
            return super()._extract_amount_data(payment_data)

        currency_iso_code = int(payment_data.get('currency'))
        currency = self.env['res.currency'].search(
            [('iso_numeric', '=', currency_iso_code)]
        )

        webhook_type = payment_data.get('objectid')
        amount_key = 'refund_amount' if webhook_type == 'refund' else 'amount'
        return {
            'amount': float(payment_data.get(amount_key)),
            'currency_code': currency.name,
        }

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction based on the payment data."""
        if self.provider_code != 'billdesk':
            return super()._apply_updates(payment_data)

        # Update the provider reference.
        webhook_type = payment_data.get('objectid')
        reference_key = 'transactionid' if webhook_type == 'transaction' else 'refundid'
        provider_reference = payment_data.get(reference_key)
        if not provider_reference:
            raise ValidationError(_("Billdesk: Received data with missing id."))

        allowed_to_modify = self.state not in ('done', 'authorized')
        if allowed_to_modify:
            self.provider_reference = provider_reference

        # Update the payment method.
        if webhook_type == 'transaction':
            payment_method_type = payment_data.get('payment_method_type', '')
            payment_method = self.env['payment.method']._get_from_code(payment_method_type)
            if allowed_to_modify and payment_method:
                self.payment_method_id = payment_method

        # Update the payment state.
        status_key = 'auth_status' if webhook_type == 'transaction' else 'refund_status'
        entity_status = payment_data.get(status_key)
        if not entity_status:
            raise ValidationError(_("Billdesk: Received data with missing status."))

        STATUS_MAPPING = billdesk_const.PAYMENT_STATUS_MAPPING if webhook_type == 'transaction' else billdesk_const.REFUND_STATUS_MAPPING
        if entity_status in STATUS_MAPPING.get('done', ''):
            self._set_done()

            # Immediately post-process the transaction if it is a refund, as the post-processing
            # will not be triggered by a customer browsing the transaction from the portal.
            if self.operation == 'refund':
                self.env.ref('payment.cron_post_process_payment_tx')._trigger()
        elif entity_status in STATUS_MAPPING.get('in progress', ''):
            self._set_pending()
        elif entity_status in STATUS_MAPPING.get('cancel', ''):
            self._set_canceled()
        elif entity_status in STATUS_MAPPING.get('error', ''):
            _logger.warning(
                "The transaction with reference %s underwent an error. Reason: %s",
                self.reference,
                payment_data.get('transaction_error_desc'),
            )
            self._set_error(
                "An error occurred during the processing of your payment. Please try again."
            )
        else:  # Classify unsupported payment status as the `error` tx state.
            _logger.warning(
                "Received data for transaction with reference %s with invalid payment status: %s",
                self.reference,
                entity_status,
            )
            self._set_error(
                f"Billdesk: Received data with invalid status: {entity_status}"
            )
