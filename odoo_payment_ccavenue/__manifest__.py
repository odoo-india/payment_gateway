# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Payment Provider: CCAvenue",
    'version': '19.0.1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "A payment provider covering India.",
    'website': "https://www.odoo.com/",
    'description': " ",  # Non-empty string to avoid loading the README file.,
    'depends': ['payment'],
    'images': ['static/description/banner.jpg'],
    'data': [
        'views/payment_ccavenue_templates.xml',
        'data/payment_provider_data.xml',
        'views/payment_provider_views.xml',
        'data/payment_cron.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'author': "Odoo IN Pvt Ltd",
    'license': 'LGPL-3',
}
