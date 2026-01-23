import { loadJS } from "@web/core/assets";
import { patch } from "@web/core/utils/patch";

import { PaymentForm } from "@payment/interactions/payment_form";

patch(PaymentForm.prototype, {
    // #=== DOM MANIPULATION ===#

    /**
     * Update the payment context to set the flow to 'direct'.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option.
     * @return {void}
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== "paytm") {
          await super._prepareInlineForm(...arguments);
          return;
        }

        // Overwrite the flow of the select payment method.
        this._setPaymentFlow("direct");
    },

    // #=== PAYMENT FLOW ===#

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== "paytm") {
          await super._processDirectFlow(...arguments);
          return;
        }

        const { merchant_id, orderId, amount, tokenType, token, tx_env } = processingValues;

        const stagingUrl = "https://securestage.paytmpayments.com";
        const liveUrl = "https://secure.paytmpayments.com";
        const paytmUrl = tx_env === 'TEST' ? stagingUrl : liveUrl;

        await loadJS(`${paytmUrl}/merchantpgpui/checkoutjs/merchants/${merchant_id}.js`);

        const config = {
            "root": "",
            "flow": "DEFAULT",
            "data": {
                "orderId": orderId,
                "token": token,
                "tokenType": tokenType,
                "amount": amount
            },
            "handler": {
                "notifyMerchant": (eventName) => {
                    if (eventName === "APP_CLOSED") {
                        window.location.reload();
                    }
                }
            }
        };

        if (window.Paytm && window.Paytm.CheckoutJS) {
            window.Paytm.CheckoutJS.onLoad(() => {
                window.Paytm.CheckoutJS.init(config).then(() => {
                    window.Paytm.CheckoutJS.invoke();
                }).catch((error) => {
                    console.error("Paytm CheckoutJS initialization error => ", error);
                });
            });
        } else {
            console.error("Paytm CheckoutJS not loaded");
        }
    },
});
