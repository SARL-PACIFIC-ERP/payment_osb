/** @odoo-module */

/**
 * Copyright © Lyra Network.
 * This file is part of OSB plugin for Odoo. See COPYING.md for license details.
 *
 * @author    Lyra Network (https://www.lyra.com/)
 * @copyright Copyright © Lyra Network
 * @license   http://www.gnu.org/licenses/agpl.html GNU Affero General Public License (AGPL v3)
 */

import { patch } from '@web/core/utils/patch';
import { PaymentForm } from '@payment/interactions/payment_form';

import { osbCheckAmount,
         osbHidePreMessage,
         osbPrepareInlineForm,
         osbProcessDirectFlow,
         osbSubmitPayment
} from '@payment_osb/js/payment_utils';

let can_process_payment = true;

patch(PaymentForm.prototype, {
    start() {
        super.start();

        // KR is defined by the script of the embedded fields, rendered only when the provider
        // uses them: nothing to do in redirect mode. The interaction starts once the page is
        // loaded, and jQuery is not part of the website assets anymore.
        if (typeof KR === 'undefined') {
            return;
        }

        // Update form token on amount update.
        osbCheckAmount();
    },

    _osbGetInlineValues() {
        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = radio && this._getInlineForm(radio);
        const osbInlineForm = inlineForm?.querySelector('[name="o_osb_element_container"]');
        if (!osbInlineForm) {
            return null;
        }

        return JSON.parse(osbInlineForm.dataset['osbInlineFormValues']);
    },

    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if ((typeof (KR) == "undefined") || (paymentMethodCode != "osb")) {
            await super._prepareInlineForm(...arguments);
            return;
        }

        const inlineValues = this._osbGetInlineValues();
        if (!inlineValues) {
            await super._prepareInlineForm(...arguments);
            return;
        }

        this._disableButton(false);

        // Set the flow to direct to avoid redirection to payment page on Odoo payment button clic,
        // but only once the embedded fields are displayed: without a form token (refused request,
        // gateway error), the customer pays on the hosted page through the default redirect flow.
        // The help message announcing that redirection is hidden only in the first case.
        if (await osbPrepareInlineForm(inlineValues)) {
            this._setPaymentFlow('direct');
            osbHidePreMessage();
        }
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'osb') {
            await super._processDirectFlow(...arguments);
            return;
        }

        if (! can_process_payment) {
            return;
        }

        var inlineValues = this._osbGetInlineValues();
        if (!(await osbProcessDirectFlow(inlineValues, processingValues))) {
            // No usable form token (stored token expired, refused request, gateway error): pay on
            // the gateway payment page instead, through a new transaction in the redirect flow.
            this._setPaymentFlow('redirect');
            await this._initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, 'redirect');
            return;
        }

        this._enableButton();
        can_process_payment = false;
    },

    async _initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode == "osb" && ! can_process_payment) {
            osbSubmitPayment();
            this._enableButton();
            can_process_payment = false;

            return;
        }

        await super._initiatePaymentFlow(...arguments);
    }
});