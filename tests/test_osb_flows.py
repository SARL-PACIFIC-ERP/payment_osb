# Flow tests: payment method activation on install, pending/cancel statuses, sale order
# confirmation, form token refusal on an empty cart and brand logos on the payment page.
import json
import re
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon

# Brands declared inactive in data/payment_method_data.xml.
INACTIVE_BRANDS = {'osbecartebleue', 'osbvisaelectron', 'osbvpay', 'osbapplepay', 'osbpaypal'}


@tagged('post_install', '-at_install')
class TestOsbFlows(PaymentHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enable_process_patcher = False
        cls.enable_post_process_patcher = False
        cls.provider = cls._prepare_provider('osb', update_values={'is_published': True})
        cls.provider_multi = cls._prepare_provider('osbmulti')
        cls.payment_method_id = cls.provider.payment_method_ids.filtered(lambda pm: pm.code == 'osb').id
        cls.currency = cls.currency_euro
        cls.amount = 100.0
        cls.partner = cls.default_partner

    def _signed_form(self, reference, status, amount='10000'):
        data = {
            'vads_ext_info_order_ref': reference, 'vads_order_id': reference,
            'vads_trans_status': status, 'vads_amount': amount, 'vads_currency': '978',
            'vads_trans_uuid': 'uuid-%s' % reference, 'vads_result': '00',
        }
        data['signature'] = self.provider._osb_generate_sign('out', data)
        return data

    def _order(self, name):
        product = self.env['product.product'].create({'name': name, 'list_price': 100.0, 'type': 'service'})
        # The order currency is computed from the pricelist, and a new database requires an online
        # signature before confirmation: set both, or the order is not confirmed by the payment.
        pricelist = self.env['product.pricelist'].create({'name': 'OSB EUR', 'currency_id': self.currency.id})
        return self.env['sale.order'].create({
            'partner_id': self.partner.id, 'pricelist_id': pricelist.id, 'require_signature': False,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 100.0,
                                   'tax_ids': False})],
        })

    def test_payment_methods_active_as_declared(self):
        """Installing does not activate the brands that the data declares inactive."""
        pms = self.env['payment.method'].with_context(active_test=False).search(
            [('provider_id', 'in', (self.provider | self.provider_multi).ids)])
        self.assertEqual(
            {pm.code for pm in pms if not pm.active}, INACTIVE_BRANDS,
            sorted((pm.code, pm.active) for pm in pms))
        self.assertTrue(pms.filtered(lambda pm: pm.code in ('osb', 'osbmulti')).mapped('active'))
        self.assertEqual(self.provider._get_default_payment_method_codes(), set())
        self.assertEqual(self.provider_multi._get_default_payment_method_codes(), set())

    def test_brand_logos_on_payment_page(self):
        self.provider.osb_payment_data_entry_mode = 'redirect'
        names = ['American Express', 'Apple Pay', 'CB', 'e-Carte Bleue', 'Mastercard', 'PayPal', 'V PAY',
                 'Visa', 'Visa Electron']
        html = self._portal_pay(**self._prepare_pay_values()).text
        shown = {n for n in names if re.search(r'title="%s"' % re.escape(n), html)}
        self.assertEqual(shown, {'American Express', 'CB', 'Mastercard', 'Visa'})

    def test_ipn_pending(self):
        tx = self._create_transaction('redirect', reference='OSBPEND')
        response = self._make_http_post_request(self._build_url('/payment/osb/ipn'),
                                                data=self._signed_form('OSBPEND', 'WAITING_AUTHORISATION'))
        self.assertEqual(response.text, 'Payment processed, order has been updated.')
        self.assertEqual(tx.state, 'draft', "the notification is only queued before the cron")
        self.assertTrue(tx.payment_data_ids)
        self._run_processing()
        self.assertEqual(tx.state, 'pending')
        self.assertFalse(tx.payment_data_ids)

    def test_return_cancelled(self):
        tx = self._create_transaction('redirect', reference='OSBCANC')
        self._make_http_post_request(self._build_url('/payment/osb/return'),
                                     data=self._signed_form('OSBCANC', 'CANCELLED'))
        self._run_processing()
        self.assertEqual(tx.state, 'cancel')

    def test_sale_order_confirmed_after_processing(self):
        order = self._order('OSB flow product')
        tx = self._create_transaction('redirect', reference='OSBSO', amount=order.amount_total,
                                      sale_order_ids=[(6, 0, order.ids)])
        self._make_http_post_request(self._build_url('/payment/osb/ipn'),
                                     data=self._signed_form('OSBSO', 'AUTHORISED'))
        self.assertEqual(order.state, 'draft')
        self._run_processing()
        self.assertEqual(tx.state, 'done')
        self.assertTrue(tx.is_post_processed)
        self.assertEqual(order.state, 'sale')

    @mute_logger('odoo.http')
    def test_create_form_token_refused_for_empty_cart(self):
        order = self._order('OSB empty cart product')
        tx = self._create_transaction('direct', reference='%s-1' % order.name, amount=100.0,
                                      sale_order_ids=[(6, 0, order.ids)])
        order.order_line.unlink()
        self.assertFalse(order._is_cart_ready_for_checkout())
        payload = {'provider_id': self.provider.id, 'reference': tx.reference, 'amount': 0.0,
                   'currency_id': self.currency.id,
                   'osb_access_token': tx._get_specific_processing_values({})['osb_access_token']}
        with patch('odoo.addons.payment_osb.controllers.rest.requests.post') as post_mock:
            response = self.url_open('/payment/osb/createFormToken', data=json.dumps(payload),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        self.assertEqual(response.status_code, 422, response.text[:500])
        post_mock.assert_not_called()
