from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"
    
    contract_posting = fields.Boolean(string="Contract Posting", default=False)
    accrued_revenue_account_id = fields.Many2one('account.account', string="Accrued Revenue Account", domain=[('account_type', '=', 'asset_current')])
    contract_expense_account_id = fields.Many2one('account.account', string="Contract Expense Account", domain=[('account_type', '=', 'liability_current')])
    auto_apply_contract_period = fields.Boolean(string="Auto-Apply Contract Period to Invoices", default=False)