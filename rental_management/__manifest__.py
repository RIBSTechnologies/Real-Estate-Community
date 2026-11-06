# -*- coding: utf-8 -*-
# Copyright 2020-Today TechKhedut.
# Part of TechKhedut. See LICENSE file for full copyright and licensing details.
{
    'name': """Advanced Property Sale & Rental Management | Real Estate
     | Property Sales | Property Rental | Property Management""",
    'description': """
        - Property Sale
        - Property Rental
        - Lease Contract
        - Landlord Management
        - Customer Management
        - Property Maintenance
        - Customer Recurring Invoice
        - Property List
    """,
    'summary': """
        Property Sale & Rental Management
    """,
    'version': "20.0.3.3.0",
    'author': 'TechKhedut Inc.',
    'company': 'TechKhedut Inc.',
    'maintainer': 'TechKhedut Inc.',
    'website': "https://www.techkhedut.com",
    'category': 'Services',
    'depends': ['mail', 'contacts', 'account', 'hr', 'maintenance', 'crm', 'website'],
    'data': [
        # security
        'security/groups.xml',
        'security/ir.access.csv',
        'security/security.xml',
        # Data
        'data/ir_cron.xml',
        'data/sequence.xml',
        'data/property_product_data.xml',
        'data/update_ir_cron.xml',
        # wizard views
        'wizard/contract_wizard_view.xml',
        'wizard/tenancy_payment_wizard_view.xml',
        'wizard/property_sale_wizard_view.xml',
        'wizard/property_maintenance_wizard_view.xml',
        'wizard/booking_wizard_view.xml',
        'wizard/property_sale_tenancy_xls_report_view.xml',
        'wizard/landlord_tenancy_sold_xls_view.xml',
        'wizard/active_contract_view.xml',
        'wizard/subproject_creation_view.xml',
        'wizard/unit_creation_view.xml',
        'wizard/agreement_preview_view.xml',
        # Views
        'views/assets.xml',
        'views/property_details_view.xml',
        'views/property_document_view.xml',
        'views/user_type_view.xml',
        'views/tenancy_details_view.xml',
        'views/contract_duration_view.xml',
        'views/rent_invoice_view.xml',
        'views/property_amenities_view.xml',
        'views/property_specification_view.xml',
        'views/property_vendor_view.xml',
        'views/property_tag_view.xml',
        'views/product_product_inherit_view.xml',
        'views/property_invoice_inherit.xml',
        'views/res_config_setting_view.xml',
        'views/property_res_city.xml',
        'views/nearby_connectivity_view.xml',
        'views/agreement_template_view.xml',
        'views/configuration_views.xml',
        'views/property_region_views.xml',
        'views/property_project_view.xml',
        'views/property_sub_project_views.xml',
        'views/rent_bill_view.xml',
        'views/templates/property_web_template.xml',
        # Inherit Views
        'views/maintenance_product_inherit.xml',
        'views/property_maintenance_view.xml',
        'views/property_crm_lead_inherit_view.xml',
        # Report views
        'report/property_name.xml',
        'report/tenancy_details_report_template.xml',
        'report/tenancy_details_report_template.xml',
        'report/property_details_report.xml',
        'report/property_sold_report.xml',
        'report/invoice_report_inherit.xml',
        # Mail Template
        'data/active_contract_mail_template.xml',
        'data/tenancy_reminder_mail_template.xml',
        'data/property_book_mail_template.xml',
        'data/property_sold_mail_template.xml',
        'data/sale_invoice_mail_template.xml',
        # menus
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rental_management/static/src/js/lib/jquery.js',
            'rental_management/static/src/xml/template.xml',
            'rental_management/static/src/scss/style.scss',
            'rental_management/static/src/js/lib/index.js',
            'rental_management/static/src/js/lib/map.js',
            'rental_management/static/src/js/lib/xy.js',
            'rental_management/static/src/js/lib/worldLow.js',
            'rental_management/static/src/js/lib/Animated.js',
            'rental_management/static/src/js/lib/apexcharts.js',
            'rental_management/static/src/js/rental.js',
            'rental_management/static/src/components/**/*',
            'rental_management/static/src/views/**/*',
        ],
        'web.assets_frontend': [
            'rental_management/static/src/css/extra.css',
        ],
    },
    'images': [
        'static/description/property-rental.gif',
    ],
    'license': 'OPL-1',
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': 250,
    'currency': 'USD',
}
