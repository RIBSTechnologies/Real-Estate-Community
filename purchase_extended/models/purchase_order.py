from odoo import fields, models


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'purchase.property.location.mixin']

    building_id = fields.Many2one(tracking=True)
    unit_id = fields.Many2one(tracking=True)
    contact_person = fields.Char(tracking=True)
