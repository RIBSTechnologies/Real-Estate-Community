# -*- coding: utf-8 -*-
{
    'name': 'Account Extended - Invoice, Credit Note, Bill, Refund, Journal Entry & Payment Reports',
    'summary': 'Tax Invoice, Credit Note, Vendor Bill / Refund, Journal Entry and Customer / Vendor Payment reports '
               'with company logo, Building / Unit from analytic accounts',
    'version': '20.0.1.8.2',
    'category': 'Accounting/Accounting',
    'author': 'RIBS Technologies',
    'website': 'https://www.ribstechnologies.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'analytic',
        'ribs_real_estate',
        'sh_pdc',
    ],
    'data': [
        'views/narration_views.xml',
        'report/report_common.xml',
        'report/report_uae_rental_tax_invoice.xml',
        'report/report_credit_note.xml',
        'report/report_customer_payment.xml',
        'report/report_vendor_bill.xml',
        'report/report_journal_entry.xml',
        'report/report_combined_pdc_cheque.xml',
        'report/report_rent_tax_invoice.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'account_extended/static/src/js/move_line_copy.js',
            'account_extended/static/src/xml/move_line_copy.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
