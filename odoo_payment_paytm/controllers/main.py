# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import pprint

from odoo import http
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.odoo_payment_paytm import utils as paytm_utils

_logger = get_payment_logger(__name__)


class PaytmController(http.Controller):
    _return_url = '/payment/paytm/return'
    _webhook_url = '/payment/paytm/webhook'

    @http.route(_return_url, type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def paytm_return(self, **post):
        """
        Process the payment data sent by paytm after callback from checkout.
        :param dict post: The POST data sent by paytm

        """
        # Paytm sends payment data via callback url, but we do not process it here.
        # As per Paytm docs, webhook is recommended for payment status processing.
        _logger.info(
            'Callback data received from paytm callback url:\n%s', pprint.pformat(post)
        )

        # Redirect user to payment/status page
        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False, save_session=False)
    def paytm_webhook(self, **post):
        """
        Process the payment data sent by Paytm via webhook
        :param dict post: The POST data sent by Paytm
        """
        data = post if post else request.get_json_data()

        _logger.info(
            'Notification received from Paytm webhook URL with data:\n%s', pprint.pformat(data)
        )

        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference(
            'paytm', data
        )

        if not tx_sudo:
            return ''  # Acknowledge the webhook

        # 'payment status' webhook
        if 'CHECKSUMHASH' in data:
            is_valid_checksum = paytm_utils.verifySignature(
                params=data,
                key=tx_sudo.provider_id.paytm_merchant_key,
                checksum=data.get('CHECKSUMHASH')
            )
        # 'success refund' webhook
        else:
            is_valid_checksum = paytm_utils.verifySignature(
                params=json.dumps(data.get('body'), separators=(',', ':')),
                key=tx_sudo.provider_id.paytm_merchant_key,
                checksum=data.get('head', {}).get('signature')
            )

        if is_valid_checksum:
            tx_sudo._process('paytm', data)
        else:
            _logger.warning('Invalid checksum for Paytm notification, transaction reference %s', tx_sudo.reference)
        return ''  # Acknowledge the webhook
