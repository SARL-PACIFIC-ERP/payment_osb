# coding: utf-8
#
# Copyright © Lyra Network.
# This file is part of OSB plugin for Odoo. See COPYING.md for license details.
#
# Author:    Lyra Network (https://www.lyra.com)
# Copyright: Copyright © Lyra Network
# License:   http://www.gnu.org/licenses/agpl.html GNU Affero General Public License (AGPL v3)

import logging
import pprint

from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
from ..helpers import tools

_logger = logging.getLogger(__name__)

class OsbController(http.Controller):
    _notify_url = '/payment/osb/ipn'
    _return_url = '/payment/osb/return'

    def _get_providers_from_rest_response(self, post_data, flow):
        """Return the Osb providers whose secret key signs the raw kr-answer (Lyra v4.3.4 fix).

        Called before kr-answer is parsed. Lyra signs the IPN with the REST password and the
        return to shop with the HMAC-SHA-256 key. Unlike upstream, all the matching providers
        are returned, so that two providers sharing the same keys do not reject each other.
        """
        providers = request.env['payment.provider'].sudo().search([('code', 'in', ['osb', 'osbmulti'])])

        def signs(provider):
            key = provider._osb_get_rest_password() if flow == 'ipn' else provider._osb_get_rest_sha256_key()
            return tools.check_hash(post_data, key)

        return providers.filtered(signs)

    def _verify_rest_response(self, post_data, flow):
        """Authenticate a REST response, then make sure kr-answer is a JSON object.

        :return: The providers whose key signs the response.
        :raise ValidationError: If the signature is missing or invalid, or kr-answer is not JSON.
        """
        providers_sudo = self._get_providers_from_rest_response(post_data, flow)
        if not providers_sudo:
            raise ValidationError('OSB: missing or invalid kr-hash signature, REST response rejected.')

        if tools.parse_rest_answer(post_data) is None:
            raise ValidationError('OSB: kr-answer is not a JSON object, REST response rejected.')

        return providers_sudo

    def _get_return_url(self, result, **pdt_data):
        return_url = pdt_data.pop('return_url', '')

        if not return_url:
            return_url = '/payment/process' if result else '/shop/cart'

        return return_url

    @http.route(
        _return_url, type='http', auth='public', methods=['POST', 'GET'], csrf=False,
        save_session=False
    )
    def osb_return_from_checkout(self, **pdt_data):
        # Check payment result and create transaction.
        _logger.debug('OSB: entering _from_notification with data %s', pprint.pformat(pdt_data))

        try:
            is_rest = False
            # is_rest is only set below, once the REST signature is verified: never read it from
            # the POST, or an unsigned form notification would skip the signature check.
            data = {key: value for key, value in pdt_data.items() if key != 'is_rest'}
            providers_sudo = request.env['payment.provider']

            # Check the type of integration.
            if tools.check_rest_response(pdt_data):
                # Verify the signature of the raw kr-answer before parsing it.
                providers_sudo = self._verify_rest_response(pdt_data, 'return')

                data = tools.convert_rest_result(pdt_data)
                data['is_rest'] = '1'
                is_rest = True

            tx_sudo = request.env['payment.transaction'].sudo()._get_tx_from_notification_data('osb', data)

            if is_rest and tx_sudo.provider_id not in providers_sudo:
                raise ValidationError('OSB: REST response signed for another provider, rejected.')

            # Handle the notification data.
            tx_sudo._handle_notification_data('osb', data)
        except ValidationError:
            _logger.exception("OSB: Unable to handle the return notification data; skipping to acknowledge.")

        return request.redirect('/payment/status')

    @http.route(_notify_url, type='http', auth='public', methods=['POST'], csrf=False,
        save_session=False
    )
    def osb_ipn(self, **post):
        # Check payment result and create transaction.
        _logger.debug('OSB: entering IPN _get_tx_from_notification with post data %s', pprint.pformat(post))

        try:
            is_rest = False
            # is_rest is only set below, once the REST signature is verified: never read it from
            # the POST, or an unsigned form notification would skip the signature check.
            data = {key: value for key, value in post.items() if key != 'is_rest'}
            providers_sudo = request.env['payment.provider']

            # Check the type of integration.
            if tools.check_rest_response(post):
                # Verify the signature of the raw kr-answer before parsing it.
                providers_sudo = self._verify_rest_response(post, 'ipn')

                if not tools.order_cycle_closed(post):
                    return 'Payment failure.'

                data = tools.convert_rest_result(post)
                data['is_rest'] = '1'
                is_rest = True

            result = request.env['payment.transaction'].sudo()._get_tx_from_notification_data('osb', data)

            if is_rest and result.provider_id not in providers_sudo:
                raise ValidationError('OSB: REST response signed for another provider, rejected.')

            if (data.get('vads_trans_status') == 'ABANDONED') or (data.get('vads_trans_status') == 'CANCELED') and (data.get('vads_order_status') == 'UNPAID') and (data.get('vads_order_cycle') == 'CLOSED'):
                return 'Payment abandoned.'

            # Handle the notification data.
            result._handle_notification_data('osb', data)
        except ValidationError: # Acknowledge the notification to avoid getting spammed.
            _logger.exception("OSB: Unable to handle the IPN notification data; skipping to acknowledge.")
            return 'Bad request received.'

        return 'Payment processed, order has been updated.' if result else 'An error occurred while processing payment.'