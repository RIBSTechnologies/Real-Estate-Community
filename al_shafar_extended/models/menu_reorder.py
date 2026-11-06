# -*- coding: utf-8 -*-
import logging

from odoo import models, api

_logger = logging.getLogger(__name__)

# Desired left-to-right order for the "Properties" app's top-level menu bar.
# Matched by exact NAME, not xmlid - these menus are contributed by several
# different modules (rental_management, ribs_real_estate, property_dashboard)
# with no single stable id shared between them. property_dashboard's own
# models/menu_sync.py uses the same name-matching approach for the same
# reason, so this stays consistent with how this menu bar is already managed.
_MENU_SEQUENCE = {
    'Statistics': 10,
    'Property': 20,
    'Contract': 30,
    'Contract Payment Summary': 40,
    'PDC Cheque Payment Summary': 50,
    'Configurations': 60,
    'Maintenances': 70,
    'Users': 80,
    'Reports': 90,
}

# These are two menu items ribs_real_estate created AS CHILDREN OF THE
# PROPERTIES APP ITSELF (rental_management.menu_tenancy_details renamed to
# "Accounting", and ribs_real_estate.menu_crm) - shortcuts into
# accounting/CRM functionality from inside Properties. They are NOT the
# real standalone Accounting/CRM apps, which are separate ir.ui.menu records
# with their own different ids/parents living entirely outside this tree.
# _ensure_properties_menu_order below only ever searches
# parent_id = <the Properties app's own id>, so this can never reach those
# other records - archiving these two only removes these two shortcut
# entries from the Properties bar; the real apps and all their own menus,
# data, and access are completely untouched.
_MENU_HIDE = {'Accounting', 'CRM'}


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _ensure_properties_menu_order(self):
        """
        Idempotent: reorders/hides the named items directly under the
        "Properties" app root. Called via a <function> tag in
        data/menu_reorder.xml, which is NOT gated by noupdate, so this
        self-heals on every module install/upgrade, on every environment.
        """
        # active_test=False: also see already-archived menus, so re-running
        # this is a true no-op instead of re-hiding something already hidden.
        # ir.ui.menu.full_list=True: ir.ui.menu.search_fetch() (core, see
        # addons/base/models/ir_ui_menu.py) hard-codes a group-visibility
        # filter that applies even to the technical/install-time superuser -
        # it checks self.env.user.group_ids literally, and e.g. "Accounting"
        # is restricted to the Manager/Officer groups the install-time user
        # isn't a member of, so without this flag the search below would
        # silently never find it. This is the exact context flag core's own
        # _visible_menu_ids() uses to bypass that filter.
        Menu = self.sudo().with_context(active_test=False, **{'ir.ui.menu.full_list': True})
        root = Menu.search([('parent_id', '=', False), ('name', '=', 'Properties')], limit=1)
        if not root:
            _logger.warning("al_shafar_extended: 'Properties' app root menu not found, skipping menu reorder")
            return

        children = Menu.search([('parent_id', '=', root.id)])
        for menu in children:
            assert menu.parent_id.id == root.id  # only ever the Properties app's own children, never anything else
            if menu.name in _MENU_HIDE:
                if menu.active:
                    menu.write({'active': False})
                    _logger.info("al_shafar_extended: hid Properties menu '%s' (id=%s)", menu.name, menu.id)
            elif menu.name in _MENU_SEQUENCE:
                seq = _MENU_SEQUENCE[menu.name]
                if menu.sequence != seq or not menu.active:
                    menu.write({'sequence': seq, 'active': True})
                    _logger.info(
                        "al_shafar_extended: reordered Properties menu '%s' -> sequence=%s",
                        menu.name, seq)
