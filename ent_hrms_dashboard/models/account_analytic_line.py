from odoo import models, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import date


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    @api.constrains('date')
    def _check_timesheet_future_date(self):
        today = date.today()
        for record in self:
            if record.date and record.date > today:
                raise ValidationError(
                    "You cannot create a timesheet for a future date."
                )

    def unlink(self):
        for line in self:
            if line.ref and 'Leave' in line.ref:
                if not self.env.user.has_group('hr.group_hr_manager'):
                    raise UserError(_("You are not allowed to delete timesheet entries."))

        return super(AccountAnalyticLine, self).unlink()

