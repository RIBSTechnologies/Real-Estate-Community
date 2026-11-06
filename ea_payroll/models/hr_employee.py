
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"
    _description = "Employee"

    slip_ids = fields.One2many(
        "hr.payslip", "employee_id", string="Payslips", readonly=True
    )
    payslip_count = fields.Integer(
        compute="_compute_payslip_count",
        groups="ea_payroll.group_payroll_user",
    )
    contract_id = fields.Many2one(
        "hr.version",
        related="version_id",
        string="Current Contract",
        readonly=False,
    )
    contract_ids = fields.One2many(
        "hr.version",
        related="version_ids",
        string="Employee Contracts",
        readonly=False,
    )
    bank_account_id = fields.Many2one(
        "res.partner.bank",
        related="primary_bank_account_id",
        string="Bank Account",
        readonly=False,
    )

    def _compute_payslip_count(self):
        for employee in self:
            employee.payslip_count = len(employee.slip_ids)
