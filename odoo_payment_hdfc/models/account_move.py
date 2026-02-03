# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64

from odoo import models
from odoo.tools.image import image_data_uri


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _generate_qr_code(self, silent_errors=False):
        self.ensure_one()
        hdfc_provider = self.env['payment.provider'].sudo().search([
            ('is_published', '=', True),
            ('state', 'in', ['enabled', 'test']),
            ('code', '=', 'hdfc'),
            ('show_qr_on_invoice', '=', True),
        ], limit=1)
        if hdfc_provider and self.state == 'posted':
            ver = '01'
            mode = '03' if hdfc_provider.state == 'test' else '15'
            tr = self.payment_reference + '_1'
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
