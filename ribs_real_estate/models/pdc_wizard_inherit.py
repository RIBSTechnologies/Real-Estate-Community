from odoo import models, fields, api
from odoo.exceptions import UserError

class PDCWizardInherit(models.Model):
    _inherit = 'pdc.wizard'

    bank_account = fields.Many2one("res.partner.bank", string='Bank Account')
    pdc_location = fields.Selection([('bank','Bank'), ('office','Office')], default='office', required=True ,string="Location")

    def action_bounce_redirect(self):
        # res = super (PDCWizardInherit, self). action_bounced()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bounce Wizard',
            'res_model': 'pdc.bounce.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context':{'default_inv': self.invoice_id.id, 'default_name': self.name}
        }
    
    def action_deposited(self):
        self.pdc_location = 'bank'
        return super().action_deposited()

    # @api.model
    # def default_get(self, fields):
    #     rec = super().default_get(fields)
    #     active_ids = self.env.context.get('active_ids')
    #     invoices = self.env['account.move'].browse(active_ids)
    #     if invoices and len(invoices) == 1:
    #         invoice = invoices[0]
    #     rec['journal_id'] = invoice.tenancy_property_id.property_project_id.cuc_account_id.id
    #     return rec
