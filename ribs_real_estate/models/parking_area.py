from odoo import api, models, fields

class parkingSlots(models.Model):
    _name = 'parking.slots'
    _rec_name = 'parking_numbers'
    _description = "Parking Slots"

    parking_numbers = fields.Char(string='Parking Numbers', store=True)
    project_id = fields.Many2one('property.project', string='Project', required=True, store=True)

    _parking_numbers_uniq = models.Constraint(
        'unique(parking_numbers)',
        'Parking Number should be unique',
    )

class ParkingArea(models.Model):
    _name = 'parking.allocation'
    _rec_name = 'project_name'
    _description = "Parking Allocation"

    project_id = fields.Many2one('property.project', string='Project', required=True, store=True,
                                 domain=lambda self: [('id', 'not in', self._get_used_project_ids())])
    parking_ids = fields.Many2many('parking.slots', string='Parking Slots')
    project_name = fields.Char(related="project_id.name", string='Project Name')

    @api.model
    def model_create_multi(self, vals):
        res = super(ParkingArea, self).create(vals)
        if res.parking_ids and res.project_id:
            res.parking_ids.write({'project_id': res.project_id.id})
        return res

    def write(self, vals):
        res = super(ParkingArea, self).write(vals)
        project_id = vals.get('project_id', self.project_id.id)
        if 'parking_ids' in vals or 'project_id' in vals:
            for record in self:
                if record.parking_ids:
                    record.parking_ids.write({'project_id': project_id})
        return res

    @api.model
    def _get_used_project_ids(self):
        return self.search([]).mapped('project_id.id')






