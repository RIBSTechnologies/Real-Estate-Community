# -*- coding: utf-8 -*-

from odoo import models, fields


class PropertyProject(models.Model):
    _inherit = 'property.project'

    dm_number = fields.Char(string="DM Number", tracking=True)
    land_area = fields.Char(string="Land Area", tracking=True)
