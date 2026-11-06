from odoo import api, fields, models

class ContractActivationConfirm(models.TransientModel):
    _name = 'contract.activation.confirm'
    _description = 'Contract Activation Confirmation'

    contract_id = fields.Many2one('tenancy.details', required=True)
    message = fields.Text(readonly=True)

    def action_confirm(self):
        return self.contract_id.with_context(
            skip_document_confirmation=True
        ).action_active_rent_contract()
        
    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}