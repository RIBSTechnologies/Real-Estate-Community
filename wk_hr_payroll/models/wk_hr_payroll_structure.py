# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval


class WkHrPayrollStructure(models.Model):
    """
    Salary structure used to defined
    - Basic
    - Allowances
    - Deductions
    """
    _name = 'wk.hr.payroll.structure'
    _description = 'Salary Structure'

    @api.model
    def _get_parent(self):
        return self.env.ref('wk_hr_payroll.structure_base', False)

    name = fields.Char(required=True)
    code = fields.Char(string='Reference', required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True,
        copy=False, default=lambda self: self.env.company)
    note = fields.Text(string='Description')
    parent_id = fields.Many2one('wk.hr.payroll.structure', string='Parent', default=_get_parent)
    children_ids = fields.One2many('wk.hr.payroll.structure', 'parent_id',
                                   string='Children', copy=True)
    rule_ids = fields.Many2many('wk.hr.salary.rule', 'hr_structure_salary_rule_rel',
                                'struct_id', 'rule_id', string='Salary Rules')
    ytd_computation = fields.Boolean(default=False, string='Year to Date Computation',
        help="Adds a column in the payslip that shows the accumulated amount paid for different rules during the year")
    default_struct_id = fields.Many2one('wk.hr.payroll.structure', string="Pay Structure")
    version_properties_definition = fields.PropertiesDefinition("Version Properties Definition")
    payslip_properties_definition = fields.PropertiesDefinition("Payslip Properties Definition")
    use_worked_day_lines = fields.Boolean(default=True, help="Worked days won't be computed/displayed in payslips.")
    

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError(
                _('You cannot create a recursive salary structure.'))

    @api.model
    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {}, code=_("%s (copy)") % (self.code))
        return super(WkHrPayrollStructure, self).copy(default)

    def get_all_rules(self):
        """
        @return: returns a list of tuple (id, sequence) of rules that are maybe to apply
        """
        all_rules = []
        for struct in self:
            all_rules += struct.rule_ids._recursive_search_of_rules()
        return all_rules

    def _get_parent_structure(self):
        parent = self.mapped('parent_id')
        if parent:
            parent = parent._get_parent_structure()
        return parent + self


class WkHrContributionRegister(models.Model):
    _name = 'wk.hr.contribution.register'
    _description = 'Contribution Register'

    company_id = fields.Many2one('res.company',string='Company',
        default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', string='Partner')
    name = fields.Char(required=True)
    register_line_ids = fields.One2many('wk.hr.payslip.line', 'register_id',
                                        string='Register Line', readonly=True)
    note = fields.Text(string='Description')
