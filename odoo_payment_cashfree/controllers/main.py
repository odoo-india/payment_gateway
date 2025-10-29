# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint
import hmac

from werkzeug.exceptions import Forbidden

from odoo import _
from odoo.http import Controller, request, route
from odoo.exceptions import ValidationError

from odoo.addons.odoo_payment_cashfree import const

_logger = logging.getLogger(__name__)


class CashfreeController(Controller):

    RETURN_URL = '/payment/cashfree/return'
    WEBHOOK_URL = '/payment/cashfree/webhook'

    @route(RETURN_URL, type='http', auth='public', methods=['GET'])
    def cashfree_return_from_checkout(self, **data):
        """
        Handles the redirect after Cashfree checkout.

        This method is invoked when:
        - The user abandons the iFrame (status = 'error').
        - The payment is completed (status = 'SUCCESS').

        - If the status is 'error', the transaction is marked as canceled.
        - If the status is 'SUCCESS', no action is taken; the final status is determined via webhook.

        After processing, the user is redirected to /payment/status.
        """
        _logger.info("Notification received from CashFree with data:\n%s", pprint.pformat(data))
        if data.get('status', '') == 'error':
            order_id = data.get('orderId')
            tx_sudo = request.env['payment.transaction'].sudo().search([('reference', '=', order_id)])
            if not tx_sudo:
                raise ValidationError(_("No transaction found for orderId '%s'", order_id))
            tx_sudo._set_canceled()
        return request.redirect('/payment/status')

    @route(WEBHOOK_URL, type='http', auth='public', methods=['POST'], csrf=False)
    def cashfree_webhook(self):
        """ Process the notification data sent by CashFree to the webhook.

        :return: An empty string to acknowledge the notification.
        :rtype: str
        """
        response = request.get_json_data()
        if not response:
            _logger.error("No JSON data received in the request.")
            return request.make_json_response({'error': 'No JSON data received'}, status=400)
        raw_data = request.httprequest
        event_type = response.get('type', '')
        if event_type not in const.HANDLED_WEBHOOK_EVENTS:
            _logger.warning("Unhandled event type: %s", event_type)
            return request.make_json_response('', status=200)

        entity_type = 'payment' if event_type in const.WEBHOOK_TYPE_MAPPING['payment'] else 'refund'
        response.update(entity_type=entity_type)
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference(
            'cashfree', response
        )
        signature = request.httprequest.headers.get('x-webhook-signature')
        if not signature:
            _logger.error("Missing required webhook components.")
            return "Missing components", 400
        if tx_sudo:
            self._verify_signature(raw_data, signature, tx_sudo)
            tx_sudo._process('cashfree', response)
        else:
            _logger.warning("Transaction not found for reference: %s", response.get('reference'))
        return request.make_json_response('')

    @staticmethod
    def _verify_signature(payment_data, received_signature, tx_sudo):
        """Check that the received signature matches the expected one.

        :param dict payment_data: The payment data.
        :param str received_signature: The signature received with the payment data.
        :param payment.transaction tx_sudo: The sudoed transaction referenced by the payment data.
        :return: None
        :raise Forbidden: If the signatures don't match.
        """
        expected_signature = tx_sudo.provider_id._cf_generate_digital_sign(
            payment_data, incoming=True
        )
        if not hmac.compare_digest(received_signature, expected_signature):
            _logger.warning("Received payment data with invalid signature")
            raise Forbidden()
