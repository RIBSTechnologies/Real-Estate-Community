# -*- coding: utf-8 -*-

# Klystron Global LLC
# Copyright (C) Klystron Global LLC
# All Rights Reserved
# https://www.klystronglobal.com/


from odoo import models, api, tools


class Menu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    @api.ormcache('frozenset(self.env.user._get_group_ids())', 'self.env.uid', 'debug')
    def _visible_menu_ids(self, debug=False):
        menus = super(Menu, self)._visible_menu_ids(debug)
        if self.env.user.hide_menu_access_ids and not self.env.user.has_group('base.group_system'):
            return menus - frozenset(self.env.user.hide_menu_access_ids.ids)
        return menus
