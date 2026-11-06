from odoo import _, models
from odoo.exceptions import UserError


def _open_portal_wizard(env, partner):
    """Open Odoo's standard "Grant portal access" wizard for one partner.
    The tenant then logs in to the standard customer portal (/my), where
    rental_management / ribs_real_estate already show their contracts,
    maintenance requests and documents."""
    return env['portal.wizard'].with_context(
        default_partner_ids=partner.ids)._action_open_modal_new()


class TenancyDetails(models.Model):
    _inherit = 'tenancy.details'

    def action_open_portal_access(self):
        self.ensure_one()
        if not self.tenancy_id:
            raise UserError(_("Set the tenant on this contract first."))
        return _open_portal_wizard(self.env, self.tenancy_id)


class PropertyVendor(models.Model):
    _inherit = 'property.vendor'

    def action_open_portal_access(self):
        self.ensure_one()
        if not self.customer_id:
            raise UserError(_("Set the customer on this contract first."))
        return _open_portal_wizard(self.env, self.customer_id)


class PortalWizard(models.TransientModel):
    _inherit = 'portal.wizard'

    def _action_open_modal_new(self):
        # portal.wizard.user lines must exist before their buttons can be used,
        # so create the wizard first (same as portal.wizard.action_open_wizard)
        return self.create({})._action_open_modal()
