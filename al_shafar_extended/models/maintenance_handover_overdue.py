# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from odoo import _, api, fields, models

from .maintenance_request import STAGE_HANDOVER, STAGE_SCRAP

_logger = logging.getLogger(__name__)

# Days after the Scheduled Date within which a request must reach Handover;
# overridable via System Parameter al_shafar_extended.handover_overdue_days.
DEFAULT_HANDOVER_OVERDUE_DAYS = 3


class MaintenanceRequestHandoverOverdue(models.Model):
    """A request not handed over within N days (default 3) of its Scheduled
    Date is escalated once by email to the building's Property Manager (the
    same manager ribs_real_estate's maintenance emails go to). Rescheduling
    the request re-arms the alert for the new date."""
    _inherit = 'maintenance.request'

    handover_overdue_mail_date = fields.Datetime(
        string='Handover Overdue Alert Sent', readonly=True, copy=False)

    def write(self, vals):
        if 'schedule_date' in vals and 'handover_overdue_mail_date' not in vals:
            vals = dict(vals, handover_overdue_mail_date=False)
        return super().write(vals)

    def _handover_overdue_manager(self):
        self.ensure_one()
        building = self.building_id_parent or self.property_id.property_project_id
        return building.property_manager

    @api.model
    def _handover_overdue_days(self):
        value = self.env['ir.config_parameter'].sudo().get_str(
            'al_shafar_extended.handover_overdue_days', DEFAULT_HANDOVER_OVERDUE_DAYS)
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return DEFAULT_HANDOVER_OVERDUE_DAYS

    @api.model
    def _cron_handover_overdue_alert(self):
        days = self._handover_overdue_days()
        deadline = fields.Datetime.now() - timedelta(days=days)
        requests = self.search([
            ('schedule_date', '!=', False),
            ('schedule_date', '<=', deadline),
            ('handover_overdue_mail_date', '=', False),
            ('stage_id.name', 'not in', (STAGE_HANDOVER, STAGE_SCRAP)),
            ('state', '!=', 'cancelled'),
        ])
        template = self.env.ref('al_shafar_extended.mail_template_maintenance_handover_overdue',
                                raise_if_not_found=False)
        if not template:
            return
        for request in requests:
            manager = request._handover_overdue_manager()
            if not manager.work_email:
                _logger.info("al_shafar_extended: handover overdue on %s but its building has no "
                             "Property Manager email", request.display_name)
                continue
            template.with_context(handover_overdue_days=days, manager_name=manager.name).send_mail(
                request.id,
                email_values={
                    'email_from': request.company_id.email or self.env.company.email,
                    'email_to': manager.work_email,
                },
            )
            request.message_post(body=_(
                "Not handed over within %(days)s days of the scheduled date - alert sent to %(manager)s.",
                days=days, manager=manager.name))
            request.handover_overdue_mail_date = fields.Datetime.now()
