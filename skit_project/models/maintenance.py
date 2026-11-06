from odoo import fields, models


#inherit property maintenance 
class PropertyMaintenance(models.Model):
    _inherit = 'maintenance.request'
    
    def action_crete_bill(self):
        """ to pass the property id with context to update analytic distribution """
        property_id = self.property_id 
        return super(
            PropertyMaintenance,
            self.with_context(tenancy_id=property_id)
        ).action_crete_bill()
    
    def action_crete_invoice(self):
        """ to pass the property id with context to update analytic distribution """
        property_id = self.property_id
        return super(
            PropertyMaintenance,
            self.with_context(tenancy_id=property_id)
        ).action_crete_invoice()