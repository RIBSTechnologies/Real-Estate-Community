# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ContractTerminationReportWizard(models.TransientModel):
    _name = 'contract.termination.report.wizard'
    _description = 'Contract Termination Report Wizard'

    date_from = fields.Date(
        string="Termination Date From",
        default=lambda self: fields.Date.today().replace(month=1, day=1)
    )
    date_to = fields.Date(
        string="Termination Date To",
        default=fields.Date.today
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string="Customers / Partners"
    )
    refund_status = fields.Selection([
        ('all', 'All Statuses'),
        ('pending', 'Pending Refund'),
        ('refunded', 'Refunded'),
        ('no_refund', 'No Refund Required')
    ], string="Refund Status Filter", default='all', required=True)

    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company
    )

    def _get_report_domain(self):
        self.ensure_one()
        domain = [
            ('state', '=', 'terminated'),
            ('company_id', '=', self.company_id.id),
        ]
        if self.date_from:
            domain.append(('termination_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('termination_date', '<=', self.date_to))
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        if self.refund_status != 'all':
            domain.append(('refund_status', '=', self.refund_status))
        return domain

    def _get_terminated_contracts(self):
        self.ensure_one()
        return self.env['contract.contract'].search(self._get_report_domain(), order='termination_date desc, id desc')

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('al_shafar_extended.action_report_contract_termination_pdf').report_action(self)
