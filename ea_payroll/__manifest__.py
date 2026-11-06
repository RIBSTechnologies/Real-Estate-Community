# -*- coding: utf-8 -*-
##############################################################################
#
#    ERP Artists
#    Copyright (C) 2025-TODAY ERP Artists (<https://www.erpartists.com>).
#    Author: ERP Artists (<https://www.erpartists.com>)
#
##############################################################################
{
    "name": "Payroll",
    "version": "20.0.1.0.0",
    "category": "Payroll",
    "summary": """Manage employee payroll with contracts, salary structures, payslips,
    payroll batches, contribution registers, reports, and configurable payroll settings.""",
    "description": """ Payroll Management This module provides a simple way to manage employee payroll in Odoo. It helps businesses manage employee contracts, salary structures, salary rules, payslips, and payroll batches from one place. 
Key Features: 
- Manage employee payroll information. 
- Configure employee contracts and payment schedules. 
- Create and manage salary structures. 
- Configure salary rules for payroll calculations. 
- Calculate employee payslips automatically. 
- Process payslips individually or in batches. 
- Manage worked days and salary inputs. 
- Manage payroll contribution registers. 
- View payslip and payroll reports. 
- Send payslips to employees by email. 
- Configure payroll settings and access rights. 
- Keep payroll calculations organized and consistent. 
    This module is useful for businesses that need a simple and centralized system to manage employee salaries and payroll processing. """,
    "author": "ERP Artists",
    "website": "https://www.erpartists.com",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_holidays",
        "mail",
    ],
    "data": [
        "security/hr_payroll_security.xml",
        "security/ir.access.csv",
        "data/hr_payroll_sequence.xml",
        "data/hr_payroll_data.xml",
        "wizard/hr_payroll_contribution_register_report_views.xml",
        "wizard/hr_payroll_payslips_by_employees_views.xml",
        "views/menus.xml",
        "views/hr_contract_views.xml",
        "views/hr_payroll_structure_views.xml",
        "views/hr_salary_rule_category_views.xml",
        "views/hr_contribution_register_views.xml",
        "views/hr_salary_rule_views.xml",
        "views/hr_payslip_line_views.xml",
        "views/hr_payslip_views.xml",
        "views/hr_payslip_run_views.xml",
        "views/hr_employee_views.xml",
        "views/report_contributionregister.xml",
        "views/report_payslip.xml",
        "views/report_payslipdetails.xml",
        "report/report.xml",
        "views/res_config_settings_views.xml",
        "wizard/hr_payroll_send_email.xml",
        "wizard/hr_payslip_change_state_view.xml",
    ],
    "demo": ["demo/hr_payroll_demo.xml"],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': 0.00,
    'currency': 'USD',
}
