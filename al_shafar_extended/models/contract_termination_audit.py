# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ContractTerminationAudit(models.Model):
    _name = 'contract.termination.audit'
    _description = 'Contract Termination & Settlement Audit Log'
    _order = 'execution_datetime desc, id desc'

    name = fields.Char(string="Audit Reference", required=True, copy=False, readonly=True, default=lambda self: _('New'))
    contract_id = fields.Many2one('tenancy.details', string="Tenancy Contract", required=True, ondelete='cascade', index=True)
    customer_id = fields.Many2one('res.partner', string="Customer", related='contract_id.tenancy_id', store=True, readonly=True)
    company_id = fields.Many2one('res.company', string="Company", related='contract_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', string="Currency", related='contract_id.currency_id', readonly=True)

    termination_date = fields.Date(string="Termination Date", required=True)
    termination_reason = fields.Char(string="Termination Reason")
    settlement_method = fields.Selection([
        ('full_month', 'Full Month'),
        ('prorated', 'Prorated by Days'),
        ('no_refund', 'No Refund')
    ], string="Settlement Method", required=True)
    prorate_days = fields.Integer(string="Prorate Days", default=0)
    tax_refundable = fields.Boolean(string="Tax Refundable Option", help="Checked = Tax Not Refundable; Unchecked = Tax Refundable")

    contract_amount = fields.Monetary(string="Contract Amount", currency_field='currency_id')
    amount_already_paid = fields.Monetary(string="Amount Already Paid", currency_field='currency_id')
    amount_utilized = fields.Monetary(string="Amount Utilized", currency_field='currency_id')
    settlement_amount = fields.Monetary(string="Settlement Amount", currency_field='currency_id')
    prorated_amount = fields.Monetary(string="Prorated Amount", currency_field='currency_id')
    remaining_refund_amount = fields.Monetary(string="Remaining Refund Amount", currency_field='currency_id')

    invoice_refund_amount = fields.Monetary(string="Invoice Refund Amount", currency_field='currency_id')
    tax_refund_amount = fields.Monetary(string="Tax Refund Amount", currency_field='currency_id')
    deposit_refund_amount = fields.Monetary(string="Security Deposit Refund Amount", currency_field='currency_id')
    total_refund_amount = fields.Monetary(string="Total Refund Amount", currency_field='currency_id')

    user_id = fields.Many2one('res.users', string="Processed By", default=lambda self: self.env.user, required=True)
    execution_datetime = fields.Datetime(string="Execution Date & Time", default=fields.Datetime.now, required=True)

    invoice_refund_move_id = fields.Many2one('account.move', string="Invoice Refund Entry", ondelete='set null')
    tax_refund_move_id = fields.Many2one('account.move', string="Tax Refund Entry", ondelete='set null')
    deposit_refund_move_id = fields.Many2one('account.move', string="Security Deposit Refund Entry", ondelete='set null')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('contract.termination.audit') or _('SETTL/%s') % fields.Date.today().strftime('%Y%m%d')
        return super().create(vals_list)
