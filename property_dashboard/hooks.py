# -*- coding: utf-8 -*-
"""Uninstall hook - put any relocated menu back at root level."""

import logging

_logger = logging.getLogger(__name__)


def uninstall_hook(cr_or_env, registry=None):
    """Works on Odoo 15/16 (cr, registry) and 17/18/19 (env)."""
    from odoo import api, SUPERUSER_ID
    if hasattr(cr_or_env, 'cr'):                 # Odoo 17+ passes an Environment
        env = cr_or_env
    else:                                        # Odoo 15/16 pass (cr, registry)
        env = api.Environment(cr_or_env, SUPERUSER_ID, {})
    try:
        restored = env['property.dashboard.menu.sync'].restore_root_menus()
        _logger.info("property_dashboard: restored %s menu(s) to root level.", restored)
    except Exception:
        _logger.warning("property_dashboard: menu restore failed on uninstall.",
                        exc_info=True)
