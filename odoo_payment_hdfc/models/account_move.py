# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import uuid

from odoo import fields, models
from odoo.addons.odoo_payment_hdfc import const as hdfc_const
from odoo.tools.image import image_data_uri


class AccountMove(models.Model):
    _inherit = 'account.move'

    hdfc_txn_id = fields.Char(string="HDFC UPI Txn Unique ID")

    def _generate_qr_code(self, silent_errors=False):
        self.ensure_one()
        hdfc_provider = self.env['payment.provider'].sudo().search([
            ('is_published', '=', True),
            ('state', 'in', ['enabled', 'test']),
            ('code', '=', 'hdfc'),
            ('company_id', '=', self.company_id.id),
            ('show_qr_on_invoice', '=', True),
        ], limit=1)

        self.hdfc_txn_id = hdfc_const.HDFC_INV_REF_PREFIX + uuid.uuid4().hex[:16]

        if hdfc_provider and self.state == 'posted':
            ver = '01'
            mode = '03' if hdfc_provider.state == 'test' else '15'
            tr = self.hdfc_txn_id
            tn = ''
            pn = hdfc_provider.hdfc_merchant_name
            pa = hdfc_provider.hdfc_merchant_vpa
            mc = '6012'
            am = str(self.amount_residual)
            cu = 'INR'
            qr_string = (
                "upi://pay?"
                f"ver={ver}&"
                f"mode={mode}&"
                f"tr={tr}&"
                f"tn={tn}&"
                f"pn={pn}&"
                f"pa={pa}&"
                f"mc={mc}&"
                f"am={am}&"
                f"cu={cu}&"
                "qrMedium=06"
            )

            barcode = self.env['ir.actions.report'].barcode(barcode_type='QR', value=qr_string, width=120, height=120, quiet=False)
            return image_data_uri(base64.b64encode(barcode))

        return super()._generate_qr_code(silent_errors)
