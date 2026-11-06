# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResPartnerUserTypeTag(models.Model):
    """Multi-select companion to res.partner.user_type. Kept as a separate
    field/model instead of converting user_type itself to Many2many, since
    user_type is used as a single value in many equality domains and direct
    assignments across rental_management/ribs_real_estate (e.g.
    [('user_type', '=', 'customer')], self.customer_id.user_type = 'customer')
    that would otherwise break.
    """
    _name = 'res.partner.user.type.tag'
    _description = 'Partner User Type Tag'

    name = fields.Char(required=True)
    code = fields.Char(required=True)

    _code_uniq = models.Constraint(
        'unique(code)',
        'A user type tag with this code already exists.',
    )


class ResPartnerVendorType(models.Model):
    _inherit = 'res.partner'

    user_type = fields.Selection(selection_add=[('vendor', 'Vendor')])
    additional_user_type_ids = fields.Many2many(
        'res.partner.user.type.tag', string='Additional User Types',
        help="Tag this contact with more than one role (e.g. Vendor and Owner) "
             "without changing its primary User Type above.")

    def _is_tagged_vendor(self):
        self.ensure_one()
        return self.user_type == 'vendor' or 'vendor' in self.additional_user_type_ids.mapped('code')

    @api.onchange('user_type', 'additional_user_type_ids')
    def _onchange_user_type_set_supplier_rank(self):
        if self._is_tagged_vendor() and not self.supplier_rank:
            self.supplier_rank = 1

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        for partner in partners:
            if partner._is_tagged_vendor() and not partner.supplier_rank:
                partner.supplier_rank = 1
        return partners

    def write(self, vals):
        res = super().write(vals)
        if 'user_type' in vals or 'additional_user_type_ids' in vals:
            for partner in self:
                if partner._is_tagged_vendor() and not partner.supplier_rank:
                    partner.supplier_rank = 1
        return res
