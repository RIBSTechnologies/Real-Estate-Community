from odoo import api, fields, models, _

class UnitSequence(models.TransientModel):  
    _name = 'unit.sequence'
    _description = 'Unit Sequence Creation'


    unit_creation_id = fields.Many2one('unit.creation', string="Unit Creation")
    unit_name = fields.Char(string="Unit Name")
    parking_name = fields.Char(string="Parking Name")
    property_type = fields.Selection([("commercial", "Commercial"),
                                      ("residential", "Residential"),
                                      ("office", "Office"),
                                      ("industrial", "Industrial"),
                                      ("land", "Land"),],
                                     string="Property Type",
                                     required=True)
    property_subtype_id = fields.Many2one('property.sub.type',
                                          string="Property Sub Type",
                                          required=False)
    bhk = fields.Integer(string="BHK",default=1)
    floor = fields.Integer(string="Floor", default=1)

    @api.onchange('property_type')
    def onchange_property_type(self):
        for rec in self:
            rec.property_subtype_id = False




    