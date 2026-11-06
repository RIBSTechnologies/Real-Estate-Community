from odoo import models, fields, api

class DewaMeterReading(models.Model):
    _name = 'dewa.meter.reading.type'
    _description = "Dewa Meter Type"

    name = fields.Char('Meter Type')
    