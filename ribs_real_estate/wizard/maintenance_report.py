from odoo import fields, models,api
from odoo.exceptions import UserError

class MaintenanceReportWizard(models.TransientModel):
    _name = 'maintenance.report'
    _description = "Maintenance Report"

    maintenance_report_for = fields.Selection([('buildings', 'Buildings'),
                                              ('units', 'Units'),
                                              ('contracts', 'Contracts')],
                                              default='buildings',
                                              required=True,
                                              string="Maintenance Report",
                                              help="Select maintenance report for buildings, units, contracts or contracts")

    buildings = fields.Many2many(
        'property.project',
        'maintenance_report_building_rel',
        'wizard_id',
        'building_id',
        string="Buildings"
    )

    units = fields.Many2many(
        'property.details',
        'maintenance_report_unit_rel',
        'wizard_id',
        'unit_id',
        string="Units"
    )

    contracts = fields.Many2many(
        'tenancy.details',
        'maintenance_report_contract_rel',
        'wizard_id',
        'contract_id',
        string="Contracts"
    )

    def _get_grouped_maintenance_data(self, maintenances, group_by):
        grouped_data = {}
        grand_total = 0.0

        for maintenance in maintenances:
            if maintenance.total <= 0:
                continue

            if group_by == 'unit':
                key = maintenance.property_id.name if maintenance.property_id else 'No Unit'
            elif group_by == 'building':
                key = maintenance.property_id.property_project_id.name if maintenance.property_id and maintenance.property_id.property_project_id else 'No Building'
            elif group_by == 'contract':
                key = maintenance.rent_contract_id.tenancy_seq if maintenance.rent_contract_id else 'No Contract'
            else:
                key = 'Other'

            if key not in grouped_data:
                grouped_data[key] = []
            grouped_data[key].append({
                'id': maintenance.id,
                'name': maintenance.name,
                'total': maintenance.total,
            })
            grand_total += maintenance.total

        return sorted([(k, v) for k, v in grouped_data.items() if v]), grand_total

    def maintenance_report_print_action(self):
        self.ensure_one()
        domain = []
        group_by = False

        if self.maintenance_report_for == 'buildings':
            if self.buildings:
                domain = [('property_id.property_project_id', 'in', self.buildings.ids)]
            else:
                domain = [('property_id.property_project_id', '!=', False)]
            group_by = 'building'

        elif self.maintenance_report_for == 'units':
            if self.units:
                domain = [('property_id', 'in', self.units.ids)]
            else:
                domain = [('property_id', '!=', False)]
            group_by = 'unit'

        elif self.maintenance_report_for == 'contracts':
            if self.contracts:
                domain = [('rent_contract_id', 'in', self.contracts.ids)]
            else:
                domain = [('rent_contract_id', '!=', False)]
            group_by = 'contract'
        else:
            raise UserError("Please select Maintenance Report For")

        maintenance = self.env['maintenance.request'].search(domain)

        if not maintenance:
            raise UserError("No maintenance found")

        data = {
            'group_by': group_by,
            'grouped_data': None,
            'grand_total': 0.0,
        }

        if group_by:
            grouped_data, grand_total = self._get_grouped_maintenance_data(maintenance, group_by)
            data['grouped_data'] = grouped_data
            data['grand_total'] = grand_total

            if not grouped_data:
                raise UserError("No maintenance found")

        return self.env.ref(
            'ribs_real_estate.maintenance_report_pdf_action'
        ).report_action(maintenance, data=data)

    class MaintenanceReportCustom(models.AbstractModel):
        _name = 'report.ribs_real_estate.maintenance_report_pdf'
        _description = 'Maintenance Report Custom'

        @api.model
        def _get_report_values(self, docids, data=None):
            docs = self.env['maintenance.request'].browse(docids)

            group_by = data.get('group_by') if data else None
            grouped_data = data.get('grouped_data') if data else None
            grand_total = data.get('grand_total', 0.0) if data else 0.0

            if not group_by:
                grand_total = sum(doc.total for doc in docs if doc.total > 0)

            return {
                'doc_ids': docids,
                'doc_model': 'maintenance.request',
                'docs': docs,
                'group_by': group_by,
                'grouped_data': grouped_data,
                'grand_total': grand_total,
            }