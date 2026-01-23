# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pprint

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

from odoo.addons.odoo_payment_ccavenue.utils import (
    decrypt_ccavenue_data,
    parse_ccavenue_response,
)

_logger = get_payment_logger(__name__)


class CCavenueController(http.Controller):
    _return_url = '/payment/ccavenue/return'
    _cancel_url = '/payment/ccavenue/cancel'
    _webhook_url = '/payment/ccavenue/webhook'

    @http.route([_return_url, _cancel_url], type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def ccavenue_return(self, **post):
        """
        Process the payment data sent by CCAvenue after redirection from checkout.

        :param dict post: The data sent by CCAvenue
        """
        # Redirect user to `payment/status` page after CCAvenue returns.
        # This prevents CCAvenue from redirecting to the webhook URL (as per their docs).
        # Note: CCAvenue sends payment transaction data here in redirect URL also, but we don't process it
        #       we only process data received in webhook (CCAvenue's Dynamic Event Notification)

        # Redirect the user to the status page
        return request.redirect('/payment/status')

    @http.route([_webhook_url], type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def ccavenue_webhook(self, **post):
        """
        Process the payment data sent by CCAvenue via webhook.
        In CCAvenue, this is called Dynamic Event Notification.
        """
        _logger.info(
            'Notification received from CCAvenue with data:\n%s', pprint.pformat(post)
        )

        # CCAvenue sends the encrypted response in `encResp` parameter
        enc_resp = post.get('encResp')

        if not enc_resp:
            # if no encResp, we cannot process the request
            _logger.warning('CCAvenue: No encResp found in the request')
            raise Forbidden()

        # Get the payment provider
        payment_provider = request.env['payment.provider'].sudo().search([('code', '=', 'ccavenue')], limit=1)

        if not payment_provider:
            _logger.error('CCAvenue: No payment provider found')
            return ''

        # Verify the request by decrypting
        decrypted_data = self._verify_request_by_decryption(
            enc_resp, payment_provider.ccavenue_working_key
        )

        if not decrypted_data:
            _logger.warning('CCAvenue: Invalid request - decryption failed')
            raise Forbidden()

        _logger.info(
            'CCAvenue: Decrypted data:\n%s', pprint.pformat(decrypted_data)
        )
        # Process the transaction using the _process method
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('ccavenue', decrypted_data)
        tx_sudo._process('ccavenue', decrypted_data)

        return ''

    def _verify_request_by_decryption(self, enc_resp, working_key):
        """
        Verify CCAvenue request by decrypting encResp with working key.

        CCAvenue encrypts payloads with a shared secret key (working key). Successful decryption
        confirms authenticity, as CCAvenue provides no other verification method.
        """
        try:
            decrypted_string = decrypt_ccavenue_data(enc_resp, working_key)
            decrypted_data = parse_ccavenue_response(decrypted_string)
            return decrypted_data
        except ValueError:
            return False
