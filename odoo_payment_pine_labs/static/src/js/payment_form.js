/* global Pinelabs */

import { loadJS } from '@web/core/assets';
import { PaymentForm } from '@payment/interactions/payment_form';
import { patch } from '@web/core/utils/patch';

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
        if (providerCode !== 'pine_labs') {
            await super._prepareInlineForm(...arguments);
            return;
        }

        if (flow === 'token') {
            return; // No need to update the flow for tokens.
        }

        // Overwrite the flow of the select payment method.
        this._setPaymentFlow('direct');
    },

    // #=== PAYMENT FLOW ===#

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'pine_labs') {
            await super._processDirectFlow(...arguments);
            return;
        }
        await loadJS(processingValues.load_url);
        function handleCheckout(redirectUrl) {
          const options = {
            redirectUrl,
            successHandler: async function (response) {
                console.log(response);
                window.location = '/payment/status';
            },
            failedHandler: async function (response) {
                console.log(response);
                window.location = '/payment/status';
            },
          };
          const plural = new Plural(options);
          plural.open(options);
        }
        handleCheckout(processingValues.pine_labs_token_url);
    },

});
