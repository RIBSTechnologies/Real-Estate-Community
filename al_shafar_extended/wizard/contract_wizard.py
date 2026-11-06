# -*- coding: utf-8 -*-

from odoo import models, api


class ContractWizard(models.TransientModel):
    _inherit = 'contract.wizard'

    @api.onchange('contract_value', 'property_id')
    def _onchange_contract_value_deposit_basis(self):
        """When the unit's Deposit Basis is set to Contract Value, keep the
        Security Deposit in sync with this contract's actual Contract Value
        (duration/discount aware) instead of the unit's flat Yearly Rent."""
        for rec in self:
            property_id = rec.property_id
            if property_id and property_id.deposit_basis == 'contract':
                rec.deposit_amount = (rec.contract_value or 0.0) * (property_id.deposit_percentage or 0.0) / 100.0

    def _process_by_dated_full_payment(self, contract_id):
        """'By Date' Full Payment: ribs_real_estate prices the rent invoice
        line as get_total_rent() [monthly rent] * (days in contract) - a unit
        mismatch that charges the full annual rent (or more) instead of the
        contract's actual prorated value. Reuse the same method, but price
        the rent line from contract_value, which is already correctly
        prorated to the contract's exact start/end dates."""
        invoice_post_type = self.env["ir.config_parameter"].sudo(
        ).get_str("rental_management.invoice_post_type", False)
        delta = self.duration_end_date - self.start_date
        invoice_lines = [(0, 0, {
            'product_id': self.installment_item_id.id,
            "name": f"Full Payment : {self.start_date} to {self.duration_end_date}",
            "quantity": 1,
            "price_unit": self.contract_value or 0.0,
            "tax_ids": self.tax_ids.ids if self.instalment_tax else False,
        })]
        if self.is_any_deposit:
            invoice_lines.append((0, 0, {
                "product_id": self.deposit_item_id.id,
                "name": "Deposit of " + self.property_id.name,
                "quantity": 1,
                "price_unit": self.deposit_amount,
                "tax_ids": self.tax_ids.ids if self.deposit_tax else False,
            }))
        if self.is_any_maintenance and self.maintenance_service_invoice == 'merge':
            invoice_lines.append((0, 0, {
                "product_id": self.maintenance_item_id.id,
                "name": "Maintenance of " + self.property_id.name,
                "quantity": 1 if self.property_id.maintenance_rent_type == 'once' else (
                        delta.days + 1),
                "price_unit": self.total_maintenance,
            }))
        if self.is_extra_service and self.extra_service_invoice == 'merge':
            for line in self.property_id.extra_service_ids:
                service_type = 'Once' if line.service_type == 'once' else "Recurring"
                invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": f"Service Type : {service_type} - {line.service_id.name}",
                    "quantity": 1 if line.service_type == "once" else (delta.days + 1),
                    "price_unit": line.price,
                    "tax_ids": self.tax_ids.ids if self.service_tax else False,
                }))
        if self.is_added_services and self.added_service_ids and self.added_service_invoice == 'merge':
            for line in self.added_service_ids:
                invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": line.service_id.name,
                    "quantity": 1,
                    "price_unit": line.price,
                    "tax_ids": False,
                }))
        if self.is_added_services and self.added_service_ids and self.added_service_invoice == 'separate':
            self._process_separate_added_services(contract_id=contract_id)
        invoice_id = self.env['account.move'].sudo().create({
            "partner_id": self.customer_id.id,
            "move_type": "out_invoice",
            "invoice_date": contract_id.invoice_start_date,
            "invoice_line_ids": invoice_lines,
            "tenancy_id": contract_id.id
        })
        if invoice_post_type == "automatically":
            invoice_id.action_post()
        self.env['rent.invoice'].sudo().create({
            "tenancy_id": contract_id.id,
            "type": "full_rent",
            "invoice_date": contract_id.invoice_start_date,
            "amount": invoice_id.amount_total,
            "description": "Full Payment Of Rent" + (" + Deposit" if self.is_any_deposit else ""),
            "rent_invoice_id": invoice_id.id,
            "rent_amount": invoice_id.amount_total, })
        if self.is_any_maintenance and self.maintenance_service_invoice == 'separate':
            self._process_separate_invoices(
                contract_id=contract_id, maintenance=True)
        if self.is_extra_service and self.extra_service_invoice == 'separate':
            self._process_separate_invoices(
                contract_id=contract_id, utility=True)
        contract_id.action_send_active_contract()
