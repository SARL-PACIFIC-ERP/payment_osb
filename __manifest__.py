# coding: utf-8
#
# Copyright © Lyra Network.
# This file is part of OSB plugin for Odoo. See COPYING.md for license details.
#
# Author:    Lyra Network (https://www.lyra.com)
# Copyright: Copyright © Lyra Network
# License:   http://www.gnu.org/licenses/agpl.html GNU Affero General Public License (AGPL v3)

{
    'name': 'OSB Payment Provider',
    'version': '19.0.4.3.0',
    'summary': 'Accept payments with OSB secure payment gateway.',
    'category': 'Accounting/Payment Providers',
    'author': 'Lyra Network',
    'website': 'https://www.lyra.com/',
    'license': 'AGPL-3',
    'depends': ['payment', 'account'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_provider_views_multi.xml',
        'views/payment_osb_templates.xml',
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
        'data/payment_provider_data_multi.xml',
        'security/ir.model.access.csv',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_osb/static/src/**/*'
        ]
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'images': ['static/description/icon.png'],
    'application': True,
    'installable': True
}
