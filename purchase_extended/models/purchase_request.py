from odoo import fields, models


class PurchaseRequest(models.Model):
    _name = 'purchase.request'
    _inherit = ['purchase.request', 'purchase.property.location.mixin']

    building_id = fields.Many2one(tracking=True)
    unit_id = fields.Many2one(tracking=True)
    contact_person = fields.Char(tracking=True)
