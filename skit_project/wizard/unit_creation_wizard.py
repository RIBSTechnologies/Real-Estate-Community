from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)


class UnitCreationInherit(models.TransientModel):

    _inherit = 'unit.creation'
    
    
    def action_create_property_unit(self):
        self.ensure_one()
        if not self.unit_sequence_ids:
            raise UserError("No unit preview data found. Please generate and review units first.")

        if self.total_floors <= 0 or self.units_per_floor <= 0:
            raise UserError("Total floors and units per floor must be greater than 0.")

        active_id = self.env.context.get('project_id')
        unit_from = self.env.context.get('unit_from')

        if not active_id or not unit_from:
            raise UserError("Missing project or subproject context.")

        if unit_from == 'project':
            project = self.env["property.project"].browse(active_id)
            property_rec = {'property_project_id': project.id}
        else:
            sub_project = self.env["property.sub.project"].browse(active_id)
            project = sub_project.property_project_id
            property_rec = {
                'property_project_id': project.id,
                'subproject_id': sub_project.id,
            }

        property_rec.update({
            'sale_lease': 'for_tenancy' if project.project_for == 'rent' else 'for_sale',
            'total_floor': self.total_floors,
            'property_subtype_id': project.property_subtype_id.id,
            'landlord_id': project.landlord_id.id,
            'type': project.property_type,
            'street': project.street,
            'street2': project.street2,
            'city_id': project.city_id.id,
            'zip': project.zip,
            'state_id': project.state_id.id,
            'country_id': project.country_id.id,
            'region_id': project.region_id.id,
            'website': project.website,
            'longitude': project.longitude,
            'latitude': project.latitude,
        })

        unit_amenities, unit_images, unit_specification, unit_connectivity = self.get_property_availability(
            unit_from=unit_from, project_id=project
        )
        property_rec.update(self.get_property_availability_info(
            project_id=project,
            unit_amenities=unit_amenities,
            unit_specification=unit_specification,
            unit_images=unit_images,
            unit_connectivity=unit_connectivity
        ))

        created_ids = []
        parking_ids = []

        for line in self.unit_sequence_ids:
            vals = property_rec.copy()
            vals.update({
                'name': line.unit_name,
                'property_seq': line.unit_name,
                'type': line.property_type,
                'property_subtype_id': line.property_subtype_id.id,
                'unit_type':line.bhk,
            })

            try:
                floor_str = line.unit_name.replace(self.property_code_prefix, '').split("-")[0]
                vals['floor'] = int(floor_str)
            except Exception:
                vals['floor'] = 0

            property_unit = self.env['property.details'].create(vals)
            created_ids.append(property_unit.id)

            if self.create_parking_slots and line.parking_name:
                parking_vals = {
                    'parking_numbers': line.parking_name,
                    'project_id': project.id,
                }
                parking = self.env['parking.slots'].create(parking_vals)
                parking_ids.append(parking.id)

                property_unit.parking_ids = [(4, parking.id)]

        if parking_ids:
            alloc = self.env['parking.allocation'].search([('project_id', '=', project.id)], limit=1)
            if alloc:
                alloc.parking_ids = [(6, 0, parking_ids)]
            else:
                self.env['parking.allocation'].create({
                    'project_id': project.id,
                    'parking_ids': [(6, 0, parking_ids)],
                })

        project.write({
            'total_floors': self.total_floors,
            'units_per_floor': self.units_per_floor,
            'floor_created': project.floor_created + self.total_floors
        })

        return {
            "name": "Properties",
            "type": "ir.actions.act_window",
            "domain": [("id", "in", created_ids)],
            "view_mode": "list,form",
            'context': {'create': False},
            "res_model": "property.details",
            "target": "current",
        }