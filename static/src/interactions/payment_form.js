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
    setup() {
        super.setup();

        // Update form token on amount update.
        $(document).ready(function() {
            if (typeof (KR) == 'undefined') {
                return;
            }

            osbCheckAmount();
            osbHidePreMessage();
        });
    },

    _osbGetInlineValues() {
        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        const osbInlineForm = inlineForm.querySelector('[name="o_osb_element_container"]');

        return JSON.parse(
            osbInlineForm.dataset['osbInlineFormValues']
        );
    },

    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if ((typeof (KR) == "undefined") || (paymentMethodCode != "osb")) {
            await super._prepareInlineForm(...arguments);
            return;
        }

        const inlineValues = this._osbGetInlineValues();
        if (inlineValues.length == 0) {
            return;
        }

        // Set the flow to direct to avoid redirection to payment page on Odoo payment button clic.
        this._setPaymentFlow('direct');
        this._disableButton(false);

        await osbPrepareInlineForm(inlineValues);
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
        await osbProcessDirectFlow(inlineValues, processingValues);

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