# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pprint
import hmac
from werkzeug.exceptions import Forbidden

from odoo.http import Controller, request, route

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.odoo_payment_pine_labs import const as pine_labs_const


_logger = get_payment_logger(__name__)


class PineLabsController(Controller):

    WEBHOOK_URL = '/payment/pinelabs/webhook'

    @route(WEBHOOK_URL, type='http', auth='public', methods=['POST'], csrf=False)
    def pinelabs_webhook(self):
        """ Process the notification data sent by Pinelabs to the webhook.

        :return: An empty string to acknowledge the notification.
        :rtype: str
        """
        data = request.get_json_data()
        _logger.info("Notification received from Pinelabs with data:\n%s", pprint.pformat(data))

        event_type = data['event_type']
        if event_type in pine_labs_const.HANDLED_WEBHOOK_EVENTS:
            entity_data = data['data']
            received_signature = request.httprequest.headers.get('Webhook-Signature')
            tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference(
                'pine_labs', entity_data
            )
            signed_content = f"{request.httprequest.headers.get('Webhook-Id')}.{request.httprequest.headers.get('Webhook-Timestamp')}.{request.httprequest.get_data()}"
            if tx_sudo:
                self._verify_signature(
                    signed_content.encode('utf-8'), received_signature, tx_sudo
                )
                tx_sudo._process('pine_labs', entity_data)

        return request.make_json_response('')

    @staticmethod
    def _verify_signature(
        signed_content, received_signature, tx_sudo
    ):
        """Check that the received signature matches the expected one.

        :param str signed_content: The string from signature will be calculate.
        :param str received_signature: The signature to compare with the expected signature.
        :param payment.transaction tx_sudo: The sudoed transaction referenced by the payment data

        :return: None
        :raise Forbidden: If the signatures don't match.
        """
        # Check for the received signature.
        if not received_signature:
            _logger.warning("Received payment data with missing signature.")
            raise Forbidden()

        # Compare the received signature with the expected signature.
        expected_signature = tx_sudo.provider_id._pine_labs_calculate_signature(
            signed_content
        )
        if (
            expected_signature is None
            or not hmac.compare_digest(received_signature, expected_signature)
        ):
            _logger.warning("Received payment data with invalid signature.")
