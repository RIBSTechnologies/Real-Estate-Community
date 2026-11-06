from odoo import api, models


class PurchaseRequestLineMakePurchaseOrder(models.TransientModel):
    _name = 'purchase.request.line.make.purchase.order'
    _inherit = ['purchase.request.line.make.purchase.order', 'purchase.property.location.mixin']

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        line_ids = [cmd[2]['line_id'] for cmd in res.get('item_ids', []) if cmd[0] == 0]
        requests = self.env['purchase.request.line'].browse(line_ids).request_id
        # Only prefill when every selected request points at the same place.
        if len(requests.building_id) == 1 and all(request.building_id for request in requests):
            res['building_id'] = requests.building_id.id
        if len(requests.unit_id) == 1 and all(request.unit_id for request in requests):
            res['unit_id'] = requests.unit_id.id
        contacts = set(requests.mapped('contact_person'))
        if len(contacts) == 1 and all(request.contact_person for request in requests):
            res['contact_person'] = contacts.pop()
        return res

    @api.model
    def _prepare_purchase_order(self, picking_type, company, origin):
        data = super()._prepare_purchase_order(picking_type, company, origin)
        data.update({
            'building_id': self.building_id.id,
            'unit_id': self.unit_id.id,
            'contact_person': self.contact_person,
        })
        return data

    def make_purchase_order(self):
        # An existing RFQ picked in the wizard keeps its own Building / Unit /
        # Contact Person; only fill the ones it doesn't have yet.
        order = self.purchase_order_id
        if order:
            vals = {}
            if self.building_id and not order.building_id:
                vals['building_id'] = self.building_id.id
            if self.unit_id and not order.unit_id:
                vals['unit_id'] = self.unit_id.id
            if self.contact_person and not order.contact_person:
                vals['contact_person'] = self.contact_person
            if vals:
                order.write(vals)
        return super().make_purchase_order()
