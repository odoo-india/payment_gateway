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
        if (providerCode !== "billdesk") {
            await super._prepareInlineForm(...arguments);
            return;
        }

        // Overwrite the flow of the select payment method.
        this._setPaymentFlow("direct");
    },

    // #=== PAYMENT FLOW ===#

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== "billdesk") {
            await super._processDirectFlow(...arguments);
            return;
        }
        const { txn_env } = processingValues;
        const billdeskOptions = this._prepareBilldeskOptions(processingValues);
        const testingSdk =
            "https://uat1.billdesk.com/merchant-uat/websdk/shared/billdesksdk.esm.js";
        const productionSdk = "https://pay.billdesk.com/websdk/shared/billdesksdk.esm.js";
        await loadJS(txn_env == "test" ? testingSdk : productionSdk);
        window.loadBillDeskSdk(billdeskOptions);
    },

    /**
     * Prepare the options to init the Billdesk Ace SDK Object.
     *
     * @param {object} processingValues - Processing values
     * @return {object}
     */
    _prepareBilldeskOptions(processingValues) {
        const {
            merchant_id: merchantId,
            bd_order_id: bdOrderId,
            auth_token: authToken,
            return_url: returnUrl,
            payment_categories,
        } = processingValues;
        const flowConfig = {
            merchantId,
            bdOrderId,
            authToken,
            childWindow: false,
            returnUrl,
            prefs: {
                payment_categories,
            },
        };
        return {
            flowType: "payments",
            flowConfig,
        };
    },
});
