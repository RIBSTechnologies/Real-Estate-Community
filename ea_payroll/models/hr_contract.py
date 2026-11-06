from odoo import api, fields, models


class HrContract(models.Model):
    """
    Employee contract based on the visa, work permits
    allows to configure different Salary structure
    """

    _inherit = "hr.version"
    _description = "Employee Contract"

    @api.model_create_multi
    def create(self, vals_list):
        records = self.env["hr.version"]
        to_create_vals = []
        for vals in vals_list:
            employee_id = vals.get("employee_id")
            date_ver = vals.get("date_version") or fields.Date.today()
            if isinstance(date_ver, str):
                date_ver = fields.Date.to_date(date_ver)
            if employee_id:
                existing = self.search(
                    [
                        ("employee_id", "=", employee_id),
                        ("date_version", "=", date_ver),
                        ("active", "=", True),
                    ],
                    limit=1,
                )
                if existing:
                    if "date_start" in vals and "contract_date_start" not in vals:
                        vals["contract_date_start"] = vals["date_start"]
                    if "date_end" in vals and "contract_date_end" not in vals:
                        vals["contract_date_end"] = vals["date_end"]
                    existing.write(vals)
                    records |= existing
                    continue
            if "date_start" in vals and "contract_date_start" not in vals:
                vals["contract_date_start"] = vals["date_start"]
            if "date_end" in vals and "contract_date_end" not in vals:
                vals["contract_date_end"] = vals["date_end"]
            to_create_vals.append(vals)
        if to_create_vals:
            records |= super().create(to_create_vals)
        return records

    def write(self, vals):
        if "date_start" in vals and "contract_date_start" not in vals:
            vals["contract_date_start"] = vals["date_start"]
        if "date_end" in vals and "contract_date_end" not in vals:
            vals["contract_date_end"] = vals["date_end"]
        return super().write(vals)

    struct_id = fields.Many2one("hr.payroll.structure", string="Salary Structure")
    schedule_pay = fields.Selection(
        [
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("semi-annually", "Semi-annually"),
            ("annually", "Annually"),
            ("weekly", "Weekly"),
            ("bi-weekly", "Bi-weekly"),
            ("bi-monthly", "Bi-monthly"),
        ],
        string="Scheduled Pay",
        index=True,
        default="monthly",
        help="Defines the frequency of the wage payment.",
    )
    resource_calendar_id = fields.Many2one(
        "resource.calendar",
        default=lambda self: self.env.company.resource_calendar_id,
        required=True,
        help="Employee's working schedule.",
    )
    state = fields.Selection(
        [
            ("draft", "New"),
            ("open", "Running"),
            ("close", "Expired"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        help="Status of the contract",
    )
    kanban_state = fields.Selection(
        [
            ("normal", "In Progress"),
            ("done", "Ready"),
            ("blocked", "Blocked"),
        ],
        string="Kanban State",
        default="normal",
        tracking=True,
    )

    def get_all_structures(self):
        """
        @return: the structures linked to the given contracts, ordered by
                 hierachy (parent=False first, then first level children and
                 so on) and without duplicates
        """
        # TODO: remove, too simple and not used
        return self.struct_id.get_structure_with_parents()
