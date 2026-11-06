# -*- coding: utf-8 -*-
{
    'name': "Property Management Dashboard",
    'summary': "Modern, colourful property analytics dashboard — properties, "
               "units, buildings, contacts, tenancy contracts and invoices.",
    'description': """
Property Management Dashboard
=============================
A modernised, 3D/glassmorphism analytics dashboard for the rental_management
property suite, built with OWL + Chart.js for Odoo 18.

Features
--------
* KPI cards: total properties, available, on-rent, sold, buildings,
  active tenancies, tenants, occupancy %, rent invoiced, outstanding.
* Charts: properties by status, by type, by sub-type (villa/apartment...),
  monthly rent invoiced trend, contracts by status, top buildings by units.
* Tables: recent tenancy contracts and top outstanding invoices.
* Filters: property type, sale/rent, region, building, sub-type, year, month.
* 5 switchable themes (Purple, Ocean, Light, Dark, Comet) with a colourful,
  glassmorphism UI matching the Advanced Accounting Dashboard.
* Every KPI card and chart segment is clickable and drills into the
  underlying Odoo list views.
    """,
    'author': "Al-Shafar",
    'category': 'Real Estate',
    'version': '20.0.7.0.0',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'rental_management',
    ],
    'data': [
        'security/ir.access.csv',
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'property_dashboard/static/src/css/dashboard.css',
            'property_dashboard/static/src/js/property_dashboard.js',
            'property_dashboard/static/src/js/property_statistics.js',
            'property_dashboard/static/src/xml/property_dashboard.xml',
            'property_dashboard/static/src/xml/property_statistics.xml',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
