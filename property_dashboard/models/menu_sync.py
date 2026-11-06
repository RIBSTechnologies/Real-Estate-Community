# -*- coding: utf-8 -*-
"""
Menu placement helper for the Property Dashboard.

Two jobs
--------
1. RELOCATE  - any menu that sits at ROOT level (i.e. shows up as its own app
   tile on the Odoo home screen) and is named Statistics / Dashboard is moved
   underneath  Properties > Property.  The original parent / icon / sequence
   is remembered, so uninstalling this module puts everything back.

2. MIRROR    - if a "Statistics" menu already lives directly under the
   Properties app root, a copy of it is also created under
   Properties > Property, so you can reach it from both places.

Everything is matched by NAME, not by XML id, because rental_management is a
paid module whose XML ids change between releases.  Both operations are
idempotent - running them again on upgrade changes nothing.

Tuning without touching code
----------------------------
Settings > Technical > Parameters > System Parameters:

    property_dashboard.root_menu_names   Statistics,Dashboard,Property Dashboard
    property_dashboard.target_menu_names Property,Properties

Then run the server action "Property Dashboard: Fix Menu Placement"
(Settings > Technical > Actions > Server Actions) - no module upgrade needed.
"""

import json
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

APP_ROOT_XMLIDS = (
    'rental_management.main_menu_rental_management',
    'rental_management.rental_management_main_menu',
    'rental_management.property_main_menu',
)
APP_ROOT_NAMES = ('Properties', 'Property Management', 'Real Estate')

# Root-level menus that should not be their own app.
# NOTE: "Property Dashboard" / "Properties Dashboard" are deliberately absent
# here - that is THIS module's own dashboard, kept as a standalone top-level
# app on purpose (see menu_property_dashboard in dashboard_views.xml).
DEFAULT_ROOT_NAMES = ('Statistics', 'Statistic', 'Dashboard')
# Where they should go, searched as a child of the Properties app root.
DEFAULT_TARGET_NAMES = ('Property', 'Properties')
# Menus already under the app root that should ALSO appear under Property.
DEFAULT_MIRROR_NAMES = ('Statistics', 'Statistic')

# Never touch root menus that belong to these modules - they are real Odoo apps.
PROTECTED_MODULES = (
    'base', 'web', 'web_enterprise', 'board', 'mail', 'contacts', 'calendar',
    'spreadsheet', 'spreadsheet_dashboard', 'spreadsheet_dashboard_oca',
    'spreadsheet_dashboard_account', 'spreadsheet_dashboard_sale',
    'account', 'account_accountant', 'sale', 'sale_management', 'purchase',
    'stock', 'mrp', 'hr', 'hr_holidays', 'hr_expense', 'crm', 'project',
    'website', 'point_of_sale', 'documents', 'sign', 'helpdesk', 'im_livechat',
)

PARAM_MOVED = 'property_dashboard.relocated_menus'
PARAM_ROOT_NAMES = 'property_dashboard.root_menu_names'
PARAM_TARGET_NAMES = 'property_dashboard.target_menu_names'
PARAM_MIRROR_NAMES = 'property_dashboard.mirror_menu_names'
PARAM_OWN_PLACEMENT = 'property_dashboard.own_menus_under_property'
PARAM_DASH_NAMES = 'property_dashboard.dashboard_menu_names'
PARAM_DASH_ANCHOR = 'property_dashboard.dashboard_anchor_names'
PARAM_DASH_RENAME = 'property_dashboard.rename_own_dashboard'
PARAM_NATIVE_RENAME = 'property_dashboard.native_dashboard_new_name'
PARAM_MIRROR_ON = 'property_dashboard.mirror_statistics'
NATIVE_DASHBOARD_NAMES = ('Dashboard',)
DEFAULT_NATIVE_NEW_NAME = 'Statistics'

# Dashboard menus live on the Properties bar, right before "Contract".
# "Property Dashboard" is NOT in this list on purpose - it's kept as its own
# standalone top-level app, never pulled onto the Properties bar.
DEFAULT_DASH_NAMES = ('Dashboard',)
DEFAULT_DASH_ANCHOR = ('Contract', 'Contracts')
OWN_DASHBOARD_NAME = 'Property Dashboard'

# Menus this module ships, in the order they should appear under Property.
OWN_MENUS = (
    ('property_dashboard.menu_property_statistics', 1),
)

MAX_DEPTH = 4


class PropertyDashboardMenuSync(models.AbstractModel):
    _name = 'property.dashboard.menu.sync'
    _description = 'Property Dashboard - menu placement helper'

    # ================================================================== #
    # lookups
    # ================================================================== #
    def _menus(self, lang=None):
        menus = self.env['ir.ui.menu'].sudo()
        return menus.with_context(lang=lang) if lang else menus

    def _names_from_param(self, key, default):
        raw = self.env['ir.config_parameter'].sudo().get_str(key, False)
        if not raw:
            return tuple(default)
        return tuple(n.strip() for n in raw.split(',') if n.strip())

    def _app_root(self):
        """The Properties application root menu."""
        for xmlid in APP_ROOT_XMLIDS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                return menu.sudo()
        for lang in ('en_US', None):
            menu = self._menus(lang).search(
                [('parent_id', '=', False), ('name', 'in', APP_ROOT_NAMES)], limit=1)
            if menu:
                return menu.sudo()
        return self._menus().browse()

    def _find_child(self, root, names, exclude=None):
        for lang in ('en_US', None):
            for name in names:
                menu = self._menus(lang).search(
                    [('parent_id', '=', root.id), ('name', '=', name)], limit=1)
                if menu and (not exclude or menu.id != exclude.id):
                    return menu.sudo()
        return self._menus().browse()

    def _target_menu(self):
        """Properties > Property  (falls back to the app root itself)."""
        root = self._app_root()
        if not root:
            return self._menus().browse()
        target = self._find_child(root, self._names_from_param(
            PARAM_TARGET_NAMES, DEFAULT_TARGET_NAMES), exclude=root)
        return target or root

    def _is_protected(self, menu):
        """True for menus owned by Odoo itself - we must never move these."""
        return self._module_of(menu) in PROTECTED_MODULES

    def _remember(self, menu):
        """Snapshot a menu's placement so uninstall / revert can undo it."""
        moved = self._read_moved()
        key = str(menu.id)
        if key not in moved:
            moved[key] = {
                'parent_id': menu.parent_id.id or False,
                'web_icon': menu.web_icon or False,
                'sequence': menu.sequence,
                'name': menu.name,
            }
            self._write_moved(moved)

    def _module_of(self, menu):
        rec = self.env['ir.model.data'].sudo().search(
            [('model', '=', 'ir.ui.menu'), ('res_id', '=', menu.id)], limit=1)
        return rec.module if rec else ''

    # ================================================================== #
    # 1) RELOCATE root-level menus
    # ================================================================== #
    def _root_candidates(self):
        names = self._names_from_param(PARAM_ROOT_NAMES, DEFAULT_ROOT_NAMES)
        app_root = self._app_root()
        found = self._menus().browse()
        for lang in ('en_US', None):
            found |= self._menus(lang).search(
                [('parent_id', '=', False), ('name', 'in', list(names))])
        out = self._menus().browse()
        for menu in found:
            if app_root and menu.id == app_root.id:
                continue                                   # never move the app itself
            module = self._module_of(menu)
            if module in PROTECTED_MODULES:
                _logger.info("property_dashboard: skipping root menu '%s' (module %s "
                             "is protected).", menu.name, module)
                continue
            out |= menu
        return out

    def _read_moved(self):
        raw = self.env['ir.config_parameter'].sudo().get_str(PARAM_MOVED, False)
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _write_moved(self, data):
        self.env['ir.config_parameter'].sudo().set_str(PARAM_MOVED, json.dumps(data))

    @api.model
    def relocate_root_menus(self):
        """Move root-level Statistics/Dashboard menus under Properties > Property."""
        target = self._target_menu()
        if not target:
            _logger.warning("property_dashboard: Properties app root not found - "
                            "root menus left untouched.")
            return 0

        count = 0
        for menu in self._root_candidates():
            self._remember(menu)
            menu.write({
                'parent_id': target.id,
                'web_icon': False,                         # app tile icon is meaningless now
                'sequence': menu.sequence or 20,
            })
            count += 1
            _logger.info("property_dashboard: moved root menu '%s' under '%s'.",
                         menu.name, target.complete_name)

        if count:
            self._clear_menu_cache()
        return count

    @api.model
    def restore_root_menus(self):
        """Called by the uninstall hook - put the menus back where they were."""
        moved = self._read_moved()
        if not moved:
            return 0
        Menu = self._menus()
        count = 0
        for menu_id, vals in moved.items():
            menu = Menu.browse(int(menu_id)).exists()
            if not menu:
                continue
            menu.write({
                'parent_id': vals.get('parent_id') or False,
                'web_icon': vals.get('web_icon') or menu.web_icon or False,
                'sequence': vals.get('sequence') or 10,
                'name': vals.get('name') or menu.name,
            })
            count += 1
        self.env['ir.config_parameter'].sudo().set_str(PARAM_MOVED, '')
        self._clear_menu_cache()
        return count

    # ================================================================== #
    # 2) MIRROR a Statistics menu that lives under the app root
    # ================================================================== #
    def _register_xmlid(self, menu):
        """Attach generated menus to this module so uninstall removes them."""
        IMD = self.env['ir.model.data'].sudo()
        key = 'menu_mirror_%s' % menu.id
        if not IMD.search([('module', '=', 'property_dashboard'), ('name', '=', key)], limit=1):
            IMD.create({
                'name': key,
                'module': 'property_dashboard',
                'model': 'ir.ui.menu',
                'res_id': menu.id,
                'noupdate': True,
            })

    def _mirror_tree(self, source, parent, depth=0):
        if depth > MAX_DEPTH:
            return
        Menu = self._menus()
        vals = {
            'name': source.name,
            'parent_id': parent.id,
            'sequence': source.sequence,
            'group_ids': [(6, 0, source.group_ids.ids)],
            'active': True,
        }
        if source.action:
            vals['action'] = '%s,%s' % (source.action._name, source.action.id)

        target = Menu.search([('parent_id', '=', parent.id),
                              ('name', '=', source.name),
                              ('active', 'in', (True, False))], limit=1)
        if target and self._module_of(target) == 'property_dashboard':
            target = Menu.browse()          # never clobber our own client action
        if target:
            target.write(vals)
        else:
            target = Menu.create(vals)
            self._register_xmlid(target)

        for child in source.child_id:
            self._mirror_tree(child, target, depth + 1)

    @api.model
    def mirror_statistics_into_property(self):
        if self.env['ir.config_parameter'].sudo().get_str(
                PARAM_MIRROR_ON, '0').strip() in ('0', 'false', 'False'):
            return False
        root = self._app_root()
        if not root:
            return False
        target = self._target_menu()
        if not target or target.id == root.id:
            return False
        source = self._find_child(root, self._names_from_param(
            PARAM_MIRROR_NAMES, DEFAULT_MIRROR_NAMES))
        if not source or source.id == target.id:
            return False
        self._mirror_tree(source, target)
        self._clear_menu_cache()
        _logger.info("property_dashboard: mirrored '%s' under '%s'.",
                     source.name, target.complete_name)
        return True

    # ================================================================== #
    # entry point used by data XML and the server action
    # ================================================================== #
    # ================================================================== #
    # 3) place THIS module's own menus under Property
    # ================================================================== #
    @api.model
    def place_own_menus(self):
        """Move our Statistics / Dashboard menus under Properties > Property.

        Set the system parameter property_dashboard.own_menus_under_property
        to 0 if you would rather keep them straight on the Properties bar.
        """
        param = self.env['ir.config_parameter'].sudo().get_str(PARAM_OWN_PLACEMENT, '1')
        if param.strip() in ('0', 'false', 'False'):
            return 0
        target = self._target_menu()
        root = self._app_root()
        if not target or (root and target.id == root.id):
            return 0                                # no "Property" menu -> leave as-is
        moved = 0
        for xmlid, sequence in OWN_MENUS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            menu.sudo().write({'parent_id': target.id, 'sequence': sequence,
                               'web_icon': False})
            moved += 1
        if moved:
            self._clear_menu_cache()
        return moved

    # ================================================================== #
    # 4) native Statistics wins over our rebuilt one
    # ================================================================== #
    @api.model
    def reconcile_statistics(self):
        """If rental_management ships its own Statistics menu, use that one and
        hide the rebuilt copy, so the user never sees two 'Statistics' entries.
        """
        ours = self.env.ref('property_dashboard.menu_property_statistics',
                            raise_if_not_found=False)
        root = self._app_root()
        if not root:
            return False
        native = self._find_child(
            root, self._names_from_param(PARAM_MIRROR_NAMES, DEFAULT_MIRROR_NAMES),
            exclude=ours)
        if not native:
            # nothing native -> make sure our rebuilt page is visible
            if ours and not ours.active:
                ours.sudo().write({'active': True})
            return False
        if ours:
            ours.sudo().write({'active': False})
            _logger.info("property_dashboard: native Statistics menu found, "
                         "the rebuilt copy has been archived.")
        self.mirror_statistics_into_property()
        return True

    # ================================================================== #
    # 5) dashboards sit on the Properties bar, just before "Contract"
    # ================================================================== #
    def _dashboard_menus(self):
        """Every Dashboard-ish menu, wherever it currently hangs."""
        names = list(self._names_from_param(PARAM_DASH_NAMES, DEFAULT_DASH_NAMES))
        root, target = self._app_root(), self._target_menu()
        scopes = [m.id for m in (root, target) if m] + [False]
        found = self._menus().browse()
        for lang in ('en_US', None):
            found |= self._menus(lang).search(
                [('parent_id', 'in', scopes), ('name', 'in', names)])
        ours = self.env.ref('property_dashboard.menu_property_dashboard',
                            raise_if_not_found=False)
        if root:
            found -= root                       # never move the app itself
        if ours:
            found -= ours                       # our own dashboard stays standalone
        # THE fix: Odoo's own "Dashboards" app matched here before and got
        # dragged onto the Properties bar. Base menus are off limits.
        safe = self._menus().browse()
        for menu in found:
            if self._is_protected(menu):
                _logger.info("property_dashboard: leaving base menu '%s' (module %s) "
                             "alone.", menu.name, self._module_of(menu))
                continue
            safe |= menu
        return safe

    def _rename_own_dashboard(self, dashboards):
        """Two menus both called "Dashboard" is unusable - label ours clearly."""
        if self.env['ir.config_parameter'].sudo().get_str(
                PARAM_DASH_RENAME, '1').strip() in ('0', 'false', 'False'):
            return
        ours = self.env.ref('property_dashboard.menu_property_dashboard',
                            raise_if_not_found=False)
        if not ours:
            return
        others = dashboards - ours
        if others and ours.name != OWN_DASHBOARD_NAME:
            ours.sudo().write({'name': OWN_DASHBOARD_NAME})
            _logger.info("property_dashboard: renamed our menu to '%s' to avoid a "
                         "duplicate 'Dashboard' entry.", OWN_DASHBOARD_NAME)

    @api.model
    def place_dashboards_before_contract(self):
        """Pull the dashboards onto the Properties bar and renumber the whole bar
        so they land immediately before the Contract menu."""
        root = self._app_root()
        if not root:
            return 0
        movers = self._dashboard_menus()
        if not movers:
            return 0

        self._rename_own_dashboard(movers)
        ours = self.env.ref('property_dashboard.menu_property_dashboard',
                            raise_if_not_found=False)
        for menu in movers:
            self._remember(menu)
            vals = {'parent_id': root.id}
            if ours and menu.id == ours.id:
                vals['web_icon'] = False        # only clear OUR icon
            menu.sudo().write(vals)
        self._clear_menu_cache()

        children = self._menus().search([('parent_id', '=', root.id)],
                                        order='sequence, id')
        anchor_names = self._names_from_param(PARAM_DASH_ANCHOR, DEFAULT_DASH_ANCHOR)
        anchor = self._menus().browse()
        for name in anchor_names:                       # first match wins
            match = children.filtered(lambda m, n=name: m.name == n)
            if match:
                anchor = match[0]
                break

        rest = [m for m in children if m.id not in movers.ids]
        ordered = []
        placed = False
        for menu in rest:
            if anchor and menu.id == anchor.id and not placed:
                ordered += list(movers)
                placed = True
            ordered.append(menu)
        if not placed:
            ordered += list(movers)                     # no anchor -> append

        for index, menu in enumerate(ordered, start=1):
            if menu.sequence != index * 10:
                menu.sudo().write({'sequence': index * 10})

        self._clear_menu_cache()
        _logger.info("property_dashboard: placed %s dashboard menu(s) before '%s'.",
                     len(movers), anchor.name if anchor else 'end of bar')
        return len(movers)

    # ================================================================== #
    # 0) SAFETY NET - put Odoo's own apps back at root level
    # ================================================================== #
    @api.model
    def restore_protected_menus(self):
        """Undo any earlier mistake where a base Odoo app (Dashboards, Board,
        Spreadsheet ...) was pulled under the Properties app.  Base menus belong
        at root level, full stop."""
        root = self._app_root()
        if not root:
            return 0
        scopes = [root.id]
        target = self._target_menu()
        if target and target.id != root.id:
            scopes.append(target.id)

        moved = self._read_moved()
        restored = 0
        for menu in self._menus().search([('parent_id', 'in', scopes)]):
            module = self._module_of(menu)
            if module not in PROTECTED_MODULES:
                continue
            saved = moved.pop(str(menu.id), {})
            icon = saved.get('web_icon') or menu.web_icon
            if not icon and module:
                # Odoo's own convention for app tile icons
                icon = '%s,static/description/icon.png' % module
            menu.sudo().write({
                'parent_id': saved.get('parent_id') or False,
                'web_icon': icon or False,
                'sequence': saved.get('sequence') or menu.sequence or 10,
            })
            restored += 1
            _logger.info("property_dashboard: restored base menu '%s' (module %s) "
                         "back to root level.", menu.name, module)

        if restored:
            self._write_moved(moved)
            self._clear_menu_cache()
        return restored

    # ================================================================== #
    # 6) label the native rental_management dashboard as "Statistics"
    # ================================================================== #
    @api.model
    def rename_native_dashboard(self):
        """The rental_management menu labelled "Dashboard" actually opens the
        Rent Contract Statistics page, so give it an honest name.

        Set property_dashboard.native_dashboard_new_name to an empty string to
        turn this off.
        """
        new_name = self.env['ir.config_parameter'].sudo().get_str(
            PARAM_NATIVE_RENAME, DEFAULT_NATIVE_NEW_NAME).strip()
        if not new_name:
            return 0
        root = self._app_root()
        if not root:
            return 0
        ours = self.env.ref('property_dashboard.menu_property_dashboard',
                            raise_if_not_found=False)
        scopes = [root.id]
        target = self._target_menu()
        if target and target.id != root.id:
            scopes.append(target.id)

        renamed = 0
        for lang in ('en_US', None):
            for menu in self._menus(lang).search(
                    [('parent_id', 'in', scopes),
                     ('name', 'in', list(NATIVE_DASHBOARD_NAMES))]):
                if ours and menu.id == ours.id:
                    continue                      # that one is ours
                if self._is_protected(menu):
                    continue                      # never rename a base app
                self._remember(menu)
                menu.sudo().write({'name': new_name})
                renamed += 1
                _logger.info("property_dashboard: renamed native menu 'Dashboard' "
                             "-> '%s'.", new_name)
        if renamed:
            self._clear_menu_cache()
        return renamed

    # ================================================================== #
    @api.model
    def sync_menus(self):
        self.restore_protected_menus()        # always undo base-app damage first
        moved = self.relocate_root_menus()
        self.place_own_menus()
        self.reconcile_statistics()
        self.place_dashboards_before_contract()
        self.rename_native_dashboard()        # last: "Dashboard" -> "Statistics"
        self._clear_menu_cache()
        return moved

    def _clear_menu_cache(self):
        try:                                   # Odoo 17+
            self.env.transaction.invalidate_ormcache()
        except AttributeError:                 # Odoo 15/16
            self.env['ir.ui.menu'].clear_caches()

    # ================================================================== #
    # reporting - feeds the "Check" panel on the dashboard
    # ================================================================== #
    @api.model
    def get_menu_report(self):
        root = self._app_root()
        target = self._target_menu()
        rows = [{
            'label': 'Properties app root',
            'ok': bool(root),
            'detail': root.complete_name if root else 'NOT FOUND',
        }, {
            'label': 'Relocation target',
            'ok': bool(target),
            'detail': target.complete_name if target else 'NOT FOUND',
        }]
        roots = self._menus(lang='en_US').search([('parent_id', '=', False)], order='name')
        rows.append({
            'label': 'Root-level menus (app tiles)',
            'ok': True,
            'detail': ', '.join('%s [%s]' % (m.name, self._module_of(m) or '?') for m in roots),
        })
        rows.append({
            'label': 'Menus relocated by this module',
            'ok': True,
            'detail': ', '.join(v.get('name', '') for v in self._read_moved().values()) or 'none',
        })
        return rows
