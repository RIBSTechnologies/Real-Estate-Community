# -*- coding: utf-8 -*-

from odoo import models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def fetch_online_sync_favorite_institutions(self):
        """The Accounting dashboard calls this once per bank journal card
        to show bank logos in its "Connect your bank" box, and each call
        goes out to production.odoofin.com. Bank feeds aren't used here and
        those calls (up to 60s each, ~18 in parallel) tied up the server
        and made Accounting / PDC menus load forever. Return no logos
        straight away; the "Connect" button itself still works.
        Set system parameter al_shafar_extended.bank_sync_logos = True to
        bring the original behaviour back."""
        enabled = self.env['ir.config_parameter'].sudo().get_str(
            'al_shafar_extended.bank_sync_logos', False)
        if enabled in ('1', 'True', 'true'):
            return super().fetch_online_sync_favorite_institutions()
        return []
