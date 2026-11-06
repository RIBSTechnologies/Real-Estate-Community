# -*- coding: utf-8 -*-
# account_move.py — base fields only; analytic auto-population is in analytic_setup.py

from odoo import models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    contract_id = fields.Many2one(
        'contract.contract',
        string="Contract",
        ondelete='set null',
        index=True,
    )
    tenancy_id = fields.Many2one(
        'tenancy.details',
        string="Tenancy Contract",
        ondelete='set null',
        index=True,
    )
    refund_component_type = fields.Selection([
        ('invoice', 'Invoice Refund'),
        ('tax', 'Tax Refund'),
        ('deposit', 'Security Deposit Refund'),
    ], string="Refund Component Type", index=True)
