from odoo import models, fields, api


class PropertySubType(models.Model):
    _inherit = 'property.sub.type'

    is_individual_building = fields.Boolean(string="Is Individual Building", default=False)