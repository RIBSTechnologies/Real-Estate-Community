# -*- coding: utf-8 -*-
{
    'name': 'Al-Shafar PDC Report',
    'summary': 'Professional Excel and PDF PDC Cheque Payment Reporting Module for Bank Submission',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Reporting',
    'author': 'Al-Shafar / Antigravity',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'sh_pdc',
    ],
    'data': [
        'security/ir.access.csv',
        'data/pdc_state_data.xml',
        'report/pdc_report_pdf.xml',
        'wizard/pdc_report_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
