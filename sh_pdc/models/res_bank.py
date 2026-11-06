# -*- coding: utf-8 -*-
# Odoo 20 removed the res.bank directory from base (bank names now live on
# res.partner.bank as plain text). PDC cheques still need a pick-list of
# remitter banks, so the model is kept here with the fields that were used.
from odoo import api, fields, models


class ResBank(models.Model):
    _name = 'res.bank'
    _description = 'Bank'
    _order = 'name, id'
    _rec_names_search = ('name', 'bic')

    name = fields.Char(required=True)
    bic = fields.Char('Bank Identifier Code', index=True, help="Sometimes called BIC or Swift.")
    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char()
    city = fields.Char()
    state = fields.Many2one('res.country.state', 'Fed. State', domain="[('country_id', '=?', country)]")
    country = fields.Many2one('res.country')
    email = fields.Char()
    phone = fields.Char()
    active = fields.Boolean(default=True)

    @api.depends('bic')
    def _compute_display_name(self):
        for bank in self:
            bank.display_name = bank.name + (bank.bic and (' - ' + bank.bic) or '')

    @api.onchange('country')
    def _onchange_country_id(self):
        if self.country and self.country != self.state.country_id:
            self.state = False

    @api.onchange('state')
    def _onchange_state(self):
        if self.state.country_id:
            self.country = self.state.country_id
