# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class ProjectProject(models.Model):
    _inherit = 'project.project'
    

    def _get_analytic_distribution(self):
        """
            Override: Assign analytic account automatically when journal items 
            are created from contracts or properties.
            Returns:
                dict: {analytic_account_id: percentage}
        """
        ctx = self.env.context
        distribution = {}

        # Extract context values for model and active record(s)
        active_model = ctx.get('active_model')
        active_ids = ctx.get('active_ids')
        tenancy_id = ctx.get('tenancy_id')
        # PDC payment entry creation from deposit and done action
        if tenancy_id and tenancy_id.analytic_account_id:
            distribution = {
                    tenancy_id.analytic_account_id.id: 100
                }
        # Journal entry created from a Tenancy (contract)
        # If the tenancy has a linked property and that property has
        # an analytic account, apply it with 100% distribution.
        elif active_model == 'tenancy.details' and active_ids:
            tenancy = self.env['tenancy.details'].sudo().browse(active_ids)
            if tenancy.property_id.analytic_account_id:
                distribution = {
                    tenancy.property_id.analytic_account_id.id: 100
                }

        # Journal entry created directly from Property
        # If the property has an analytic account, apply it.
        elif active_model == 'property.details' and active_ids:
            prop = self.env['property.details'].sudo().browse(active_ids)
            if prop.analytic_account_id:
                distribution = {
                    prop.analytic_account_id.id: 100
                }

        return distribution or super()._get_analytic_distribution()
