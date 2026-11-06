from odoo import models, fields

class ProjectDocumentLine(models.Model):
    _inherit = 'subproject.document'
    
    expiry_date = fields.Date(string='Expiry Date')