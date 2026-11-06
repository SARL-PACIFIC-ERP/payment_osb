# Browser tests of the payment form: the JavaScript of payment_osb must load and keep the payment
# form working. The Python tests cannot see it: they passed while the script did not load at all.
from unittest import SkipTest
from unittest.mock import patch
from urllib.parse import urlencode

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon

GATEWAY_URL = 'https://secure.osb.pf/'

# Stand-in for the JavaScript client of the gateway (KR), served instead of static.osb.pf: the
# tests never reach the gateway. Opening the embedded payment fields ends the test successfully.
KR_STUB = """
window.KR = {
    setFormConfig: async () => {},
    openPopin: () => console.log('test successful'),
    openSelectedPaymentMethod: () => console.log('test successful'),
};
"""

# The gateway client rejects the form token (expired, inconsistent public key).
KR_REJECTING_STUB = """
window.KR = {
    setFormConfig: async () => { throw new Error('Invalid form token'); },
    openPopin: () => console.error('The embedded fields were opened with a rejected form token'),
    openSelectedPaymentMethod: () => console.error('The embedded fields were opened with a rejected form token'),
};
"""

# Helpers of the scenarios: wait for a condition, wait for the interactions of the page, and end
# the test when the payment form posts to the gateway payment page (redirect flow).
JS_HELPERS = """
const waitUntil = async (condition, error, timeout = 10000) => {
    const start = Date.now();
    while (!condition()) {
        if (Date.now() - start > timeout) {
            throw new Error(error);
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
};
// The payment form handles clicks once its interaction has started, which can follow the display
// of the embedded fields when the OSB option is preselected.
const interactionsReady = async () => {
    const service = () => odoo.__WOWL_DEBUG__?.root?.env?.services?.['public.interactions'];
    await waitUntil(service, 'The interactions service is not available');
    await service().isReady;
};
const selectOsb = async () => {
    await interactionsReady();
    await waitUntil(() => document.querySelector('input[data-provider-code="osb"]'), 'No OSB payment option');
    document.querySelector('input[data-provider-code="osb"]').click();
};
const helpMessage = () => document.querySelector('input[data-provider-code="osb"]')
    .closest('[for="o_payment_radio"]').querySelector(':scope > div.small')?.textContent.trim();
const pay = async () => {
    const payButton = document.querySelector('[name="o_payment_submit_button"]');
    await waitUntil(() => !payButton.disabled, 'The Pay button stays disabled');
    payButton.click();
};
const expectGatewayPage = () => {
    HTMLFormElement.prototype.submit = function () {
        if (this.action.startsWith('%(gateway)s')) {
            console.log('test successful');
        } else {
            console.error('Unexpected form submitted to ' + this.action);
        }
    };
};
const expectEmbeddedFields = () => {
    HTMLFormElement.prototype.submit = function () {
        console.error('Redirected to ' + this.action + ' instead of opening the embedded fields');
    };
};
""" % {'gateway': GATEWAY_URL}

PAY_ON_GATEWAY_PAGE = """
expectGatewayPage();
await selectOsb();
await new Promise((resolve) => setTimeout(resolve, 1500));
if (document.querySelector('#osb-embedded-wrapper .kr-smart-form')) {
    throw new Error('Embedded fields displayed without form token');
}
if (!helpMessage()) {
    throw new Error('The help message announcing the redirection was hidden');
}
await pay();
"""


class FakeResponse:
    def json(self):
        return {'status': 'SUCCESS', 'answer': {'formToken': 'TOKEN'}}


class FakeErrorResponse:
    def json(self):
        return {'status': 'ERROR', 'answer': {'errorMessage': 'Gateway unavailable', 'errorCode': 'TEST'}}


@tagged('post_install', '-at_install')
class TestOsbPaymentFormBrowser(PaymentHttpCommon):

    kr_stub = KR_STUB

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls._prepare_provider('osb', update_values={'is_published': True})
        cls.currency = cls.currency_euro

    def fetch_proxy(self, url):
        if '.osb.pf/' in url:
            content = self.kr_stub if 'kr-payment-form' in url else ''
            return self.make_fetch_proxy_response(content)
        return super().fetch_proxy(url)

    def _pay_url(self):
        return '/payment/pay?' + urlencode(self._prepare_pay_values())

    def _run_scenario(self, url, scenario):
        self.browser_js(url, "(async () => {%s\n%s})()" % (JS_HELPERS, scenario), timeout=60)

    def _skip_without_ecommerce(self):
        # The embedded fields read the sales order of the payment form.
        if 'website_sale' not in self.env['ir.module.module']._installed():
            raise SkipTest("The embedded payment form needs eCommerce (website_sale).")

    def _order_to_pay(self):
        """A quotation whose portal page displays the embedded fields (a form token needs a sales order)."""
        self._skip_without_ecommerce()
        self.provider.osb_payment_data_entry_mode = 'embedded'
        pricelist = self.env['product.pricelist'].create({'name': 'OSB EUR', 'currency_id': self.currency.id})
        product = self.env['product.product'].create({'name': 'OSB browser product', 'list_price': 100.0, 'type': 'service'})
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id, 'pricelist_id': pricelist.id,
            'require_signature': False, 'require_payment': True,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 100.0, 'tax_ids': False})],
        })
        order.action_quotation_sent()
        return order

    def _assert_single_redirect_transaction(self):
        operations = self.env['payment.transaction'].search([('provider_id', '=', self.provider.id)]).mapped('operation')
        self.assertEqual(operations, ['online_redirect'], "A single transaction, in the redirect flow")

    def test_redirect_mode_pays_on_gateway(self):
        """The script loads without error and leaves the redirect flow to the core."""
        self.provider.osb_payment_data_entry_mode = 'redirect'
        self._run_scenario(self._pay_url(), PAY_ON_GATEWAY_PAGE)
        self._assert_single_redirect_transaction()

    def test_embedded_mode_without_form_token_falls_back_to_redirect(self):
        """When no form token is created, the customer still pays on the gateway payment page."""
        self._skip_without_ecommerce()
        self.provider.osb_payment_data_entry_mode = 'embedded'
        # Without sales order, /payment/osb/createFormToken refuses to create a form token.
        self._run_scenario(self._pay_url(), PAY_ON_GATEWAY_PAGE)
        # The redirect flow is chosen when the payment option is selected, not after a failed
        # direct payment.
        self._assert_single_redirect_transaction()

    def test_embedded_mode_opens_embedded_fields(self):
        """With a form token, the embedded fields are displayed and Pay opens them."""
        order = self._order_to_pay()
        scenario = """
expectEmbeddedFields();
await selectOsb();
await waitUntil(() => document.querySelector('#osb-embedded-wrapper .kr-smart-form'), 'Embedded fields not displayed');
if (helpMessage()) {
    throw new Error('The help message announcing the redirection is still displayed');
}
await pay();
"""
        with patch('odoo.addons.payment_osb.controllers.rest.requests.post', return_value=FakeResponse()) as post_mock:
            self._run_scenario(order.get_portal_url(), scenario)
        self.assertEqual(post_mock.call_count, 1, "A single form token is created and then reused on payment")
        self.assertEqual(post_mock.call_args.kwargs['json']['orderId'], order.name)

    @mute_logger('odoo.addons.payment_osb.controllers.rest')
    def test_no_form_token_on_payment_falls_back_to_redirect(self):
        """When no form token can be had at payment time, the customer pays on the gateway payment page."""
        order = self._order_to_pay()
        scenario = """
await selectOsb();
await waitUntil(() => document.querySelector('#osb-embedded-wrapper .kr-smart-form'), 'Embedded fields not displayed');
// The form token is stored for 15 minutes: past that, a new one is requested on payment, and the
// gateway does not deliver it.
localStorage.clear();
KR.openSelectedPaymentMethod = KR.openPopin = () => console.error('The embedded fields were opened without form token');
expectGatewayPage();
await pay();
"""
        responses = [FakeResponse(), FakeErrorResponse()]  # On display, then on payment.
        with patch('odoo.addons.payment_osb.controllers.rest.requests.post', side_effect=responses) as post_mock:
            self._run_scenario(order.get_portal_url(), scenario)
        self.assertEqual(post_mock.call_count, 2)

    def test_rejected_form_token_falls_back_to_redirect(self):
        """When the gateway client rejects the form token, the customer pays on the gateway payment page."""
        order = self._order_to_pay()
        self.kr_stub = KR_REJECTING_STUB
        scenario = """
expectGatewayPage();
await selectOsb();
await new Promise((resolve) => setTimeout(resolve, 1500));
if (document.querySelector('#osb-embedded-wrapper .kr-smart-form')) {
    throw new Error('Embedded fields kept with a rejected form token');
}
await pay();
"""
        with patch('odoo.addons.payment_osb.controllers.rest.requests.post', return_value=FakeResponse()):
            self._run_scenario(order.get_portal_url(), scenario)
