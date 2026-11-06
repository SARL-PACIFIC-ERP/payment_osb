/** @odoo-module */

/**
 * Copyright © Lyra Network.
 * This file is part of OSB plugin for Odoo. See COPYING.md for license details.
 *
 * @author    Lyra Network (https://www.lyra.com/)
 * @copyright Copyright © Lyra Network
 * @license   http://www.gnu.org/licenses/agpl.html GNU Affero General Public License (AGPL v3)
 */

let popin = false;

export function osbCheckAmount() {
    // Only the eCommerce payment step displays the amount summary.
    var amount_total_summary = document.querySelector('#amount_total_summary');
    if (amount_total_summary === null) {
        return;
    }

    var observer = new MutationObserver( function(mutations) {
        mutations.forEach((mutation) => {
            const checkedRadio = document.querySelectorAll("[data-payment-method-code='osb']")[0];
            if (checkedRadio && checkedRadio.checked) {
                console.log("Amount total sumary has changed. We may have to re-create form token.");
                checkedRadio.click();
            }
        });
    });

    // Configure and start observing the target element for changes in child nodes.
    var config = { characterData: true, childList: true, subtree: true };

    observer.observe(amount_total_summary, config);
}

export function osbHidePreMessage() {
    // The help message of the provider announces the redirection to the payment page: hide it
    // when the embedded fields are displayed below the payment option instead.
    const wrapper = document.getElementById('osb-embedded-wrapper');
    const paymentOption = document.querySelector('input[data-provider-code="osb"]');
    const option = paymentOption?.closest('[for="o_payment_radio"]');
    if (!wrapper || !option) {
        return;
    }

    const helpMessage = option.querySelector(':scope > div.small');
    if (helpMessage && option.nextElementSibling?.contains(wrapper)) {
        helpMessage.textContent = '';
    }
}

export async function osbPrepareInlineForm(inlineValues) {
    var deliveryCarrier = document.querySelector('#delivery_carrier');
    if (deliveryCarrier !== null) {
        localStorage.removeItem('osbFormToken');
        localStorage.removeItem('osbFormTokenData');
    }

    // If there is already a stored token, check if payment data has changed.
    var formToken = getOsbItem('osbFormToken');
    var tokenData = getOsbItem('osbFormTokenData');
    if ((formToken !== null) && (tokenData == JSON.stringify(inlineValues))) {
        console.log('Payment details did not change on method display. Use the existing token.');
        return await osbDisplayEmbeddedForm(formToken, inlineValues);
    }

    formToken = await osbCreateFormToken(inlineValues);
    // If form token was not created, fallback to redirection mode.
    if (!formToken) {
        return false;
    }

    setOsbItem('osbFormToken', formToken, 15*60*1000);
    setOsbItem('osbFormTokenData', JSON.stringify(inlineValues), 15*60*1000);

    return await osbDisplayEmbeddedForm(formToken, inlineValues);
}

/**
 * Ask the server for a form token and return it, or false when none was created. A network
 * error or an unexpected answer is reported in the console rather than thrown: the caller then
 * falls back to the redirect flow.
 */
async function osbCreateFormToken(values) {
    try {
        const response = await fetch('/payment/osb/createFormToken', {
            method: "POST",
            headers: {
                "Content-Type":"application/json",
            },
            body: JSON.stringify(values),
        });
        const data = await response.json();

        return data["formToken"] || false;
    } catch (error) {
        console.error('Error while creating form token.', error);

        return false;
    }
}

async function osbDisplayEmbeddedForm(formToken, inlineValues) {
    const wrapper = document.getElementById("osb-embedded-wrapper");
    if (wrapper === null) {
        return false;
    }

    // Create a div for embedded form.
    let embeddedDiv = document.createElement("div");
    embeddedDiv.setAttribute("class", "kr-smart-form");

    const isPopin = inlineValues["pop_in"] === "1";
    if (isPopin) {
        embeddedDiv.setAttribute("kr-popin", "");
        wrapper.appendChild(embeddedDiv);
    } else {
        embeddedDiv.setAttribute("kr-single-payment-button", "");
    }

    if (inlineValues["entry_mode"] === "embedded_extended_with_logos" || inlineValues["entry_mode"] === "embedded_extended_without_logos") {
        embeddedDiv.setAttribute("kr-card-form-expanded", "");
        if (inlineValues["entry_mode"] === "embedded_extended_without_logos") {
            embeddedDiv.setAttribute("kr-no-card-logo-header", "");
        }
    }

    wrapper.appendChild(embeddedDiv);

    var __vadsFormConfig = { formToken: formToken };
    if (inlineValues["compact"] === "1") {
        __vadsFormConfig['cardForm'] = { layout: 'compact' };
        __vadsFormConfig['smartForm']= { layout: 'compact'};
    }

    // The gateway client rejects an expired or inconsistent form token: remove the embedded fields
    // and let the caller fall back to the redirect flow.
    if (!(await osbSetFormConfig(__vadsFormConfig))) {
        embeddedDiv.remove();
        return false;
    }

    popin = isPopin;

    return true;
}

async function osbSetFormConfig(formConfig) {
    try {
        await KR.setFormConfig(formConfig);

        return true;
    } catch (error) {
        console.log('The gateway client rejected the form token.', error);

        return false;
    }
}

/**
 * Open the embedded payment fields with a valid form token and return true, or return false when
 * there is none (stored token expired, refused request, gateway error) so that the caller falls
 * back to the gateway payment page.
 */
export async function osbProcessDirectFlow(inlineValues, processingValues) {
    var formToken = getOsbItem('osbFormToken');

    if (getOsbItem('osbFormTokenData') == JSON.stringify(inlineValues)) {
        console.log('Payment details did not change on payment submit. Use the existing token.');
    } else {
        const newFormToken = await osbCreateFormToken(processingValues);
        if (!newFormToken) {
            console.log('Error while creating form token.');
        } else if (newFormToken == 'NO_UPDATE') {
            console.log('Payment details did not change on payment submit. Use the existing token.');
        } else {
            formToken = newFormToken;
        }
    }

    if (!formToken || !(await osbSetFormConfig({ formToken: formToken }))) {
        return false;
    }

    osbSubmitPayment();

    return true;
}

export function osbSubmitPayment() {
    if (popin) {
        KR.openPopin();
    } else {
        KR.openSelectedPaymentMethod();
    }
}

function setOsbItem(key, value, ttl) {
    let item = {
        value: value,
        expiry: ttl ? Date.now() + ttl : null
    };

    localStorage.setItem(key, JSON.stringify(item));
}

function getOsbItem(key) {
    let item = localStorage.getItem(key);

    // if the item doesn't exist, return null
    if (!item) {
        return null;
    }

    try {
        item = JSON.parse(item);
    } catch (e) {
        return null;
    }

    // Compare the expiry time of the item with the current time.
    if (item.expiry && Date.now() > item.expiry) {
        // If the item is expired, delete the item from storage and return null
        localStorage.removeItem(key);
        return null;
    }

    return item.value;
}