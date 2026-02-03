# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Payment Provider: Paytm",
    'version': '19.0.1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "A payment provider covering India",
    'description': " ",  # Non-empty string to avoid loading the README file.,
    'website': "https://www.odoo.com/",
    'images': ['static/description/banner.jpg'],
    'data': [
        'data/payment_provider_data.xml',
        'views/payment_provider_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'odoo_payment_paytm/static/src/interactions/payment_form.js'
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'depends': ['payment'],
    'author': "Odoo IN Pvt Ltd",
    'license': 'LGPL-3',
}
