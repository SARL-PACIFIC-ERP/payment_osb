# Odoo 18 does not validate the paid amount (payment._validate_amount only exists from 19): a signed
# notification must pay the amount of the transaction, in its currency, to mark it done.
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon


@tagged('post_install', '-at_install')
class TestOsbAmount(PaymentHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls._prepare_provider('osb')
        cls.payment_method_id = cls.env.ref('payment_osb.payment_method_osb').id
        cls.currency = cls.currency_euro
        cls.amount = 100.0
        cls.partner = cls.default_partner

    def _notify(self, reference, **values):
        data = {
            'vads_ext_info_order_ref': reference, 'vads_order_id': reference, 'vads_trans_status': 'AUTHORISED',
            'vads_trans_uuid': 'uuid-%s' % reference, 'vads_result': '00', **values,
        }
        data['signature'] = self.provider._osb_generate_sign('out', data)
        self._make_http_post_request(self._build_url('/payment/osb/ipn'), data=data)

    def test_amount_of_the_transaction_done(self):
        tx = self._create_transaction('redirect', reference='OSBAMOUNT1')
        self._notify(tx.reference, vads_amount='10000', vads_currency='978')
        self.assertEqual(tx.state, 'done')

    @mute_logger('odoo.addons.payment_osb.controllers.main')
    def test_lower_amount_error(self):
        tx = self._create_transaction('redirect', reference='OSBAMOUNT2')
        self._notify(tx.reference, vads_amount='100', vads_currency='978')
        self.assertEqual(tx.state, 'error')

    @mute_logger('odoo.addons.payment_osb.controllers.main')
    def test_other_currency_error(self):
        tx = self._create_transaction('redirect', reference='OSBAMOUNT3')
        self._notify(tx.reference, vads_amount='10000', vads_currency='953')
        self.assertEqual(tx.state, 'error')

    def test_converted_payment_done(self):
        """On a currency conversion, the amount of the transaction is in the effective pair."""
        tx = self._create_transaction('redirect', reference='OSBAMOUNT4')
        self._notify(tx.reference, vads_amount='11933', vads_currency='953',
                     vads_effective_amount='10000', vads_effective_currency='978')
        self.assertEqual(tx.state, 'done')
