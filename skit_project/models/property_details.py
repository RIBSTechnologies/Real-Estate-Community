from odoo import api, fields, models, tools, _


class PropertyDetails(models.Model):
    _inherit = 'property.details'
    
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    
    def create(self,vals_list):
        """ Create analytic account for unit and update"""
        result = super(PropertyDetails,self).create(vals_list)
        for unit in result:
            # check project
            if unit.property_project_id:
                analytic_account = self.env['account.analytic.account'].sudo().create(
                    {'name':unit.name,'plan_id':unit.property_project_id.project_id.account_id.plan_id.id}
                    )
                unit.analytic_account_id = analytic_account.id
        return result