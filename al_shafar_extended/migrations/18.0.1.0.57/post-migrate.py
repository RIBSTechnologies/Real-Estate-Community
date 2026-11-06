# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Re-run the analytic cleanup so every unit gets its own Units account:
    units without a building, and units that shared one account because they
    have the same Property Code or name, were left without one. Idempotent -
    see AccountAnalyticAccount._cleanup_al_shafar_analytic."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.analytic.account']._cleanup_al_shafar_analytic()
