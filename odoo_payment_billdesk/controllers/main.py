# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pprint
from werkzeug.exceptions import Forbidden

from odoo.http import Controller, request, route

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.odoo_payment_billdesk import utils

_logger = get_payment_logger(__name__)


class BilldeskController(Controller):
    RETURN_URL = "/payment/billdesk/return"
    WEBHOOK_URL = "/payment/billdesk/webhook"

    @route(RETURN_URL, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def billdesk_return_from_checkout(self, **data):
        """Process the notification data sent by Billdesk after redirection.
        :param dict data: The notification data.
        """
        _logger.info(
            "Notification received from Billdesk with data:\n%s", pprint.pformat(data)
        )
        terminal_state = data.get('terminal_state', '')
        if terminal_state == '111':  # When user cancels the transaction
            tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference(
                'billdesk', data
            )
            tx_sudo._set_canceled()
        return request.redirect('/payment/status')

    @route(WEBHOOK_URL, type='http', auth='public', methods=['POST'], csrf=False)
    def billdesk_webhook(self, **data):
        """Process the notification data sent by Billdesk to the webhook.
        :return: An empty string to acknowledge the notification.
        :rtype: str
        """
        _logger.info(
            "Webhook received from Billdesk with data:\n%s", pprint.pformat(data)
        )
        encrypted_response = data.get('transaction_response', '') or request.httprequest.data.decode()
        if not encrypted_response:
            _logger.warning("Empty response from BillDesk")
            raise Forbidden()
        billdesk_provider = request.env['payment.provider'].sudo().search([('code', '=', 'billdesk')], limit=1)
        if not billdesk_provider:
            _logger.error("Billdesk: No payment provider found")
            return request.make_json_response('')

        payload = utils.billdesk_response(
            encrypted_response,
            billdesk_provider.billdesk_encryption_key,
            billdesk_provider.billdesk_signing_key,
        )

        if not payload:
            _logger.warning("Unable to decrypt webhook data sent from BillDesk")
            raise Forbidden()
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference(
            'billdesk', payload
        )
        tx_sudo._process('billdesk', payload)
        return request.make_json_response("")
