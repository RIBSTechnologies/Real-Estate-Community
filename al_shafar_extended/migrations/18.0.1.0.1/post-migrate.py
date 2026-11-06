# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """pdc.wizard.tenancy_id moved from a related field on invoice_id (never
    populated for cheques created via the contract payment schedule) to a
    compute reading invoice_id/invoice_ids. Existing rows keep their old
    stored value (False) until forced to recompute once here."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['pdc.wizard'].search([])._compute_tenancy_id()
