from odoo import fields, models


class View(models.Model):
    """Odoo View"""
    _inherit = "ir.ui.view"

    type = fields.Selection(selection_add=[("tk_map", "Map")])

    def _get_view_info(self):
        return {'tk_map': {'icon': 'location_on'}} | super()._get_view_info()
