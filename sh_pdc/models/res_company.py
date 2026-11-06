# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    pdc_customer = fields.Many2one(
        'account.account', string="PDC Account for customer")

    pdc_vendor = fields.Many2one(
        'account.account', string="PDC Account for Vendor")

    auto_fill_open_invoice = fields.Boolean(
        string="Auto Fill open Invoice in PDC on Customer Selection ")

    pdc_operation_type = fields.Selection([('cancel', 'Cancel Only'), ('cancel_draft', 'Cancel and Reset to Draft'), ('cancel_delete', 'Cancel and Delete')],
                                          default='cancel', string="Opration Type")

    # =============
    # Customer
    # =============

    is_cust_due_notify = fields.Boolean('Customer Due Notification')

    is_notify_to_customer = fields.Boolean('Notify to Customer')

    is_notify_to_user = fields.Boolean('Notify to Internal User ')

    sh_user_ids = fields.Many2many(
        'res.users', relation='sh_user_ids_customer_company_rel', string='Responsible User')

    notify_on_1 = fields.Char(string='Notify On 1')

    notify_on_2 = fields.Char(string='Notify On 2')

    notify_on_3 = fields.Char(string='Notify On 3')

    notify_on_4 = fields.Char(string='Notify On 4')

    notify_on_5 = fields.Char(string='Notify On 5')

    # =============
    # Vendor
    # =============

    # is_vendor_due_notify = fields.Boolean('Vendor Due Notification')

    # is_notify_to_vendor = fields.Boolean('Notify to Vendor')

    # is_notify_to_user_vendor = fields.Boolean('Notify to internal User')

    # sh_user_ids_vendor = fields.Many2many(
    #     'res.users', relation='sh_user_ids_vendor_company_rel', string='Responsible User ')

    # notify_on_1_vendor = fields.Char(string='Notify on 1')

    # notify_on_2_vendor = fields.Char(string='Notify on 2')

    # notify_on_3_vendor = fields.Char(string='Notify on 3')

    # notify_on_4_vendor = fields.Char(string='Notify on 4')

    # notify_on_5_vendor = fields.Char(string='Notify on 5')
