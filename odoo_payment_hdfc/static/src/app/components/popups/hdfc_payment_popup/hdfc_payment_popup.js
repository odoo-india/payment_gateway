/** @odoo-module **/

import { Component, onWillUnmount, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ConnectionLostError, rpc, RPCError } from "@web/core/network/rpc";

export class HDFCPaymentPopup extends Component {
    static template = "odoo_payment_hdfc.HDFCPaymentPopop";
    static components = { Dialog };

    static props = {
        qrCode: String,
        formattedAmount: String,
        orderRef: String,
        txnEnv: String,
        close: Function,
    };

    setup() {
        this.dialogService = useService("dialog");

        this.pollAttempt = 0;
        this.pollDelay = 0;
        this.pollTimeoutId = null;
        this.isConfirmationDialogOpen = false;

        this.startPolling();

        onMounted(() => {
            this.handleKeyDown = (e) => {
                if (e.key === "Escape" || e.keyCode === 27) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();

                    if (!this.isConfirmationDialogOpen) {
                        this.confirmClosePopup();
                    }
                }
            };
            document.addEventListener("keydown", this.handleKeyDown, true);
        });

        onWillUnmount(() => this.stopPolling());
    }

    confirmClosePopup() {
        this.isConfirmationDialogOpen = true;

        this.dialogService.add(ConfirmationDialog, {
            title: "Cancel transaction",
            body: "Are you sure you want to exit?",
            confirm: () => {
                this.isConfirmationDialogOpen = false;
                this.props.close();
            },
            cancel: () => {
                this.isConfirmationDialogOpen = false;
            },
            close: () => {
                this.isConfirmationDialogOpen = false;
            },
        });
    }

    startPolling() {
        this.updatePollDelay();
        this.pollTimeoutId = setTimeout(async () => {
            try {
                // Fetch the post-processing values from the server.
                const postProcessingValues = await rpc("/payment/status/poll", {
                    csrf_token: odoo.csrf_token,
                });

                // Redirect the user to the landing route if the transaction reached a final state.
                const { provider_code, state, landing_route } = postProcessingValues;
                if (HDFCPaymentPopup.getFinalStates(provider_code).has(state)) {
                    window.location = landing_route;
                } else {
                    this.startPolling();
                }
            } catch (error) {
                const isRetryError = error instanceof RPCError && error.data.message === "retry";
                const isConnectionLostError = error instanceof ConnectionLostError;
                if (isRetryError || isConnectionLostError) {
                    this.startPolling();
                }
                if (!isRetryError) {
                    throw error;
                }
            }
        }, this.pollDelay);
    }

    stopPolling() {
        if (this.pollTimeoutId) {
            clearTimeout(this.pollTimeoutId);
            this.pollTimeoutId = null;
        }
    }

    static getFinalStates(providerCode) {
        return new Set(["authorized", "done", "cancel", "error"]);
    }

    updatePollDelay() {
        if (this.pollAttempt < 10) {
            this.pollDelay = 3000;
        } else if (this.pollAttempt < 20) {
            this.pollDelay = 10000;
        } else {
            this.pollDelay = 30000;
        }

        this.pollAttempt++;
    }
}
