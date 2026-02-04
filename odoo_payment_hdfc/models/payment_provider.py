# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.addons.odoo_payment_hdfc import const as hdfc_const
from odoo.addons.odoo_payment_hdfc import utils as hdfc_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.exceptions import ValidationError

_logger = get_payment_logger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('hdfc', 'HDFC')], ondelete={'hdfc': 'set default'}
    )
    hdfc_merchant_id = fields.Char(
        string='HDFC Merchant ID',
        help='The ID solely used to identify the account with HDFC.',
        required_if_provider='hdfc',
        copy=False,
    )
    hdfc_merchant_name = fields.Char(
        string='HDFC Merchant Name',
        help='The Merchant Name registered with HDFC.',
        required_if_provider='hdfc',
        copy=False,
    )
    hdfc_merchant_key = fields.Char(
        string='HDFC Merchant Key',
        help='The Key used for encryption and decryption.',
        required_if_provider='hdfc',
        copy=False,
    )
    hdfc_merchant_vpa = fields.Char(
        string='HDFC Merchant VPA',
        help='The VPA registered with HDFC.',
        required_if_provider='hdfc',
        copy=False,
    )

    show_qr_on_invoice = fields.Boolean(
        string='Show QR on Invoice',
        default=False,
        help='Enable to display the QR code on printed invoices.'
    )

    # === COMPUTE METHODS === #

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'hdfc':
            supported_currencies = supported_currencies.filtered(lambda c: c.name in hdfc_const.SUPPORTED_CURRENCIES)
        return supported_currencies

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'hdfc').update({
            'support_refund': 'partial',
        })

    # === CRUD METHODS ===#

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        self.ensure_one()
        if self.code != 'hdfc':
            return super()._get_default_payment_method_codes()
        return hdfc_const.DEFAULT_PAYMENT_METHOD_CODES

    def _get_hdfc_payment_provider(self, merchant_id=None, company_id=None):
        domain = [
            ('code', '=', 'hdfc'),
            ('state', 'in', ['enabled', 'test']),
            ('is_published', '=', True),
        ]

        if company_id:
            domain.append(('company_id', '=', company_id))

        if merchant_id:
            domain.append(('hdfc_merchant_id', '=', merchant_id))

        return self.env['payment.provider'].sudo().search(domain, limit=1)

    # === REQUEST HELPERS === #

    def _build_request_url(self, endpoint, **kwargs):
        """ Override of `payment` to build the request URl. """
        if self.code != 'hdfc':
            return super()._build_request_url(endpoint, **kwargs)

        url_host = hdfc_const.TEST_BASE_URL if self.state == 'test' else hdfc_const.PROD_BASE_URL

        return f'https://{url_host}{endpoint}'

    def _build_request_headers(self, *args, **kwargs):
        """ Override of `payment` to build the request headers. """
        if self.code != 'hdfc':
            return super()._build_request_headers(*args, **kwargs)

        return {'Content-Type': 'application/json'}

    def _parse_response_content(self, response, **kwargs):
        """Parse and validate HDFC refund response.
        Ex:
        '10999613|R-S00014-2-1|1.00|2026:01:30 04:19:40|SUCCESS|Transaction Success|00|NA|odooin@hdfcbank|100000746688|NA|NA|NA|NA|NA|NA|NA|NA|NA|NA|NA'
        'NA|R-S00014-2-2|1|2026:01:30 04:21:50|MC04|Refund Already Processed|V116|NA|NA|NA|NA|NA|NA|NA|NA|NA|NA|NA|NA|NA|NA'
        """

        if self.code != 'hdfc':
            return super()._parse_response_content(response, **kwargs)

        raw_response = response.text.strip()
        try:
            response_content = hdfc_utils.decrypt_response(
                raw_response,
                self.hdfc_merchant_key
            )
        except ValueError:
            response_content = raw_response

        parts = response_content.split('|')

        if len(parts) < 7:
            raise ValidationError(
                _('Invalid or malformed response received from HDFC:\n%s')
                % response_content
            )

        status_message = parts[5].strip()
        status_code = parts[4].strip()

        # Handle failure casess
        if status_code.upper() != 'SUCCESS':
            raise ValidationError(status_message)
        refund_data = {
            'txn_id': parts[0].strip(),
            'order_no': parts[1].strip(),
            'amount': parts[2].strip(),
            'txn_auth_date': parts[3].strip(),
            'status': status_code,
            'status_desc': status_message,
            'resp_code': parts[6].strip(),
            'approval_no': parts[7].strip(),
            'payer_vpa': parts[8].strip(),
            'rrn': parts[9].strip(),
            'ref_id': parts[10].strip(),
            'payer_bank': [
                parts[10].strip(),
                parts[10].strip(),
                parts[10].strip(),
                parts[10].strip()
            ],
            'txn_meta': [
                'REFUND'
            ]
        }
        # Success response
        return refund_data

    def _parse_response_error(self, response):
        if self.code != 'HDFC':
            return super()._parse_response_error(response)
        try:
            response_msg = response.text
        except ValueError:
            raise ValidationError(_('Error occurred while parsing message from HDFC.'))
        return response_msg
