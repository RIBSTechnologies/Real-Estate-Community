from odoo import api, fields, models


class PurchasePropertyLocationMixin(models.AbstractModel):
    """Building / Unit / Contact Person shared by purchase requests, purchase orders and the
    Create RFQ wizard, so the value picked on a request follows it to the PO."""
    _name = 'purchase.property.location.mixin'
    _description = 'Purchase Building / Unit'

    building_id = fields.Many2one('property.project', string='Building')
    unit_id = fields.Many2one(
        'property.details', string='Unit',
        domain="[('property_project_id', '=', building_id)] if building_id else []")
    contact_person = fields.Char(string='Contact Person')

    @api.onchange('unit_id')
    def _onchange_unit_id(self):
        if self.unit_id.property_project_id:
            self.building_id = self.unit_id.property_project_id

    @api.onchange('building_id')
    def _onchange_building_id(self):
        if self.unit_id and self.unit_id.property_project_id != self.building_id:
            self.unit_id = False
