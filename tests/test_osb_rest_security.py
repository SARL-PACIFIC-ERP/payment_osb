# Security tests of the REST (embedded fields) notifications: kr-answer must be authenticated by
# its kr-hash before any parsing, and must only ever be parsed as JSON (never evaluated).
import hashlib
import hmac
import json
import sys

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_osb.helpers import tools

PROBE = 'payment_osb_kr_answer_probe'
# A Python expression that is not JSON: evaluating it sets an attribute on the sys module.
PYTHON_ANSWER = "setattr(__import__('sys'), %r, 'executed') or {'orderCycle': 'OPEN'}" % PROBE
CONTROLLER_LOGGER = 'odoo.addons.payment_osb.controllers.main'


def _sign(key, answer):
    return hmac.new(key.encode(), answer.encode(), hashlib.sha256).hexdigest()


@tagged('post_install', '-at_install')
class TestOsbRestSecurity(PaymentHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enable_process_patcher = False
        cls.enable_post_process_patcher = False
        cls.provider = cls._prepare_provider('osb', update_values={
            'is_published': True, 'osb_test_password': 'pwdOSB', 'osb_sha256_test_key': 'shaOSB'})
        cls.payment_method_id = cls.provider.payment_method_ids.filtered(lambda pm: pm.code == 'osb').id
        cls.currency = cls.currency_euro
        cls.amount = 100.0
        cls.partner = cls.default_partner

    def setUp(self):
        super().setUp()
        self.addCleanup(lambda: hasattr(sys, PROBE) and delattr(sys, PROBE))

    def _answer(self, reference, status='AUTHORISED'):
        return json.dumps({
            'orderCycle': 'CLOSED', 'orderStatus': 'PAID',
            'transactions': [{'uuid': 'uuid-%s' % reference, 'detailedStatus': status, 'amount': 10000,
                              'currency': 'EUR', 'metadata': [['order_ref', reference]]}],
        })

    def _post(self, route, answer, key=None, kr_hash=None, kr_hash_key='password'):
        data = {
            'kr-hash': kr_hash if kr_hash is not None else _sign(key, answer),
            'kr-hash-algorithm': 'sha256_hmac',
            'kr-hash-key': kr_hash_key,
            'kr-answer': answer,
        }
        return self._make_http_post_request(self._build_url(route), data=data)

    # --- kr-answer is never evaluated --------------------------------------------------------

    @mute_logger(CONTROLLER_LOGGER)
    def test_ipn_unsigned_python_answer_not_executed(self):
        response = self._post('/payment/osb/ipn', PYTHON_ANSWER, kr_hash='forged')
        self.assertIsNone(getattr(sys, PROBE, None), "kr-answer was executed")
        self.assertEqual(response.text, 'Bad request received.')

    @mute_logger(CONTROLLER_LOGGER)
    def test_return_unsigned_python_answer_not_executed(self):
        tx = self._create_transaction('direct', reference='OSBPYRET')
        self._post('/payment/osb/return', PYTHON_ANSWER, kr_hash='forged', kr_hash_key='sha256_hmac')
        self.assertIsNone(getattr(sys, PROBE, None), "kr-answer was executed")
        self.assertEqual(tx.state, 'draft')
        self.assertFalse(tx.payment_data_ids)

    @mute_logger(CONTROLLER_LOGGER)
    def test_ipn_signed_python_answer_not_executed(self):
        """Even correctly signed, a kr-answer that is not JSON is rejected without being run."""
        response = self._post('/payment/osb/ipn', PYTHON_ANSWER, key='pwdOSB')
        self.assertIsNone(getattr(sys, PROBE, None), "kr-answer was executed")
        self.assertEqual(response.text, 'Bad request received.')

    # --- signature checks --------------------------------------------------------------------

    def test_ipn_valid_signature_processed(self):
        tx = self._create_transaction('direct', reference='OSBRESTIPN')
        response = self._post('/payment/osb/ipn', self._answer('OSBRESTIPN'), key='pwdOSB')
        self.assertEqual(response.text, 'Payment processed, order has been updated.')
        self._run_processing()
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'uuid-OSBRESTIPN')

    def test_return_valid_signature_processed(self):
        tx = self._create_transaction('direct', reference='OSBRESTRET')
        response = self._post('/payment/osb/return', self._answer('OSBRESTRET'), key='shaOSB',
                              kr_hash_key='sha256_hmac')
        self.assertEqual(response.status_code, 200)
        self._run_processing()
        self.assertEqual(tx.state, 'done')

    @mute_logger(CONTROLLER_LOGGER)
    def test_ipn_wrong_signature_rejected(self):
        tx = self._create_transaction('direct', reference='OSBRESTBAD')
        answer = self._answer('OSBRESTBAD')
        for kr_hash in ('', 'forged', _sign('wrong', answer), _sign('pwdOSB', answer).upper(), 'é' * 64):
            with self.subTest(kr_hash=kr_hash):
                response = self._post('/payment/osb/ipn', answer, kr_hash=kr_hash)
                self.assertEqual(response.text, 'Bad request received.')
        # The IPN is signed with the REST password, not with the HMAC-SHA-256 key.
        response = self._post('/payment/osb/ipn', answer, key='shaOSB', kr_hash_key='sha256_hmac')
        self.assertEqual(response.text, 'Bad request received.')
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    @mute_logger(CONTROLLER_LOGGER)
    def test_return_wrong_signature_rejected(self):
        tx = self._create_transaction('direct', reference='OSBRETBAD')
        self._post('/payment/osb/return', self._answer('OSBRETBAD'), key='wrong', kr_hash_key='sha256_hmac')
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    @mute_logger(CONTROLLER_LOGGER)
    def test_unset_key_never_matches(self):
        """An unset key must not sign: str(False) == 'False' would be a key known to anyone."""
        self.provider.write({'osb_test_password': False, 'osb_sha256_test_key': False})
        tx = self._create_transaction('direct', reference='OSBNOKEY')
        answer = self._answer('OSBNOKEY')
        for forged_key in ('False', 'None', ''):
            with self.subTest(forged_key=forged_key):
                response = self._post('/payment/osb/ipn', answer, kr_hash=_sign(forged_key, answer))
                self.assertEqual(response.text, 'Bad request received.')
                self._post('/payment/osb/return', answer, kr_hash=_sign(forged_key, answer),
                           kr_hash_key='sha256_hmac')
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    @mute_logger(CONTROLLER_LOGGER)
    def test_signature_of_another_provider_rejected(self):
        """A kr-answer signed by another provider's key cannot update this provider's transaction."""
        self.provider.copy({'osb_test_password': 'pwdOTHER', 'osb_sha256_test_key': 'shaOTHER'})
        tx = self._create_transaction('direct', reference='OSBOTHER')
        response = self._post('/payment/osb/ipn', self._answer('OSBOTHER'), key='pwdOTHER')
        self.assertEqual(response.text, 'Bad request received.')
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    @mute_logger(CONTROLLER_LOGGER, 'odoo.addons.payment_osb.models.payment_transaction')
    def test_unsupported_hash_algorithm_rejected(self):
        """Not a REST response: handled as a form notification, kr-answer is not even read."""
        tx = self._create_transaction('direct', reference='OSBALGO')
        answer = self._answer('OSBALGO')
        data = {'kr-hash': _sign('pwdOSB', answer), 'kr-hash-algorithm': 'sha1', 'kr-answer': answer}
        response = self._make_http_post_request(self._build_url('/payment/osb/ipn'), data=data)
        self.assertEqual(response.text, 'Bad request received.')
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    def test_check_hash_helper(self):
        answer = self._answer('OSBUNIT')
        post = {'kr-hash': _sign('pwdOSB', answer), 'kr-hash-algorithm': 'sha256_hmac', 'kr-answer': answer}
        self.assertTrue(tools.check_hash(post, 'pwdOSB'))
        self.assertFalse(tools.check_hash(post, 'other'))
        self.assertFalse(tools.check_hash(post, ''))
        self.assertFalse(tools.check_hash(post, False))
        self.assertFalse(tools.check_hash(dict(post, **{'kr-hash': 'é' * 64}), 'pwdOSB'))
        self.assertFalse(tools.check_hash(dict(post, **{'kr-hash-algorithm': 'sha1'}), 'pwdOSB'))
        self.assertFalse(tools.check_hash({'kr-hash': post['kr-hash'], 'kr-hash-algorithm': 'sha256_hmac'}, 'pwdOSB'))
        self.assertIsNone(tools.parse_rest_answer({'kr-answer': PYTHON_ANSWER}))
        self.assertIsNone(tools.parse_rest_answer({'kr-answer': '[1, 2]'}))
        self.assertIsNone(getattr(sys, PROBE, None))
        self.assertEqual(tools.parse_rest_answer({'kr-answer': answer})['orderCycle'], 'CLOSED')
