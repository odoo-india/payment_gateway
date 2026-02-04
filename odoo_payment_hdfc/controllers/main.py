import pprint

from odoo.addons.odoo_payment_hdfc import const as hdfc_const
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
        _logger.info('Notification received from HDFC with payload:\n%s', pprint.pformat(payload))

        merchant_response = request.httprequest.form.get('meRes')
        if not merchant_response:
            _logger.warning('meRes not found:\n%s', pprint.pformat(payload))
            return 'NO meRes', 400

        merchant_id = request.httprequest.form.get('pgMerchantId')
        if not merchant_id:
            _logger.warning('pgMerchantId not found:\n%s', pprint.pformat(payload))
            return 'NO pgMerchantId', 400

        merchant_info = HDFCController._extract_merchant_info(merchant_id)
        if not merchant_info:
            _logger.warning('No Merchant found with the given credentials: %s', merchant_id)
            return request.make_json_response('')

        try:
            hdfc_payload = hdfc_utils.decrypt_response(merchant_response, merchant_info.hdfc_merchant_key)
        except ValueError:
            _logger.warning('Decryption failed, Invalid Response')
            return request.make_json_response('')
        try:
            hdfc_payload_parsed = HDFCController.parse_callback_response(hdfc_payload)
        except ValueError:
            _logger.warning('Parsing failed, Invalid Response')
            return request.make_json_response('')

        event_type = 'payment' if 'txn_meta' in hdfc_payload_parsed and hdfc_payload_parsed.get('txn_meta')[0] == 'PAY' else 'refund'

        if not event_type:
            _logger.warning('Missing event type in HDFC payload.')
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
    def _extract_merchant_info(merchant_id):
        if not merchant_id:
            return {}
        return request.env['payment.provider'].sudo()._get_hdfc_payment_provider(merchant_id=merchant_id)

    @staticmethod
    def parse_callback_response(decrypted_text: str) -> dict:
        parts = decrypted_text.split('|')
        # 6409196|S00003-15|500.00|2025:12:17 04:39:27|SUCCESS|Transaction success|00|NA|sumit039@hdfcbank|535101448062|NA|null|null|null|null|null|Mybene!857679479890124!AABE0876543!NA|PAY!https://upitest.hdfcbank.com!NA!HDFC400E09AC55DB44EE803B797122DE136!NA!|odooin@hdfcbank!NA!NA|NA|NA
        if len(parts) < 21:
            raise ValueError(f'Expected 21 fields, got {len(parts)}')

        return {
            'txn_id': parts[0],  # 6409196
            'order_no': parts[1],  # S00003-15
            'amount': parts[2],  # 500.00
            'txn_auth_date': parts[3],  # 2025:12:17 04:39:27
            'status': parts[4],  # SUCCESS
            'status_desc': parts[5],  # Transaction success
            'resp_code': parts[6],  # 00
            'approval_no': parts[7],  # NA
            'payer_vpa': parts[8],  # sumit039@hdfcbank
            'rrn': parts[9],  # 535101448062
            'ref_id': parts[10],  # NA
            # |null|null|null|null|null|
            'payer_bank': parts[16].split('!'),  # Mybene!857679479890124!AABE0876543!NA
            'txn_meta': parts[17].split('!'),  # PAY!https://upitest.hdfcbank.com!NA!HDFC400E09AC55DB44EE803B797122DE136!NA!
            'payee_vpa': parts[18].split('!')[0],  # odooin@hdfcbank!NA!NA
            'payer_acc_type': parts[19].split('!')[0],  # |NA
            'payer_name': parts[20].split('!')[0],  # |NA
        }

    @staticmethod
    def _extract_payment_flow(hdfc_payload_parsed):
        order_no = hdfc_payload_parsed.get('order_no')

        if order_no.startswith(hdfc_const.HDFC_INV_REF_PREFIX):
            return 1
        else:
            return 0

    @staticmethod
    def _process_invoice(hdfc_payload_parsed):
        env = request.env

        # Get invoice
        invoice = env['account.move'].sudo().search([
            ('hdfc_txn_id', '=', hdfc_payload_parsed.get('order_no'))
        ], limit=1)

        if not invoice:
            _logger.warning('Invoice not found for order_no: %s', hdfc_payload_parsed.get('order_no'))
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

        # Create transaction
        tx_vals = {
            'provider_id': provider.id,
            'payment_method_id': upi_method.id,
            'reference': hdfc_payload_parsed.get('order_no'),
            'amount': invoice.amount_residual,
            'currency_id': invoice.currency_id.id,
            'partner_id': invoice.partner_id.id,
            'state': 'draft',
            'invoice_ids': [Command.set(invoice.ids)],
        }

        tx = env['payment.transaction'].sudo().create(tx_vals)

        # Process transaction
        try:
            tx._process('hdfc', hdfc_payload_parsed)

            # Manually need to mark the post_process to done
            if not tx.is_post_processed:
                tx._post_process()

            _logger.info(
                'HDFC transaction processed successfully (Ref: %s)',
                tx.reference
            )
            return tx

        except Exception:
            _logger.exception(
                'Failed to process HDFC transaction (Ref: %s)',
                tx.reference
            )
            return False

    @staticmethod
    def _process_sale_order(hdfc_payload_parsed):
        # Find the corresponding payment transaction
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('hdfc', hdfc_payload_parsed)
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
