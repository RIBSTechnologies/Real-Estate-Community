from odoo import models, fields, api
from odoo.exceptions import ValidationError

class DefaultTermsConditions(models.Model):
    _name = 'default.terms.conditions'
    _description = "Default Terms Conditions"

    terms_html = fields.Html(string='Terms and Conditions')

    @api.model
    def open_singleton_record(self):
        record = self.search([], limit=1)
        if not record:
            record = self.create({'terms_html': 'Add your terms here...'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'default.terms.conditions',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
            'name': 'Terms and Conditions',
        }