# Smoke tests of the payment_osb flows (form redirect, IPN, return, form token).
import json
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon


@tagged('post_install', '-at_install')
class TestOsbSmoke(PaymentHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enable_process_patcher = False
        cls.provider = cls._prepare_provider('osb', update_values={'is_published': True})
        cls.provider_multi = cls._prepare_provider('osbmulti', update_values={'is_published': True})
        cls.payment_method_id = cls.provider.payment_method_ids.filtered(lambda pm: pm.code == 'osb').id
        cls.currency = cls.currency_euro
        cls.amount = 100.0
        cls.reference = 'OSBTEST1'
        cls.partner = cls.default_partner

    def _signed(self, provider, data):
        data = dict(data)
        data['signature'] = provider._osb_generate_sign('out', data)
        return data

    def _notification(self, provider, reference, status='AUTHORISED'):
        return self._signed(provider, {
            'vads_ext_info_order_ref': reference,
            'vads_order_id': reference,
            'vads_trans_status': status,
            'vads_amount': '10000',
            'vads_currency': '978',
            'vads_trans_uuid': 'uuid-%s' % reference,
            'vads_card_brand': 'VISA',
            'vads_card_number': '497010XXXXXX0055',
            'vads_result': '00',
        })

    def test_01_install_data(self):
        self.assertTrue(self.provider)
        self.assertTrue(self.provider_multi)
        self.assertEqual(
            set(self.provider.payment_method_ids.mapped('code')),
            {'osb', 'osbcb', 'osbvisa', 'osbmastercard', 'osbamex', 'osbecartebleue',
             'osbvisaelectron', 'osbvpay', 'osbapplepay', 'osbpaypal'})
        self.assertTrue(self.provider.payment_method_ids.filtered(lambda pm: pm.code == 'osb').active)
        self.assertEqual(self.provider._get_ctx_mode(), 'TEST')
        self.provider.is_live = True
        self.assertEqual(self.provider._get_ctx_mode(), 'PRODUCTION')
        self.provider.is_live = False

    def test_02_available_providers_currency(self):
        providers = self.env['payment.provider'].sudo()._find_available_providers(
            self.env.company.id, self.partner.id, self.amount, currency_id=self.currency_euro.id)
        self.assertIn(self.provider, providers)
        xpf = self.env.ref('base.XPF')
        self.assertIn(xpf.name, self.provider.get_osb_currencies())
        unsupported = self.env['res.currency'].with_context(active_test=False).search(
            [('name', 'not in', self.provider.get_osb_currencies())], limit=1)
        providers = self.env['payment.provider'].sudo()._find_available_providers(
            self.env.company.id, self.partner.id, self.amount, currency_id=unsupported.id)
        self.assertNotIn(self.provider, providers)

    def test_03_pay_page_embedded_then_redirect(self):
        self.provider.osb_payment_data_entry_mode = 'embedded'
        response = self._portal_pay(**self._prepare_pay_values())
        self.assertEqual(response.status_code, 200)
        self.assertIn('o_osb_element_container', response.text)
        self.provider.osb_payment_data_entry_mode = 'redirect'
        response = self._portal_pay(**self._prepare_pay_values())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('o_osb_element_container', response.text)

    def test_04_redirect_form(self):
        self.provider.osb_payment_data_entry_mode = 'redirect'
        values = self._prepare_transaction_values(self.payment_method_id, None, 'redirect')
        values['tokenization_requested'] = False
        processing_values = self._get_processing_values(**values)
        form = self._extract_values_from_html_form(processing_values['redirect_form_html'])
        self.assertEqual(form['action'], 'https://secure.osb.pf/vads-payment/')
        self.assertEqual(form['inputs']['vads_amount'], '10000')
        self.assertEqual(form['inputs']['vads_currency'], '978')
        self.assertEqual(form['inputs']['vads_ctx_mode'], 'TEST')
        self.assertTrue(form['inputs']['signature'])

    def test_05_ipn_done(self):
        tx = self._create_transaction('redirect', reference='OSBIPN1')
        data = self._notification(self.provider, 'OSBIPN1')
        response = self._make_http_post_request(self._build_url('/payment/osb/ipn'), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, 'Payment processed, order has been updated.')
        self._run_processing()
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'uuid-OSBIPN1')
        self.assertEqual(tx.osb_card_brand, 'VISA')

    def test_06_return_refused(self):
        tx = self._create_transaction('redirect', reference='OSBRET1')
        data = self._notification(self.provider, 'OSBRET1', status='REFUSED')
        response = self._make_http_post_request(self._build_url('/payment/osb/return'), data=data)
        self.assertEqual(response.status_code, 200)
        self._run_processing()
        self.assertEqual(tx.state, 'error')

    @mute_logger('odoo.addons.payment_osb.controllers.main')
    def test_07_bad_signature_ignored(self):
        tx = self._create_transaction('redirect', reference='OSBBAD1')
        data = self._notification(self.provider, 'OSBBAD1')
        data['signature'] = 'forged'
        response = self._make_http_post_request(self._build_url('/payment/osb/ipn'), data=data)
        self.assertEqual(response.text, 'Bad request received.')
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    def test_08_amount_mismatch(self):
        tx = self._create_transaction('redirect', reference='OSBAMT1', amount=50.0)
        data = self._notification(self.provider, 'OSBAMT1')
        self._make_http_post_request(self._build_url('/payment/osb/ipn'), data=data)
        self._run_processing()
        self.assertEqual(tx.state, 'error')

    def test_09_create_form_token_on_submit(self):
        product = self.env['product.product'].create({'name': 'OSB product', 'list_price': 100.0, 'type': 'service'})
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'currency_id': self.currency.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 100.0, 'tax_ids': False})],
        })
        tx = self._create_transaction('direct', reference='%s-1' % order.name, amount=order.amount_total,
                                      sale_order_ids=[(6, 0, order.ids)])

        class FakeResponse:
            def json(self):
                return {'status': 'SUCCESS', 'answer': {'formToken': 'TOKEN'}}

        payload = {
            'provider_id': self.provider.id,
            'reference': tx.reference,
            'amount': order.amount_total,
            'currency_id': self.currency.id,
            'osb_access_token': tx._get_specific_processing_values({})['osb_access_token'],
        }
        with patch('odoo.addons.payment_osb.controllers.rest.requests.post', return_value=FakeResponse()):
            response = self.url_open('/payment/osb/createFormToken', data=json.dumps(payload),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        self.assertEqual(response.status_code, 200, response.text[:2000])
        self.assertEqual(response.json(), {'formToken': 'TOKEN'})

