from odoo import api, fields, models

# inherit account move line
class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    @api.depends('account_id', 'partner_id', 'product_id')
    def _compute_analytic_distribution(self):
        """ extend method to update analytic distribution in move line """
        super()._compute_analytic_distribution()
        ctx_tenancy = self.env.context.get('tenancy_id')
        for line in self:
            # Determine tenancy/property
            tenancy = (
                line.move_id.tenancy_property_id
                or ctx_tenancy
                or (line.move_id.maintenance_request_id.property_id
                    if line.move_id.maintenance_request_id else False)
            )

            # No tenancy or no analytic account continue
            analytic = tenancy and tenancy.analytic_account_id
            if not analytic:
                continue
            # Get existing distribution (as dict) or set new
            dist = dict(line.analytic_distribution or {})
            dist[analytic.id] = 100
            line.analytic_distribution = dist

    def _inverse_analytic_distribution(self):
        """ extend method to update analytic distribution for tax line """
        super()._inverse_analytic_distribution()
        for line in self:
            move = line._origin.move_id
            # Determine tenancy/property
            tenancy = (
                move.tenancy_property_id
                or (move.maintenance_request_id.property_id
                    if move.maintenance_request_id else False)
            )
            if not line.analytic_distribution and tenancy and tenancy.analytic_account_id:
                line.analytic_distribution = {tenancy.analytic_account_id.id: 100}
