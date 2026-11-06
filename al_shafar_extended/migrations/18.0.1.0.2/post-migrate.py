# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """property.details.measure_unit ("Area Measurement Unit") has had a
    Python-level default of 'sq_ft' since it was introduced, but that
    default only applies to records created afterwards through create()/
    the UI. Units created before the field existed (or imported straight
    into the DB) were left with measure_unit = NULL, which is why "Total
    Area" / "Usable Area" / "Unit Size" show a blank unit label ("0.00 /")
    on the Unit form's Area Calculations group for those older records.

    One-time backfill: any existing unit with no Area Measurement Unit
    set is assumed to be sq.ft (the field's own default), so we set it
    explicitly here rather than leaving it blank forever.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['property.details'].search([
        ('measure_unit', '=', False),
    ]).write({'measure_unit': 'sq_ft'})
