# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """maintenance.request.ticket_type is new and stored. Its first compute
    runs while this module loads - before tenant_portal_api (which depends on
    it) adds tp_source - so Tenant Portal tickets would land in 'Directly
    Created'. Recompute once every module is loaded."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    requests = env['maintenance.request'].with_context(active_test=False).search([])
    env.add_to_compute(requests._fields['ticket_type'], requests)
    env.flush_all()
