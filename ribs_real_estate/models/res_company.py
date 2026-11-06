from odoo import models, fields, api, _
from odoo.exceptions import ValidationError



class ResCompany(models.Model):
    _inherit = 'res.company'
    
    company_secretary = fields.Many2one('hr.employee', 'Company Secretary', required=True)
    fax = fields.Char('Fax')

    @api.onchange('company_secretary')
    def _onchange_company_secretary(self):
        if self.company_secretary and not self.company_secretary.work_email:
            raise ValidationError(_("Add Company Secretary Email "))