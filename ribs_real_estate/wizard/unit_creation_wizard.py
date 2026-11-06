from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)


class UnitCreationInherit(models.TransientModel):

    _inherit = 'unit.creation'

    create_parking_slots = fields.Boolean(string='Do you want to create parking Slots?', default=False)
    property_code_prefix = fields.Char(string="Unit Prefix", help="Prefix for Property Code", readonly=False)
    parking_prefix = fields.Char(string="Parking Prefix", help="Prefix for Parking Code")
    unit_sequence_ids = fields.One2many('unit.sequence', 'unit_creation_id', string="Unit Sequence")
    sequence_seen = fields.Boolean(string="Sequence Seen", default=False)


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

            if getattr(line, 'floor', None):
                vals['floor'] = line.floor
            else:
                try:
                    prefix = (self.property_code_prefix or (project.project_sequence if project else "") or "").strip()
                    clean_name = line.unit_name
                    if prefix and clean_name.startswith(prefix):
                        clean_name = clean_name[len(prefix):]
                    floor_str = clean_name.strip('-').split("-")[0]
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


    def create_unit_sequence(self):
        self.ensure_one()

        lines = []

        active_id = self.env.context.get('project_id')
        unit_from = self.env.context.get('unit_from')
        property_type = self.env.context.get('property_type')
        property_subtype_id = self.env.context.get('property_subtype_id')
        is_individual = self.env.context.get('is_individual', False)
        project = None
        if unit_from == 'project':
            project = self.env["property.project"].browse(active_id)
        elif unit_from == 'sub_project':
            sub_project = self.env["property.sub.project"].browse(active_id)
            project = sub_project.property_project_id
        
        subtype = self.env['property.sub.type'].browse(property_subtype_id) if property_subtype_id else None

        prefix = (self.property_code_prefix or (project.project_sequence if project else "") or "").strip()
        if prefix:
            prefix_str = prefix if prefix.endswith('-') else f"{prefix}-"
        else:
            prefix_str = ""

        for floor in range(self.floor_start_from, self.total_floors + self.floor_start_from):
            for unit in range(1, self.units_per_floor + 1):
                if is_individual:
                    seq_code = f"{unit:02d}"
                else:
                    seq_code = f"{floor}{unit:02d}"

                unit_name = f"{prefix_str}{seq_code}"
                parking_name = (
                    f"{project.name}/P-{seq_code}"
                    if self.create_parking_slots else ""
                )

                lines.append((0, 0, {
                    'unit_name': unit_name,
                    'property_type': property_type if property_type else '',
                    'property_subtype_id': subtype.id if subtype else False,
                    'parking_name': parking_name,
                    'floor': floor,
                }))

        self.unit_sequence_ids = None
        self.unit_sequence_ids = lines
        self.sequence_seen = True

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

