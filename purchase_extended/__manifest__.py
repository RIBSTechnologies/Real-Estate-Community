# -*- coding: utf-8 -*-
{
    'name': 'Purchase Extended - MR & Local Purchase Order Reports',
    'summary': 'Material Requisition (MR) and Local Purchase Order print reports',
    'version': '20.0.4.6.0',
    'category': 'Purchases',
    'author': 'Al-Shafar / Antigravity',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'purchase',
        'purchase_request',
        'rental_management',
    ],
    'data': [
        'views/res_company_views.xml',
        'views/purchase_property_location_views.xml',
        'reports/material_requisition_report_action.xml',
        'reports/material_requisition_report_template.xml',
        'reports/local_purchase_order_report_action.xml',
        'reports/local_purchase_order_report_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
