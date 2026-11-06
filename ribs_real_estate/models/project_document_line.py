from odoo import models, fields

class ProjectDocumentLine(models.Model):
    _inherit = 'project.document.line'
    
    expiry_date = fields.Date(string='Expiry Date')
    notes = fields.Text(string="Notes")
    user_id = fields.Many2one("res.users", string="Added by", readonly=True, default=lambda self: self.env.user)