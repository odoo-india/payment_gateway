# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models

from odoo.addons.odoo_payment_easebuzz import const as easebuzz_const


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    def _easebuzz_get_minimum_amount_warning(self, amount, currency_id, provider_code):
        amount_inr = self.env['payment.provider']._easebuzz_convert_amount_to_inr(amount, currency_id)
        if provider_code != 'easebuzz' or self.code != 'emi_india' or amount_inr >= easebuzz_const.EASEBUZZ_EMI_MIN_AMOUNT:
            return ""
        inr_currency = self.env['res.currency'].with_context(active_test=False).search([
            ('name', '=', 'INR'),
        ], limit=1)
        min_amount = inr_currency._convert(easebuzz_const.EASEBUZZ_EMI_MIN_AMOUNT, currency_id)
        return f"You cannot pay amount lesser than {currency_id.symbol} {min_amount} with this payment method"
