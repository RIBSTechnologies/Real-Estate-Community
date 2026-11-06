from odoo import api, models, _
from odoo.exceptions import UserError

class ActiveContract(models.Model):
    _inherit = 'active.contract'
    _description = "Active Contract" 

    # Added in the ribs_real_estate module
    # def action_create_contract(self): 
    #     """Extend method to create journal entries"""
    #     res = super().action_create_contract()
    #     for move in self:
    #         active_id = self.env.context.get("active_id")
    #         tenancy_id = self.env["tenancy.details"].browse(active_id)
    #         auto_apply_contract_period = tenancy_id.company_id.auto_apply_contract_period
    #         move_id = self.env['account.move'].sudo().search([('tenancy_id', '=', tenancy_id.id)])
    #         if move_id and auto_apply_contract_period:
    #             # Update start / end dates in ALL lines
    #             move_id.invoice_line_ids.write({
    #                 'deferred_start_date': tenancy_id.start_date,
    #                 'deferred_end_date': tenancy_id.end_date,
    #             })
    
    #             # Update installment line name (Commercial / Residential)
    #             partner = move_id.partner_id
    #             product_name = "Property Payment Commercial" if partner.is_company else "Property Payment Residential"
    #             installment_product_id = tenancy_id.installment_item_id.id
    
    #             # Update only the installment product line
    #             line = move_id.invoice_line_ids.filtered(
    #                 lambda l: l.product_id.id == installment_product_id
    #             )
    #             if line:
    #                 line.name = product_name
    
    #         # Create Journal Entry if enabled
    #         if tenancy_id.company_id.contract_posting:
    #             tenancy_id._create_contract_journal_entry(tenancy_id)
    #     return res

    # Extend this method to updated analytic for manual contracts
    def _prepare_installment(self):
        res = super()._prepare_installment()
        active_id = self.env.context.get("active_id")
        tenancy_id = self.env["tenancy.details"].browse(active_id)
        # Update analytic
        if tenancy_id.property_id and tenancy_id.property_id.analytic_account_id:
            invoice_ids = tenancy_id.rent_invoice_ids.mapped('rent_invoice_id')
            non_analytic_lines = invoice_ids.mapped('line_ids').filtered(lambda l: not l.analytic_distribution)
            non_analytic_lines.write(
                {'analytic_distribution':{tenancy_id.property_id.analytic_account_id.id: 100}})
        return res
   
            