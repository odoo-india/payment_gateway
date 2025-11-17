# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models

from odoo.addons.odoo_payment_easebuzz import const as easebuzz_const


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    def _easebuzz_get_minimum_amount_warning(self, amount, provider_code):
        if provider_code != 'easebuzz' or self.code != 'emi_india' or amount >= easebuzz_const.EASEBUZZ_EMI_MIN_AMOUNT:
            return ""
        return f"You cannot pay amount lesser than {easebuzz_const.EASEBUZZ_EMI_MIN_AMOUNT} with this payment method"
