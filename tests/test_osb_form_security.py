# Security tests of the form (vads_) notifications: the signature is required and compared in
# constant time, and neither the computed signature nor the customer data reach the logs.
import logging

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon

CONTROLLER_LOGGER = 'odoo.addons.payment_osb.controllers.main'
TX_LOGGER = 'odoo.addons.payment_osb.models.payment_transaction'
EMAIL = 'osb.customer@example.com'


def _log_text(records):
    formatter = logging.Formatter()
    return '\n'.join(
        record.getMessage() + ('\n' + formatter.formatException(record.exc_info) if record.exc_info else '')
        for record in records
    )


@tagged('post_install', '-at_install')
class TestOsbFormSecurity(PaymentHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enable_process_patcher = False
        cls.enable_post_process_patcher = False
        cls.provider = cls._prepare_provider('osb', update_values={'is_published': True})
        cls.payment_method_id = cls.provider.payment_method_ids.filtered(lambda pm: pm.code == 'osb').id
        cls.currency = cls.currency_euro
        cls.amount = 100.0
        cls.partner = cls.default_partner

    def _form(self, reference, status='AUTHORISED'):
        return {
            'vads_ext_info_order_ref': reference, 'vads_order_id': reference,
            'vads_trans_status': status, 'vads_amount': '10000', 'vads_currency': '978',
            'vads_trans_uuid': 'uuid-%s' % reference, 'vads_result': '00', 'vads_cust_email': EMAIL,
        }

    def _signed_form(self, reference, status='AUTHORISED'):
        data = self._form(reference, status)
        data['signature'] = self.provider._osb_generate_sign('out', data)
        return data

    def _post(self, route, data):
        return self._make_http_post_request(self._build_url(route), data=data)

    def test_bad_signature_rejected_without_leaking_it(self):
        tx = self._create_transaction('redirect', reference='OSBLOG')
        data = self._signed_form('OSBLOG')
        computed = data['signature']
        data['signature'] = 'forged'
        with self.assertLogs('odoo.addons.payment_osb', level='DEBUG') as logs:
            response = self._post('/payment/osb/ipn', data)
        self.assertEqual(response.text, 'Bad request received.')
        self.assertNotIn(computed, _log_text(logs.records))
        self.assertNotIn(EMAIL, _log_text(r for r in logs.records if r.levelno >= logging.INFO))
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    def test_signature_case_insensitive(self):
        tx = self._create_transaction('redirect', reference='OSBCASE')
        data = self._signed_form('OSBCASE')
        data['signature'] = data['signature'].swapcase()
        response = self._post('/payment/osb/ipn', data)
        self.assertEqual(response.text, 'Payment processed, order has been updated.')
        self._run_processing()
        self.assertEqual(tx.state, 'done')

    @mute_logger(CONTROLLER_LOGGER, TX_LOGGER)
    def test_unsigned_form_with_is_rest_flag_rejected(self):
        """The is_rest marker is set by the controller after the REST check, never read from the POST."""
        tx = self._create_transaction('redirect', reference='OSBFLAG')
        for route in ('/payment/osb/ipn', '/payment/osb/return'):
            for data in (dict(self._form('OSBFLAG'), is_rest='1'),
                         dict(self._form('OSBFLAG'), is_rest='1', vads_ext_info_order_ref='')):
                with self.subTest(route=route, data=sorted(data)):
                    response = self._post(route, data)
                    if route.endswith('ipn'):
                        self.assertEqual(response.text, 'Bad request received.')
        self._run_processing()
        self.assertEqual(tx.state, 'draft')
