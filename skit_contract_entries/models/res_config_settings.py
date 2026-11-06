
from odoo import api, fields, models, _

#inherit res config settings
class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"
    
    contract_posting = fields.Boolean(string="Contract Posting",related="company_id.contract_posting",readonly=False)
    
    accrued_revenue_account_id = fields.Many2one('account.account',string="Accrued Revenue Account", 
                                                related="company_id.accrued_revenue_account_id", 
                                                readonly=False)
    
    contract_expense_account_id = fields.Many2one('account.account',string="Contract Expense Account", 
                                                related="company_id.contract_expense_account_id", 
                                                readonly=False)
    
    auto_apply_contract_period = fields.Boolean(string="Auto-Apply Contract Period to Invoices", 
                                                related="company_id.auto_apply_contract_period", 
                                                readonly=False)