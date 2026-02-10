import pprint

from odoo.addons.odoo_payment_hdfc import const as hdfc_consts
from odoo.addons.odoo_payment_hdfc import utils as hdfc_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.fields import Command
from odoo.http import Controller, request, route

_logger = get_payment_logger(__name__)


class HDFCController(Controller):

    RETURN_URL = '/payment/hdfc/return'
    WEBHOOK_URL = '/payment/hdfc/webhook'

    @route(RETURN_URL, type='http', auth='public', methods=['GET'])
    def hdfc_return_from_checkout(self, **payload):
        """Handle HDFC redirect after checkout completion.

        After the user completes a payment using HDFC's dynamic QR Code, they are redirected
        back to this endpoint. This route does **not** process the transaction because
        HDFC sends the authoritative transaction details to the webhook endpoint.
        It simply acknowledges the redirect and forwards the user to the payment status page.

        :param dict payload: The query parameters received from HDFC upon redirection,
                        usually containing `txnid`, `status`, and other fields.
        :return: A redirection response to the payment status page.
        :rtype: werkzeug.wrappers.Response
        """
        _logger.info('HDFC return redirect received with payload:\n%s', pprint.pformat(payload))
        # No processing needed — main payload is received via the webhook
        return request.redirect('/payment/status')

    @route(WEBHOOK_URL, type='http', auth='public', methods=['POST'], csrf=False)
    def hdfc_webhook(self, **payload):
        """
        Handle webhook notifications received from the HDFC payment gateway.

        This endpoint receives encrypted callback payloads from HDFC, validates the
        merchant identity, decrypts and parses the response, determines the payment
        event type and flow (sale order or invoice), and triggers the corresponding
        transaction processing logic.

        The method always returns an empty JSON response as an acknowledgment to
        the HDFC server, even in case of processing failures, as per the gateway
        integration requirements.

        :param dict payload: The raw HTTP POST payload sent by HDFC.
        :return: An empty JSON response acknowledging receipt of the webhook.
        :rtype: werkzeug.wrappers.Response
        """
        _logger.info('Notification received from HDFC with payload:\n%s', pprint.pformat(payload))

        merchant_response = request.httprequest.form.get('meRes')
        merchant_id = request.httprequest.form.get('pgMerchantId')

        if not merchant_response:
            _logger.warning('meRes not found:\n%s', pprint.pformat(payload))
            return 'NO meRes', 400

        if not merchant_id:
            _logger.warning('pgMerchantId not found:\n%s', pprint.pformat(payload))
            return 'NO pgMerchantId', 400

        merchant_info = request.env['payment.provider'].sudo()._get_hdfc_payment_provider(merchant_id=merchant_id)

        if not merchant_info:
            _logger.warning('No Merchant found with the given credentials: %s', merchant_id)
            return request.make_json_response('')

        try:
            hdfc_payload = hdfc_utils.decrypt_response(merchant_response, merchant_info.hdfc_merchant_key)
        except ValueError:
            _logger.warning('Decryption failed, Invalid Response')
            return request.make_json_response('')

        try:
            hdfc_payload_parsed = HDFCController._parse_callback_response(hdfc_payload)
        except ValueError:
            _logger.warning('Parsing failed, Invalid Response')
            return request.make_json_response('')

        payment_flow = HDFCController._extract_payment_flow(hdfc_payload_parsed)

        if payment_flow == 0:
            # 0: Normal Flow
            HDFCController._process_sale_order(hdfc_payload_parsed)
        elif payment_flow == 1:
            # 1: Invoice flow
            HDFCController._process_invoice(hdfc_payload_parsed)

        # Always return empty string as acknowledgment
        return request.make_json_response('')

    @staticmethod
    def _parse_callback_response(decrypted_text):
        """
        Parse the decrypted HDFC callback response into a structured dictionary.

        The HDFC UPI callback payload is received as a pipe ('|') separated string
        containing fixed-position fields. This method validates the payload format,
        extracts the relevant transaction details, and normalizes nested metadata
        fields separated by exclamation marks ('!').

        Ex. 6409196|S00003-15|500.00|2025:12:17 04:39:27|SUCCESS|Transaction success|00|NA|sumit039@hdfcbank|535101448062|NA|null|null|null|null|null|Mybene!857679479890124!AABE0876543!NA|PAY!https://upitest.hdfcbank.com!NA!HDFC400E09AC55DB44EE803B797122DE136!NA!|odooin@hdfcbank!NA!NA|NA|NA

        :param str decrypted_text: The decrypted raw callback response string
            received from HDFC.
        :return: A dictionary containing the parsed transaction details.
        :rtype: dict
        :raises ValueError: If the response does not contain the expected number
            of fields.
        """
        parts = decrypted_text.split('|')
        if len(parts) < 21:
            raise ValueError(f'Expected 21 fields, got {len(parts)}')

        return {
            'txn_id': parts[0],                     # 6409196
            'order_no': parts[1],                   # S00003-15
            'amount': parts[2],                     # 500.00
            'txn_auth_date': parts[3],              # 2025:12:17 04:39:27
            'status': parts[4],                     # SUCCESS
            'status_desc': parts[5],                # Transaction success
            'resp_code': parts[6],                  # 00
            'approval_no': parts[7],                # NA
            'payer_vpa': parts[8],                  # sumit039@hdfcbank
            'rrn': parts[9],                        # 535101448062
            'ref_id': parts[10],                    # NA
            # Composite fields (!-separated)     # |null|null|null|null|null|
            'payer_bank': parts[16].split('!'),             # Mybene!857679479890124!AABE0876543!NA
            'txn_meta': parts[17].split('!'),               # PAY!https://upitest.hdfcbank.com!NA!HDFC400E09AC55DB44EE803B797122DE136!NA!
            'payee_vpa': parts[18].split('!')[0],           # odooin@hdfcbank!NA!NA
            'payer_acc_type': parts[19].split('!')[0],      # |NA
            'payer_name': parts[20].split('!')[0],          # |NA
        }

    @staticmethod
    def _extract_payment_flow(hdfc_payload_parsed):
        """
        Determine the payment flow type from the HDFC webhook payload.

        This method inspects the HDFC 'order_no' reference to identify from
        where the transaction is originated
            0: From Sales Order
            1: From Invoice print

        :param dict hdfc_payload_parsed: The decrypted and parsed webhook payload
            received from HDFC.
        :return: '1' if the reference corresponds to an invoice print flow,
            '0' otherwise.
        :rtype: int
        """
        order_no = hdfc_payload_parsed.get('order_no') or ''
        return int(order_no.startswith(hdfc_consts.HDFC_INV_REF_PREFIX))

    @staticmethod
    def _process_invoice(hdfc_payload_parsed):
        """
        Create and process a payment transaction for an invoice based on an HDFC webhook payload.

        This method locates the invoice linked to the HDFC transaction reference, retrieves the
        configured HDFC payment provider and its UPI payment method, creates a corresponding
        'payment.transaction' record, and processes it using the HDFC provider logic.

        :param dict hdfc_payload_parsed: The decrypted and parsed webhook payload
            received from HDFC.
        :return: 'True' if the transaction was created and processed, 'False' otherwise.
        :rtype: bool
        """
        env = request.env
        order_no = hdfc_payload_parsed.get('order_no')

        # Get invoice
        invoice = env['account.move'].sudo().search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('hdfc_txn_id', '=', order_no)
        ], limit=1)

        if not invoice:
            _logger.warning('Invoice not found for order_no: %s', order_no)
            return False

        # Get HDFC provider
        provider = env['payment.provider'].sudo()._get_hdfc_payment_provider(
            company_id=invoice.company_id.id
        )
        if not provider:
            _logger.warning('HDFC provider not found')
            return False

        # Get UPI payment method
        upi_method = env['payment.method'].sudo().search([
            ('id', 'in', provider.payment_method_ids.ids),
            ('code', '=', 'upi')
        ], limit=1)

        if not upi_method:
            _logger.warning('UPI payment method not found for HDFC provider')
            return False

        # Prevent duplicate transaction on webhook retries
        tx_sudo = env['payment.transaction'].sudo().search([
            ('reference', '=', order_no),
            ('provider_id', '=', provider.id),
        ], limit=1)

        if not tx_sudo:
            # Create transaction
            tx_vals = {
                'provider_id': provider.id,
                'payment_method_id': upi_method.id,
                'reference': order_no,
                'amount': invoice.amount_residual,
                'currency_id': invoice.currency_id.id,
                'partner_id': invoice.partner_id.id,
                'state': 'draft',
                'operation': 'online_direct',
                'invoice_ids': [Command.set(invoice.ids)],
            }
            tx_sudo = env['payment.transaction'].sudo().create(tx_vals)

        HDFCController._process_txn(tx_sudo=tx_sudo, hdfc_payload_parsed=hdfc_payload_parsed)

    @staticmethod
    def _process_sale_order(hdfc_payload_parsed):
        """
        Locate and process the payment transaction related to an HDFC webhook payload.

        This method searches for the corresponding 'payment.transaction' record
        using the reference contained in the parsed HDFC webhook payload and
        delegates the actual processing to '_process_txn'.

        :param dict hdfc_payload_parsed: The decrypted and parsed webhook payload
            received from HDFC.
        :return: None
        """
        # Find the corresponding payment transaction
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('hdfc', hdfc_payload_parsed)

        # Process Transaction
        HDFCController._process_txn(tx_sudo=tx_sudo, hdfc_payload_parsed=hdfc_payload_parsed)

    @staticmethod
    def _process_txn(tx_sudo, hdfc_payload_parsed):
        """
        Process an HDFC transaction based on the parsed webhook payload.

        This helper method validates the existence of the matching transaction,
        processes it using the HDFC payment provider logic, and triggers the
        post-processing flow if it has not already been executed.

        :param recordset tx_sudo: The sudoed 'payment.transaction' record to process.
        :param dict hdfc_payload_parsed: The decrypted and parsed webhook payload
            received from HDFC.
        :return: An empty JSON response when the transaction cannot be processed.
        :rtype: werkzeug.wrappers.Response
        """
        if not tx_sudo:
            _logger.warning('No matching HDFC transaction found for payload: %s', hdfc_payload_parsed.get('order_no'))
            return request.make_json_response('')

        # Process the verified transaction
        try:
            tx_sudo._process('hdfc', hdfc_payload_parsed)

            if not tx_sudo.is_post_processed:
                tx_sudo._post_process()

            _logger.info('HDFC transaction processed successfully (Ref: %s)', tx_sudo.reference)
        except Exception:
            _logger.exception('Failed to process HDFC transaction')
            return request.make_json_response('')
