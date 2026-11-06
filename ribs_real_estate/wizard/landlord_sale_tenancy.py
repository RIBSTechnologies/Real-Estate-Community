from odoo import fields, api, models

class LandlordSaleTenancy(models.TransientModel):

    _inherit = 'landlord.sale.tenancy'

    report_for = fields.Selection(
        [('tenancy', 'Rent'), ('sold', 'Property Sold')], string="Report For", default='tenancy')