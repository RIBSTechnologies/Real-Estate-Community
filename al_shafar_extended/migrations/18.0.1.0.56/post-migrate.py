# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Analytic accounts reduced to 5 plans (Building, Units, AR Type, Cost
    Center, Sub Cost Center): unit accounts renamed to their Property Code,
    stray Building/Units accounts and every Property Type / Sub Type account
    deleted (or archived when already used). See
    AccountAnalyticAccount._cleanup_al_shafar_analytic."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.analytic.account']._cleanup_al_shafar_analytic()
