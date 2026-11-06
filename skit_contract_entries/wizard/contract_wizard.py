from odoo import fields, models
from odoo.exceptions import UserError


class ContractWizard(models.TransientModel):
    _inherit = 'contract.wizard'
    _description = "Contract Wizard" 

    def contract_action(self):
        res = super().contract_action()
        tenancy = res.get("res_id")
        tenancy_id = self.env['tenancy.details'].sudo().browse(tenancy)
        contract_posting = tenancy_id.company_id.contract_posting
        if tenancy_id and contract_posting and tenancy_id.invoice_count != 0:
            tenancy_id._create_contract_journal_entry(tenancy_id)
        return res   