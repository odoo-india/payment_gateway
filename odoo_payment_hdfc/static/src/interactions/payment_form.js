/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentForm } from "@payment/interactions/payment_form";
import { HDFCPaymentPopup } from "../app/components/popups/hdfc_payment_popup/hdfc_payment_popup";
import { formatCurrency } from "@web/core/currency";

patch(PaymentForm.prototype, {
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, methodCode, flow) {
        if (providerCode !== "hdfc") {
            return super._prepareInlineForm(...arguments);
        }

        // Force direct flow for HDFC
        this._setPaymentFlow("direct");
    },

    _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== "hdfc") {
            return super._processDirectFlow(...arguments);
        }

        const payload = processingValues.payload;
        if (!payload?.qr_image) {
            this.displayNotification({
                title: "QR Code Error",
                message: "QR missing from HDFC response",
                type: "danger",
            });
            return;
        }
        this._showHdfcQrDialog(processingValues);
    },

    _showHdfcQrDialog(processingValues) {
        const popupProps = {
            qrCode: processingValues?.payload?.qr_image,
            formattedAmount: formatCurrency(processingValues.amount, processingValues.currency_id),
            orderRef: processingValues.reference,
            txnEnv: processingValues.txn_env,
            close: () => {
                this.services.dialog.closeAll();
            },
        };

        this.services.dialog.add(HDFCPaymentPopup, popupProps, {
            onClose: () => {
                this._enableButton();
            },
        });
    },
});
