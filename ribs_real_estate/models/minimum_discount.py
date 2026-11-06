from odoo import models, fields

class MinimumDiscount(models.Model):
    
    _name = 'minimum.discount'
    _description = "Minimum Discount"

    discount = fields.Integer(string='Minimum Discount')

