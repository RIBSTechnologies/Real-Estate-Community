from odoo import fields, models

class PropertyXlsReport(models.TransientModel):

    _inherit = 'property.report.wizard'

    type = fields.Selection(
        [('tenancy', 'Rent'), ('sold', 'Property Sold')], string="Report For", default='tenancy')