# Tests of /payment/osb/createFormToken (public route): a form token is only created for the
# owner of the payment form or of the transaction, and malformed payloads are refused cleanly.
# Needs website_sale (cart checks of the submit path).
import json
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon

REST_LOGGER = 'odoo.addons.payment_osb.controllers.rest'


class FakeResponse:
    def json(self):
        return {'status': 'SUCCESS', 'answer': {'formToken': 'TOKEN'}}


@tagged('post_install', '-at_install')
class TestOsbFormToken(PaymentHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls._prepare_provider('osb', update_values={'osb_payment_data_entry_mode': 'embedded'})
        cls.payment_method_id = cls.env.ref('payment_osb.payment_method_osb').id
        cls.currency = cls.currency_euro
        cls.amount = 100.0
        cls.partner = cls.default_partner
        cls.order = cls._create_order(cls.partner)
        cls.other_partner = cls.env['res.partner'].create({'name': 'Other customer', 'email': 'other@example.com'})
        cls.other_order = cls._create_order(cls.other_partner)

    @classmethod
    def _create_order(cls, partner):
        product = cls.env['product.product'].create({
            'name': 'OSB token product', 'list_price': 100.0, 'type': 'service', 'taxes_id': [(5, 0, 0)]})
        return cls.env['sale.order'].create({
            'partner_id': partner.id, 'currency_id': cls.currency.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 100.0})],
        })

    def _inline_values(self, order, partner):
        """The values rendered in the payment form of the order, as the browser posts them back."""
        with patch('odoo.addons.payment_osb.models.payment_provider.request', SimpleNamespace(env=self.env)):
            values = self.provider._osb_get_inline_form_values(
                order.amount_total, self.currency, partner.id, False, None, sale_order_id=order.id)
        return json.loads(values)

    def _create_form_token(self, payload):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        with patch('odoo.addons.payment_osb.controllers.rest.requests.post', return_value=FakeResponse()) as post_mock:
            response = self.url_open('/payment/osb/createFormToken', data=body,
                                     headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200, response.text[:500])
        return response.json(), post_mock

    # --- payment method selection (order) ----------------------------------------------------

    def test_order_own_order_accepted(self):
        payload = self._inline_values(self.order, self.partner)
        self.assertTrue(payload['osb_access_token'])
        result, post_mock = self._create_form_token(payload)
        self.assertEqual(result, {'formToken': 'TOKEN'})
        sent = post_mock.call_args.kwargs['json']
        self.assertEqual(sent['orderId'], self.order.name)

    @mute_logger(REST_LOGGER)
    def test_order_of_another_customer_refused(self):
        payload = self._inline_values(self.order, self.partner)
        for changes in (
            {'order_id': str(self.other_order.id)},
            {'order_id': str(self.other_order.id), 'partner_id': self.other_partner.id},
            {'osb_access_token': None},
            {'osb_access_token': 'forged'},
            {'osb_access_token': 'é' * 64},
        ):
            with self.subTest(changes=changes):
                result, post_mock = self._create_form_token(dict(payload, **changes))
                self.assertEqual(result, {'formToken': False})
                post_mock.assert_not_called()
        no_token = dict(payload)
        del no_token['osb_access_token']
        result, post_mock = self._create_form_token(no_token)
        self.assertEqual(result, {'formToken': False})
        post_mock.assert_not_called()

    @mute_logger(REST_LOGGER)
    def test_provider_not_osb_refused(self):
        other_provider = self.env['payment.provider'].create({'name': 'Not OSB'})
        payload = self._inline_values(self.order, self.partner)
        payload['provider_id'] = other_provider.id
        payload['osb_access_token'] = other_provider._osb_get_form_token_access(
            'order', payload['order_id'], payload['partner_id'], payload['currency_id'])
        result, post_mock = self._create_form_token(payload)
        self.assertEqual(result, {'formToken': False})
        post_mock.assert_not_called()

    @mute_logger(REST_LOGGER)
    def test_malformed_payloads_refused(self):
        payload = self._inline_values(self.order, self.partner)
        for body in ('not json', '[1, 2]', json.dumps(dict(payload, provider_id='x')),
                     json.dumps(dict(payload, currency_id=None)), json.dumps(dict(payload, provider_id=999999999)),
                     json.dumps(dict(payload, order_id='None'))):
            with self.subTest(body=body[:60]):
                result, post_mock = self._create_form_token(body)
                self.assertEqual(result, {'formToken': False})
                post_mock.assert_not_called()

    # --- payment submit (transaction) --------------------------------------------------------

    def _submit_payload(self, tx):
        processing_values = tx._get_specific_processing_values({})
        return {
            'provider_id': self.provider.id, 'reference': tx.reference, 'amount': tx.amount,
            'currency_id': self.currency.id, 'osb_access_token': processing_values['osb_access_token'],
        }

    def test_submit_own_transaction_accepted(self):
        tx = self._create_transaction('direct', reference='%s-1' % self.order.name, amount=self.order.amount_total,
                                      sale_order_ids=[(6, 0, self.order.ids)])
        result, post_mock = self._create_form_token(self._submit_payload(tx))
        self.assertEqual(result, {'formToken': 'TOKEN'})
        self.assertEqual(post_mock.call_args.kwargs['json']['orderId'], self.order.name)

    @mute_logger(REST_LOGGER)
    def test_submit_transaction_of_another_customer_refused(self):
        tx = self._create_transaction('direct', reference='%s-1' % self.order.name, amount=self.order.amount_total,
                                      sale_order_ids=[(6, 0, self.order.ids)])
        other_tx = self._create_transaction('direct', reference='%s-1' % self.other_order.name,
                                            amount=self.other_order.amount_total, partner_id=self.other_partner.id,
                                            sale_order_ids=[(6, 0, self.other_order.ids)])
        payload = self._submit_payload(tx)
        for changes in ({'reference': other_tx.reference}, {'osb_access_token': None}, {'osb_access_token': 'forged'}):
            with self.subTest(changes=changes):
                result, post_mock = self._create_form_token(dict(payload, **changes))
                self.assertEqual(result, {'formToken': False})
                post_mock.assert_not_called()

    @mute_logger(REST_LOGGER)
    def test_transaction_token_refused_for_an_order(self):
        """A transaction token never opens the order branch, whatever its reference holds."""
        payload = self._inline_values(self.other_order, self.other_partner)
        tx = self._create_transaction('direct', reference='%s|%s|%s' % (
            self.other_order.id, self.other_partner.id, self.currency.id), amount=1.0)
        payload['osb_access_token'] = tx._get_specific_processing_values({})['osb_access_token']
        result, post_mock = self._create_form_token(payload)
        self.assertEqual(result, {'formToken': False})
        post_mock.assert_not_called()

    @mute_logger(REST_LOGGER)
    def test_redirect_mode_refused(self):
        self.provider.osb_payment_data_entry_mode = 'redirect'
        result, post_mock = self._create_form_token(self._inline_values(self.order, self.partner))
        self.assertEqual(result, {'formToken': False})
        post_mock.assert_not_called()

    def test_submit_sends_transaction_amount_and_currency(self):
        """The amount and currency sent to the gateway are those of the transaction, not of the request."""
        tx = self._create_transaction('direct', reference='%s-1' % self.order.name, amount=self.order.amount_total,
                                      sale_order_ids=[(6, 0, self.order.ids)])
        payload = dict(self._submit_payload(tx), amount=1.0, currency_id=self.env.ref('base.USD').id)
        result, post_mock = self._create_form_token(payload)
        self.assertEqual(result, {'formToken': 'TOKEN'})
        sent = post_mock.call_args.kwargs['json']
        self.assertEqual(int(sent['amount']), 10000)
        self.assertEqual(sent['currency'], 'EUR')

    @mute_logger(REST_LOGGER)
    def test_submit_without_sales_order_refused(self):
        tx = self._create_transaction('direct', reference='OSB-NO-ORDER', amount=100.0)
        result, post_mock = self._create_form_token(self._submit_payload(tx))
        self.assertEqual(result, {'formToken': False})
        post_mock.assert_not_called()
