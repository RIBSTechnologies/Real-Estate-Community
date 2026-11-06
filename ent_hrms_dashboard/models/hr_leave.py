# -*- coding: utf-8 -*-
################################################################################
#
#    A part of OpenHRMS Project <https://www.openhrms.com>
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0
#    (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the
#    Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#    OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
#    USE OR OTHER DEALINGS IN THE SOFTWARE.
#
################################################################################
from odoo import fields, models
from odoo.exceptions import AccessError


class HrLeave(models.Model):
    """ Adds field to show leave duration on hr.leave """
    _inherit = 'hr.leave'

    duration_display = fields.Char(
        string='Requested (Days/Hours)', compute='_compute_duration_display',
        store=True, help="Field allowing to see the leave request duration "
                         "in days or hours depending on the "
                         "work_entry_type_request_unit")

    def _check_hr_manager(self, message):
        # Core auto-approves leave types without validation under sudo()
        if not self.env.su and not self.env.user.has_group('hr.group_hr_manager'):
            raise AccessError(message)

    def action_approve(self, check_state=True):
        self._check_hr_manager("Only HR can approve or validate leave requests.")
        return super().action_approve(check_state)

    def action_refuse(self):
        self._check_hr_manager("Only HR can refuse leave requests.")
        return super().action_refuse()

    def action_back_to_approval(self):
        self._check_hr_manager("Only HR can reset leave requests.")
        return super().action_back_to_approval()

    def action_cancel(self):
        self._check_hr_manager("Only HR can cancel leave requests.")
        return super().action_cancel()

