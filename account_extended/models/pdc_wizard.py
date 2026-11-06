# -*- coding: utf-8 -*-

from odoo import api, models, _
from odoo.exceptions import UserError


class PdcWizard(models.Model):
    _inherit = 'pdc.wizard'

    def _get_report_contract(self):
        """Contract of a PDC cheque: al_shafar_extended's stored tenancy_id
        when installed, else the contract of the invoice(s) it pays."""
        self.ensure_one()
        contract = self['tenancy_id'] if 'tenancy_id' in self._fields else False
        return contract or self.invoice_id.tenancy_id or self.invoice_ids[:1].tenancy_id


class ReportCombinedPdcCheque(models.AbstractModel):
    _name = 'report.account_extended.report_combined_pdc_cheque'
    _description = 'Combined PDC Cheque Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        cheques = self.env['pdc.wizard'].browse(docids).exists().sorted(
            lambda c: (c.due_date or c.payment_date, c.id))
        if not cheques:
            raise UserError(_("Please select at least one PDC cheque."))

        contracts = {cheque: cheque._get_report_contract() for cheque in cheques}
        contract_ids = {contract.id for contract in contracts.values()}
        if len(contract_ids) > 1:
            names = sorted({contract.tenancy_seq or _('No Contract') for contract in contracts.values()})
            raise UserError(_(
                "Combined PDC Cheque report can only be printed for cheques of the same contract.\n"
                "Selected cheques belong to: %s",
                ', '.join(names)))
        if not any(contract_ids) and len(cheques.mapped('partner_id')) > 1:
            raise UserError(_(
                "The selected cheques have no contract and belong to different customers. "
                "Please select cheques of a single contract."))

        contract = next(iter(contracts.values()))
        return {
            'doc_ids': cheques.ids,
            'doc_model': 'pdc.wizard',
            'docs': cheques,
            'contract': contract,
            'partner': contract.tenancy_id if contract else cheques[:1].partner_id,
            'building_name': contract.property_project_id.name if contract else '',
            'unit_name': contract._get_property_name() if contract else '',
            'currency': cheques[:1].currency_id,
            'total_amount': sum(cheques.mapped('payment_amount')),
        }
