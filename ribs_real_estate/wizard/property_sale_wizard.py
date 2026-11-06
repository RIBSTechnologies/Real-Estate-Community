from odoo import fields, models, api
from odoo.exceptions import UserError, ValidationError, RedirectWarning


class PropertySold(models.TransientModel):
    _inherit = "property.vendor.wizard"

    def property_sale_action(self):
        res = super(PropertySold, self).property_sale_action()
        active_id = self.env.context.get('active_id')
        sell_id = self.env['property.vendor'].browse(active_id)
        if sell_id.ask_price!=self.final_price and not self.env.user.has_group('rental_management.property_rental_manager'):
            raise ValidationError('Only manager can edit the final price.')
        return res







