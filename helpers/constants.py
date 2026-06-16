# coding: utf-8
#
# Copyright © Lyra Network.
# This file is part of OSB plugin for Odoo. See COPYING.md for license details.
#
# Author:    Lyra Network (https://www.lyra.com)
# Copyright: Copyright © Lyra Network
# License:   http://www.gnu.org/licenses/agpl.html GNU Affero General Public License (AGPL v3)

from odoo.tools.translate import _lt

# WARN: Do not modify code format here. This is managed by build files.
OSB_PLUGIN_FEATURES = {
    'multi': True,
    'restrictmulti': False,
    'qualif': False,
    'shatwo': True,
}

OSB_PARAMS = {
    'GATEWAY_CODE': 'OSB',
    'GATEWAY_NAME': 'OSB',
    'BACKOFFICE_NAME': 'OSB',
    'SUPPORT_EMAIL': 'support@osb.pf',
    'GATEWAY_URL': 'https://secure.osb.pf/vads-payment/',
    'SITE_ID': '12345678',
    'KEY_TEST': '1111111111111111',
    'KEY_PROD': '2222222222222222',
    'CTX_MODE': 'TEST',
    'SIGN_ALGO': 'SHA-256',
    'LANGUAGE': 'fr',

    'GATEWAY_VERSION': 'V2',
    'PLUGIN_VERSION': '4.3.0',
    'CMS_IDENTIFIER': 'Odoo_17-19',
    'REST_URL': 'https://api.secure.osb.pf/api-payment/',
    'STATIC_URL': 'https://static.osb.pf/static/'
}

OSB_LANGUAGES = {
    'cn': _lt("Chinese"),
    'de': _lt("German"),
    'es': _lt("Spanish"),
    'en': _lt("English"),
    'fr': _lt("French"),
    'it': _lt("Italian"),
    'jp': _lt("Japanese"),
    'nl': _lt("Dutch"),
    'pl': _lt("Polish"),
    'pt': _lt("Portuguese"),
    'ru': _lt("Russian"),
    'sv': _lt("Swedish"),
    'tr': _lt("Turkish"),
}

OSB_CARDS = {
    'CB': u'CB',
    'E-CARTEBLEUE': u'e-Carte Bleue',
    'MAESTRO': u'Maestro',
    'MASTERCARD': u'Mastercard',
    'VISA': u'Visa',
    'VISA_ELECTRON': u'Visa Electron',
    'VPAY': u'V PAY',
    'AMEX': u'American Express',
    'APETIZ': u'Apetiz',
    'BANCONTACT': u'Bancontact Mistercash',
    'CA_DO_CARTE': u'CA DO Carte',
    'CHQ_DEJ': u'Chèque Déjeuner',
    'DINERS': u'Diners',
    'DISCOVER': u'Discover',
    'EDENRED': u'Ticket Restaurant',
    'JCB': u'JCB',
    'KADEOS_CULTURE': u'Carte Kadéos Culture',
    'KADEOS_GIFT': u'Carte Kadéos Zénith',
    'PAYPAL': u'PayPal',
    'PAYPAL_BNPL': u'PayPal Pay Later',
    'PAYPAL_BNPL_SB': u'PayPal Pay Later Sandbox',
    'PAYPAL_SB': u'PayPal Sandbox',
    'PRV_BDP': u'Banque de Polynésie',
    'PRV_BDT': u'Banque de Tahiti',
    'PRV_OPT': u'OPT',
    'PRV_SMART_CARD': u'Smart Card',
    'PRV_SOC': u'Banque Socredo',
    'PRV_SOC_GOLD': u'Banque Socredo Gold',
    'PRV_SOC_VERTE': u'Banque Socredo Verte',
    'S-MONEY': u'S-money',
    'SODEXO': u'Pass Restaurant',
}

OSB_CURRENCIES = [
    ['AUD', '036', 2],
    ['CNY', '156', 2],
    ['DJF', '262', 0],
    ['EUR', '978', 2],
    ['FJD', '242', 2],
    ['GBP', '826', 2],
    ['HKD', '344', 2],
    ['JPY', '392', 0],
    ['KHR', '116', 0],
    ['LAK', '418', 2],
    ['NZD', '554', 2],
    ['SBD', '090', 2],
    ['THB', '764', 2],
    ['USD', '840', 2],
    ['VUV', '548', 0],
    ['XPF', '953', 0],
]

OSB_ONLINE_DOC_URI = {
    'fr': 'https://secure.osb.pf/doc/fr-FR/plugins/',
    'en': 'https://secure.osb.pf/doc/en-EN/plugins/',
}

OSB_DOCUMENTATION = {
    'fr': 'Français',
    'en': 'English',
    'es': 'Español',
    'de': 'Deutsch',
    'pt': 'Português',
}

OSB_PAYMENT_DATA_ENTRY_MODE = {
    'redirect': _lt("Bank data acquisition on payment gateway"),
    'embedded': _lt("Embedded payment fields on merchant site (REST API)"),
    'embedded_extended_with_logos': _lt("Embedded payment fields extended on merchant site with logos (REST API)"),
    'embedded_extended_without_logos': _lt("Embedded payment fields extended on merchant site without logos (REST API)"),
}

OSB_REST_API_KEYS_DESC = 'REST API keys are available in your OSB Back Office (menu: Settings > Shops > REST API keys).'