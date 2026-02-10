# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import uuid

from odoo import fields, models
from odoo.addons.odoo_payment_hdfc import const as hdfc_consts
from odoo.addons.odoo_payment_hdfc import utils as hdfc_utils
from odoo.tools.image import image_data_uri


class AccountMove(models.Model):
    _inherit = 'account.move'

    hdfc_txn_id = fields.Char(
        string='HDFC UPI Txn Unique ID',
        readonly=True,
        index=True,
        copy=False
    )

    def _generate_qr_code(self, silent_errors=False):
        """
        Generate and return a QR code for the invoice, using the HDFC payment provider when applicable.

        This method overrides the base QR generation logic to support HDFC UPI dynamic QR codes
        on customer invoices. When the invoice is posted and an HDFC payment provider is configured
        for the current company with "Show QR on Invoice" enabled, a unique HDFC transaction
        reference is generated and used to build the QR payload. The resulting QR code is then
        rendered as a base64-encoded image data URI for display on the invoice PDF.

        :param bool silent_errors: Whether errors should be silenced during QR code generation.
                                This parameter is forwarded to the parent implementation when
                                falling back.
        :return: A base64-encoded image data URI of the generated QR code, or the result of the
                parent implementation.
        :rtype: str or None
        """
        self.ensure_one()
        hdfc_provider = self.env['payment.provider'].sudo()._get_hdfc_payment_provider(
            company_id=self.company_id.id,
            show_qr_on_invoice=True
        )

        if hdfc_provider and self.state == 'posted' and self.move_type == 'out_invoice':
            self.hdfc_txn_id = hdfc_consts.HDFC_INV_REF_PREFIX + uuid.uuid4().hex[:16]
            qr_string = hdfc_utils.generate_qr_code(
                hdfc_provider,
                txn_ref=self.hdfc_txn_id,
                txn_note='',
                amount=self.amount_residual
            )

            barcode = self.env['ir.actions.report'].barcode(barcode_type='QR', value=qr_string, width=120, height=120, quiet=False)
            return image_data_uri(base64.b64encode(barcode))

        return super()._generate_qr_code(silent_errors)
