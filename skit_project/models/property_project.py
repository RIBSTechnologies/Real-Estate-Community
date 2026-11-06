from odoo import api, fields, models, _


class PropertyProject(models.Model):

    _inherit = "property.project"
    
    project_id = fields.Many2one('project.project', string='Project')
    
    def create(self, vals_list):
        res = super(PropertyProject, self).create(vals_list)
        for rec in res:
            analytic_plan = self.env['account.analytic.plan'].sudo().create({'name':rec.name})
            analytic_account = self.env['account.analytic.account'].sudo().create({'name':rec.name,'plan_id':analytic_plan.id})
            rec.project_id = self.env['project.project'].sudo().create({'name':rec.name,
                                                       'account_id':analytic_account.id}).id
        return res
    
    def write(self, vals):
        """ after duplicate to write the rename"""
        res = super(PropertyProject, self).write(vals)
        for rec in self:
            if 'name' in vals:
                rename = vals.get('name')
                if rec.project_id and rec.project_id.account_id.plan_id:
                    rec.project_id.account_id.plan_id.sudo().write({'name': rename})
                if rec.project_id and rec.project_id.account_id:
                    rec.project_id.account_id.sudo().write({'name': rename})
                if rec.project_id:
                    rec.project_id.sudo().write({'name': rename})
        return res
    
    