# coding: utf-8
#
# Copyright © Osb Network.
# This file is part of Osb Collect plugin for Odoo. See COPYING.md for license details.
#
# Author:    Osb Network (https://www.osb.com)
# Copyright: Copyright © Osb Network
# License:   http://www.gnu.org/licenses/agpl.html GNU Affero General Public License (AGPL v3)

import logging
import base64
import requests
import json

from odoo.tools import float_round
from odoo import http
from odoo.http import request

from ..helpers import tools, constants
_logger = logging.getLogger(__name__)

class OsbRestController(http.Controller):
    @http.route("/payment/osb/createFormToken", type="http", auth='public', methods=['POST'], csrf=False)
    def osb_refresh_form_token(self, **post):
        # Input checks ported from the upstream Lyra plugin v4.3.4. In addition, the request must
        # carry the access token rendered to the owner of the payment form (order) or returned with
        # the processing values of the transaction (submit): without it, anyone could have a form
        # token created for the order of another customer and send that customer's data to the gateway.
        # On submit, the amount, currency and order sent to the gateway are those of the transaction.
        no_form_token = json.dumps({ "formToken": False })
        try:
            processing_values = json.loads(request.httprequest.data.decode('utf-8'))
        except ValueError:
            _logger.info('Osb Collect: invalid payload on createFormToken endpoint.')
            return no_form_token

        if not isinstance(processing_values, dict):
            return no_form_token

        provider_id = processing_values.get("provider_id")
        currency_id = processing_values.get("currency_id")
        if not self._osb_is_record_id(provider_id) or not self._osb_is_record_id(currency_id):
            return no_form_token

        payment_provider = request.env['payment.provider'].sudo().browse(provider_id).exists()
        if not payment_provider or payment_provider.code not in ['osb', 'osbmulti']:
            return no_form_token

        # Form tokens only serve the embedded payment fields.
        if payment_provider.osb_payment_data_entry_mode == 'redirect':
            return no_form_token

        access_token = processing_values.get("osb_access_token")

        # On payment method selection, we have only order ID.
        if "order_id" in processing_values:
            order_id = processing_values["order_id"]
            partner_id = processing_values.get("partner_id")
            if not payment_provider._osb_check_form_token_access(access_token, 'order', order_id, partner_id, currency_id):
                _logger.info('Osb Collect: createFormToken refused, invalid access token for the order.')
                return no_form_token

            if not str(order_id).isdigit():
                return no_form_token

            processed_values = payment_provider.osb_generate_values_from_order(processing_values)
            if not processed_values:
                return no_form_token
        else:
            # On payment submit, we have transaction data.
            reference = processing_values.get("reference")
            if not reference or not isinstance(reference, str):
                return no_form_token

            payment_transaction = request.env['payment.transaction'].sudo().search([('reference', '=', reference), ('provider_id', '=', payment_provider.id)], limit=1)
            if not payment_transaction or not payment_provider._osb_check_form_token_access(access_token, 'tx', payment_transaction.id):
                _logger.info('Osb Collect: createFormToken refused, invalid access token for the transaction.')
                return no_form_token

            # The REST notification finds the transaction through its sales order.
            if not payment_transaction.sale_order_ids:
                return no_form_token

            sale_order = payment_transaction.sale_order_ids[0]
            sale_order._check_cart_is_ready_to_be_paid()

            # Check amount coherence.
            compare_amounts = sale_order.currency_id.compare_amounts
            if (compare_amounts(payment_transaction.amount, sale_order.amount_total)):
                return json.dumps({ "formToken": "NO_UPDATE" })

            currency_id = payment_transaction.currency_id.id
            processing_values = dict(processing_values, reference=payment_transaction.reference,
                                     amount=payment_transaction.amount, currency_id=currency_id)
            processing_values.pop('currency', None)
            processed_values = payment_transaction._get_specific_rendering_values(processing_values)
            if not processed_values:
                return no_form_token

            processed_values["vads_order_id"] = sale_order.name

        currency_data = payment_provider._osb_get_currency(currency_id)
        if not currency_data:
            return no_form_token

        currency = currency_data[0]

        params = self.generate_form_token_data(processed_values, payment_provider, currency)
        form_token = self.osb_create_form_token(params, payment_provider)
        return json.dumps({ "formToken": form_token })

    @staticmethod
    def _osb_is_record_id(value):
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    def generate_form_token_data(self, values, payment_provider, currency):
        params = {
            "amount": values["vads_amount"],
            "currency": currency,
            "orderId": values["vads_order_id"],
            "customer": {
                "email": values["vads_cust_email"],
                "reference": values["vads_cust_id"],
                "billingDetails": {
                    "firstName": values["vads_cust_first_name"],
                    "lastName": values["vads_cust_last_name"],
                    "address": values["vads_cust_address"],
                    "zipCode": values["vads_cust_zip"],
                    "state": values["vads_cust_state"],
                    "city": values["vads_cust_city"],
                    "phoneNumber": values["vads_cust_phone"],
                    "country": values["vads_cust_country"],
                    "language": values["vads_language"],
                }
            },
            "shipingDetails": {
                "firstName": values["vads_ship_to_first_name"],
                "lastName": values["vads_ship_to_last_name"],
                "address": values["vads_ship_to_street"],
                "zipCode": values["vads_ship_to_zip"],
                "city": values["vads_ship_to_city"],
                "state": values["vads_ship_to_state"],
                "phoneNumber": values["vads_ship_to_phone_num"],
                "country": values["vads_ship_to_country"],
            },
            "transactionOptions": {
                "cardOptions": {
                    "paymentSource": "EC"
                }
            },
            "contrib": values["vads_contrib"],
        }

        validation_mode = payment_provider.osb_validation_mode
        if validation_mode == "1":
            params["transactionOptions"]["cardOptions"]["manualValidation"] = "YES"
        elif validation_mode == "0":
            params["transactionOptions"]["cardOptions"]["manualValidation"] = "NO"

        capture_delay = payment_provider.osb_capture_delay
        if capture_delay and capture_delay.isdigit():
            params["transactionOptions"]["cardOptions"]["captureDelay"] = capture_delay

        retry = payment_provider.osb_embedded_payment_attempts
        if retry and retry.isdigit():
            params["transactionOptions"]["cardOptions"]["retry"] = retry

        cards = payment_provider._osb_get_embedded_payment_means()
        if cards != []:
            params['paymentMethods'] = tuple(cards)

        return params

    def osb_create_form_token(self, values, payment_provider):
        try:
            identification = payment_provider.osb_site_id + ":" + payment_provider._osb_get_rest_password()
            headers = {
                "Authorization": "Basic " + base64.b64encode((identification.encode('utf-8'))).decode('utf-8'),
                "Content-Type": "application/json"
            }

            request_url = constants.OSB_PARAMS.get('REST_URL') + 'V4/Charge/CreatePayment'

            response = requests.post(url = request_url, json = values, headers = headers)
            if response.json().get("status") != "SUCCESS":
                _logger.error("Error while creating form token: " + response.json().get("answer", {}).get("errorMessage") + "(" + response.json().get("answer", {}).get("errorCode") + ").")
                if "detailedErrorMessage" in response.json().get("answer", {}) and response.json().get("answer", {}).get("detailedErrorMessage") is not None:
                    _logger.error("Detailed message: " + response.json().get("answer", {}).get("detailedErrorMessage") + "(" + response.json().get("answer", {}).get("detailedErrorCode") + ").")
            else:
                msg = ""
                if "orderId" in values:
                    msg = " for order #" + values['orderId']

                # The request data holds the customer's personal data: do not log it.
                _logger.info("Form token created successfully {}.".format(msg))

                return response.json().get("answer", {}).get("formToken")
        except Exception as exc:
            _logger.error(exc)

        return False