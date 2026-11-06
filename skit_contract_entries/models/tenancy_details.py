from odoo import fields, models
from odoo.exceptions import UserError 

#inherit tenancy details
class TenancyDetails(models.Model):
    """Property Rent Contract"""
    _inherit = 'tenancy.details'
    
    journal_entry_id = fields.Many2one('account.move',"Journal Entry", readonly=True)
    
    def action_journal(self):
        """ action to show created journal entries """
        self.ensure_one()
        if not self.journal_entry_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': 'Journal Entry',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.journal_entry_id.id,
            'target': 'current',
        }
        
    def _create_contract_journal_entry(self, tenancy):
        """ create journal entries """
        customer = tenancy.tenancy_id
        rent_amount = tenancy.total_rent_year  
        if rent_amount <= 0:
            raise UserError("Contract rent amount must be greater than 0.")
        tax_amount = 0.0
        taxes = tenancy.tax_ids  
        if taxes:
            tax_res = taxes.compute_all(
                rent_amount,
                currency=tenancy.currency_id or self.env.company.currency_id,
                product=False,
                partner=customer
            )
            tax_amount = tax_res.get('total_included', rent_amount) - rent_amount
        total_amount = rent_amount + tax_amount
        config_id = tenancy.company_id.accrued_revenue_account_id.id
        accrued_account = self.env['account.account'].sudo().browse(config_id)
        expense_config_id = tenancy.company_id.contract_expense_account_id.id
        expense_id = self.env['account.account'].sudo().browse(expense_config_id)
        move_vals = {
            'ref': f"{tenancy.tenancy_seq}",
            'line_ids': [
                (0, 0, {
                    'account_id': expense_id.id,
                    'partner_id': customer.id,
                    'credit': total_amount,
                    'move_type': 'entry',
                }),
                (0, 0, {
                    'account_id': accrued_account.id,
                    'partner_id': customer.id,
                    'debit': total_amount,
                    'move_type': 'entry',
                }),
            ],
        }
        move = self.env['account.move'].with_context(tenancy_id=tenancy.property_id).create(move_vals)
        move.action_post()
        tenancy.write({'journal_entry_id':move.id})
        return move