# -*- coding: utf-8 -*-
# Copyright 2020-Today TechKhedut.
# Part of TechKhedut. See LICENSE file for full copyright and licensing details.
import base64
from odoo import api, fields, models, tools, _
from odoo.tools.image import is_image_size_above
from odoo.exceptions import ValidationError
from odoo.addons.rental_management.tools import get_video_embed_code, get_video_thumbnail
from datetime import date, timedelta


def is_float(str_vals):
    """Check if string is Float or not
    :param str_vals: String
    :return: True if string is Float or not
    """
    vals = str_vals.replace("-", "").replace(".", "").isnumeric()
    return bool(vals)


class PropertyDetails(models.Model):
    """Property Details"""
    _name = 'property.details'
    _description = 'Property Details and for registration new Property'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Property Details
    name = fields.Char(string='Name', required=True, translate=True, tracking=True)
    image = fields.Binary(string='Image')
    type = fields.Selection([('land', 'Land'),
                             ('residential', 'Residential'),
                             ('commercial', 'Commercial'),
                             ('industrial', 'Industrial')
                             ], string='Property Type',
                            required=True,
                            default="residential",
                            tracking=True)
    sale_lease = fields.Selection([('for_sale', 'Sale'),
                                   ('for_tenancy', 'Rent')],
                                  string='Property For',
                                  default='for_tenancy',
                                  required=True,
                                  tracking=True)
    property_seq = fields.Char(string='Property Code',
                               required=True,
                               readonly=False,
                               copy=False,
                               default=lambda self: '')
    stage = fields.Selection([('draft', 'Draft'),
                              ('available', 'Available'),
                              ('booked', 'In Booking'),
                              ('on_lease', 'On Rent'),
                              ('sale', 'In Sale'),
                              ('sold', 'Sold')
                              ],
                             group_expand='_expand_groups',
                             string='Status',
                             default='draft',
                             copy=False,
                             required=True)
    
    stage_search = fields.Selection([
        ('draft', 'Draft'),
        ('available', 'Available'),
        ('on_lease', 'On Rent'),
    ], compute='_compute_stage_search', store=True)

    @api.depends('stage')
    def _compute_stage_search(self):
        for rec in self:
            if rec.stage in ('draft', 'available', 'on_lease'):
                rec.stage_search = rec.stage
            else:
                rec.stage_search = False


    # Multi Companies
    company_id = fields.Many2one('res.company',
                                 string='Company',
                                 default=lambda self: self.env.company,
                                 tracking=True)
    currency_id = fields.Many2one('res.currency',
                                  related='company_id.currency_id',
                                  string='Currency')

    # Property Sub Type
    property_subtype_id = fields.Many2one('property.sub.type',
                                          string="Property Sub Type",
                                          domain="[('type','=',type)]",
                                          tracking=True)

    # Project & Sub Project & Region
    region_id = fields.Many2one('property.region', string="Region")
    property_project_id = fields.Many2one('property.project',
                                          string="Building")
    subproject_id = fields.Many2one('property.sub.project',
                                    string="Sub Project")

    # Address
    region_id = fields.Many2one('property.region', string="Region", tracking=True)
    zip = fields.Char(string='Zip', tracking=True)
    street = fields.Char(string='Street1', translate=True, tracking=True)
    street2 = fields.Char(string='Street2', translate=True, tracking=True)
    city = fields.Char(string='City  ', translate=True, tracking=True)
    city_id = fields.Many2one('property.res.city', string='City', tracking=True)
    country_id = fields.Many2one('res.country', 'Country', tracking=True)
    state_id = fields.Many2one(
        "res.country.state", string='State', store=True,
        domain="[('country_id', '=?', country_id)]",
        tracking=True)

    # Lat Long
    longitude = fields.Char(string='Longitude')
    latitude = fields.Char(string='Latitude')

    # Owner Details
    landlord_id = fields.Many2one(related='property_project_id.landlord_id')
    landlord_phone = fields.Char(string="Phone", related="landlord_id.phone")
    landlord_email = fields.Char(string="Email", related="landlord_id.email")
    website = fields.Char(string='Website', translate=True)

    # Property Tags
    tag_ids = fields.Many2many('property.tag', string='Tags', tracking=True)

    # Availability
    amenities = fields.Boolean(string="Amenities", tracking=True)
    is_facilities = fields.Boolean(string="Specifications", tracking=True)
    is_images = fields.Boolean(string="Images", tracking=True)
    is_floor_plan = fields.Boolean(string="Floor Plans", tracking=True)
    nearby_connectivity = fields.Boolean(string="Nearby Connectivities", tracking=True)

    # Area Measurement
    is_section_measurement = fields.Boolean(
        string="Is Section Area Measurement")
    measure_unit = fields.Selection([('sq_ft', 'ft²'),
                                     ('sq_m', 'm²'),
                                     ('sq_yd', 'yd²'),
                                     ('cu_ft', 'ft³'),
                                     ('cu_m', 'm³')],
                                    default='sq_ft',
                                    string="Area Measurement Unit", tracking=True)
    room_measurement_ids = fields.One2many('property.room.measurement',
                                           'room_measurement_id',
                                           string='Area Measurement')
    total_room_measure = fields.Integer(compute='_compute_room_measure',
                                        store=True,
                                        tracking=True)
    total_area = fields.Float(string="Total Area", tracking=True)
    usable_area = fields.Float(string="Usable Area", tracking=True)
    sq_ft = fields.Float(string="Total Ft²")
    sq_m = fields.Float(string="Total M²")
    sq_yd = fields.Float(string="Total Yd²")
    cu_ft = fields.Float(string="Total Ft³")
    cu_m = fields.Float(string="Total M³")

    # Pricing
    price = fields.Monetary(string="Price", store=True)
    rent_unit = fields.Selection([('Day', "Day"),
                                  ('Month', "Month"),
                                  ('Year', "Year")],
                                 default='Month',
                                 string="Rent Unit",
                                 tracking=True)
    pricing_type = fields.Selection([('fixed', 'Fixed'),
                                     ('area_wise', 'Area Wise')],
                                    string="Pricing Type",
                                    default='fixed',
                                    tracking=True)
    price_per_area = fields.Monetary(string="Price / Area")

    # Utility Service
    is_extra_service = fields.Boolean(string="Utility Services", tracking=True)
    extra_service_ids = fields.One2many('extra.service.line',
                                        'property_id',
                                        string="Services")
    extra_service_cost = fields.Monetary(string="Utility Cost",
                                         compute="_compute_extra_service_cost")

    # Maintenance Service
    is_maintenance_service = fields.Boolean(string="Is Any Maintenance", tracking=True)
    maintenance_rent_type = fields.Selection([('once', 'Once'),
                                              ('recurring', 'Recurring')],
                                             string="Maintenance Type",
                                             default="once")
    maintenance_type = fields.Selection([('fixed', 'Fixed'),
                                         ('area_wise', 'Area Wise')],
                                        string="Charges Type")
    per_area_maintenance = fields.Monetary(string="Maintenance / Area")
    total_maintenance = fields.Monetary(string="Total Maintenance")

    #  Property Documents
    document_ids = fields.One2many('property.documents',
                                   'property_id',
                                   string="Documents")

    # Property Amities
    amenities_ids = fields.Many2many('property.amenities',
                                     string="Property Amenities")

    # Property Specification
    property_specification_ids = fields.Many2many('property.specification',
                                                  string='Property Specifications')

    # Image
    property_images_ids = fields.One2many('property.images',
                                          'property_id',
                                          string='Property Images')
    # Floor Plan
    floreplan_ids = fields.One2many('floor.plan',
                                    'property_id',
                                    string='Property Floor Plans')
    # Nearby Connectivity
    connectivity_ids = fields.One2many('property.connectivity.line',
                                       'property_id',
                                       string="Property Nearby Conductivities")

    # Maintenance History
    maintenance_ids = fields.One2many('maintenance.request',
                                      'property_id',
                                      string='Maintenance Histories')

    # Increment History
    increment_history_ids = fields.One2many('increment.history', 'property_id')

    # Property Broker And Tenancies
    tenancy_broker_count = fields.Integer(string="Rent Broker Count",
                                          compute="compute_count")
    tenancy_ids = fields.One2many('tenancy.details',
                                  'property_id',
                                  string='Rent Contracts')
    broker_ids = fields.One2many('tenancy.details',
                                 'property_id',
                                 string='Broker History',
                                 domain=[('is_any_broker', '=', True)])

    # Property Broker and Selling
    property_vendor_ids = fields.One2many('property.vendor',
                                          'property_id',
                                          string='Booking Details')
    sold_booking_id = fields.Many2one('property.vendor', copy=False,
                                      string="Booking")
    sale_broker_count = fields.Integer(string="Sale Broker Count",
                                       compute="compute_count")

    #  Enquiry
    tenancy_inquiry_ids = fields.One2many('tenancy.inquiry',
                                          'property_id',
                                          string="Rent Enquiry")
    sale_inquiry_ids = fields.One2many('sale.inquiry',
                                       'property_id',
                                       string="Sale Enquiry")

    # CRM Lead
    lead_count = fields.Integer(string="Lead Count",
                                compute="_compute_lead")
    lead_opp_count = fields.Integer(string="Opportunity Count",
                                    compute="_compute_lead")

    # Property Type wise Details
    total_floor = fields.Integer(string='No of Floors', tracking=True)
    floor = fields.Char(string='Floor', tracking=True)
    bed = fields.Integer(string='Rooms', default=1, tracking=True)
    bathroom = fields.Integer(string='Bathrooms', default=1, tracking=True)
    parking = fields.Integer(string='Parking', default=1, tracking=True)
    facing = fields.Selection([('N', 'North(N)'),
                               ('E', 'East(E)'),
                               ('S', 'South(S)'),
                               ('W', 'West(W)'),
                               ('NE', 'North-East(NE)'),
                               ('SE', 'South-East(SE)'),
                               ('SW', 'South-West(SW)'),
                               ('NW', 'North-West(NW)'), ],
                              string='Facing', default='N',
                              tracking=True)
    furnishing_id = fields.Many2one('property.furnishing', string="Furnishing", tracking=True)
    unit_type = fields.Integer(string="Unit Type", default=1, tracking=True)

    # Smart Button Count
    document_count = fields.Integer(string='Document Count',
                                    compute='_compute_document_count')
    request_count = fields.Integer(string='Request Count',
                                   compute='_compute_request_count')
    booking_count = fields.Monetary(string='Booking Count',
                                    compute='_compute_booking_count')
    tenancy_count = fields.Integer(string='Rent Count',
                                   compute='_compute_booking_count')
    increment_history_count = fields.Integer(string="Increment History Count",
                                             compute="_compute_booking_count")
    vendor_count = fields.Integer(string="Sell Count", compute='_compute_booking_count')

    # Create, Constrain, Write, Scheduler, Name get
    # Create
    @api.model_create_multi
    def create(self, vals_list):
        """Property Create"""
        for vals in vals_list:
            if not vals.get('property_seq'):
                vals['property_seq'] = self.env['ir.sequence'].next_by_code(
                    'property.details') or ''
        res = super(PropertyDetails, self).create(vals_list)
        return res

    # Stage Expand
    @api.model
    def _expand_groups(self, states, domain):
        return ['draft', 'available', 'booked', 'on_lease', 'sale', 'sold']

    # On delete
    @api.ondelete(at_uninstall=False)
    def _unlink_property(self):
        """Prevent unlink property when status is not 'available'"""
        for rec in self:
            if rec.stage in ['booked', 'on_lease', 'sale', 'sold']:
                raise ValidationError(
                    _("You can't delete property until status is in 'Draft' or 'Available'"))

    # Scheduler
    @api.model
    def update_property_measurement(self):
        """To Update measurement not required after vesrion 2.0"""
        pass

    # Compute
    # Total Measurement
    @api.depends('room_measurement_ids', 'type', 'measure_unit', 'is_section_measurement')
    def _compute_room_measure(self):
        """Compute room measurement"""
        for rec in self:
            total = 0
            if rec.room_measurement_ids:
                for data in rec.room_measurement_ids:
                    total = total + data.carpet_area
            rec.total_room_measure = total
            if rec.is_section_measurement:
                rec.total_area = total

    # CRM Leads
    @api.depends('sale_lease')
    def _compute_lead(self):
        """Compute property lead"""
        for rec in self:
            rec.lead_count = self.env['crm.lead'].search_count(
                [('property_id', 'in', [rec.id]), ('type', '=', 'lead')])
            rec.lead_opp_count = self.env['crm.lead'].search_count(
                [('property_id', 'in', [rec.id]), ('type', '=', 'opportunity')])

    # Utility Service Total
    @api.depends('extra_service_ids')
    def _compute_extra_service_cost(self):
        """Compute extra service total cost"""
        for rec in self:
            amount = 0.0
            if rec.extra_service_ids:
                for data in rec.extra_service_ids:
                    amount = amount + data.price
            rec.extra_service_cost = amount

    # Counts
    # Document Count
    def _compute_document_count(self):
        """Compute property document count"""
        for rec in self:
            document_count = self.env['property.documents'].search_count(
                [('property_id', 'in', [rec.id])])
            rec.document_count = document_count

    # Booking Count
    def _compute_booking_count(self):
        """Compute property booking count"""
        for rec in self:
            count = self.sold_booking_id.book_price
            rec.booking_count = count
            rec.tenancy_count = self.env['tenancy.details'].search_count(
                [('property_id', 'in', [rec.id])])
            rec.increment_history_count = self.env['increment.history'].search_count(
                [('property_id', 'in', [rec.id])])
            rec.vendor_count = self.env['property.vendor'].search_count(
                [('property_id', 'in', [rec.id])])

    # Maintenance Request Count
    def _compute_request_count(self):
        for rec in self:
            """Compute maintenance request count"""
            request_count = self.env['maintenance.request'].search_count(
                [('property_id', 'in', [rec.id])])
            rec.request_count = request_count

    # Count
    def compute_count(self):
        """Compute Count"""
        for rec in self:
            rec.sale_broker_count = len(self.env['property.vendor'].sudo(
            ).search([('property_id', 'in', [rec.id]), ('is_any_broker', '=', True)]).mapped(
                'broker_id').mapped('id'))
            rec.tenancy_broker_count = len(self.env['tenancy.details'].sudo(
            ).search([('property_id', 'in', [rec.id]), ('is_any_broker', '=', True)]).mapped(
                'broker_id').mapped('id'))

    # Onchange
    # Area Wise Price
    @api.onchange('pricing_type', 'price_per_area', 'measure_unit', 'room_measurement_ids',
                  'is_section_measurement',
                  'total_area')
    def _onchange_fix_area_price(self):
        """Onchange fix area price"""
        for rec in self:
            if rec.pricing_type == 'area_wise':
                rec.price = rec.total_area * rec.price_per_area

    # Maintenance Area wise Price
    @api.onchange('is_maintenance_service', 'maintenance_type', 'per_area_maintenance')
    def _onchange_maintenance_type_charges(self):
        """Onchange maintenance type charge"""
        for rec in self:
            if rec.is_maintenance_service and rec.maintenance_type == 'area_wise':
                rec.total_maintenance = rec.per_area_maintenance * rec.total_area

    # Total Area
    @api.onchange('room_measurement_ids', 'is_section_measurement')
    def _onchange_area_measure(self):
        """Onchange area measurement"""
        for rec in self:
            total = 0.0
            if rec.is_section_measurement and rec.room_measurement_ids:
                for data in rec.room_measurement_ids:
                    total = total + data.carpet_area
                rec.total_area = total

    # Property Sub Type Domain
    @api.onchange('type')
    def _onchange_property_sub_type(self):
        """Onchange property sub type"""
        for rec in self:
            rec.property_subtype_id = False

    # State And Country Onchange
    @api.onchange('country_id')
    def _onchange_country_id(self):
        """Empty state_id onchange country_id"""
        if self.country_id and self.country_id != self.state_id.country_id:
            self.state_id = False

    @api.onchange('state_id')
    def _onchange_state(self):
        """Get country onchange state_id"""
        if self.state_id.country_id:
            self.country_id = self.state_id.country_id

    @api.constrains('longitude', 'latitude')
    def _check_longitude_latitude_values(self):
        """
        Check longitude latitude values
        values should be float
        longitude should be between -180 to 180
        latitude should be between -80 to 80
        """
        for rec in self:
            if rec.longitude and not is_float(rec.longitude):
                raise ValidationError(
                    _("Longitude values must be float.")
                )
            if rec.latitude and not is_float(rec.latitude):
                raise ValidationError(
                    _("Latitude values must be float.")
                )
            if rec.longitude and is_float(rec.longitude) and (
                    float(rec.longitude) > 180 or float(rec.longitude) < -180):
                raise ValidationError(
                    _("Longitude must be in range of -180 to 180")
                )
            if rec.latitude and is_float(rec.latitude) and (
                    float(rec.latitude) > 90 or float(rec.latitude) < -90):
                raise ValidationError(
                    _("Latitude must be in range of -90 to 90")
                )

    # Buttons
    # Stage Buttons
    def action_in_available(self):
        """Status : Available"""
        for rec in self:
            rec.stage = 'available'

    def action_in_booked(self):
        """Status : Booked"""
        for rec in self:
            rec.stage = 'booked'

    def action_sold(self):
        """Status : Sold"""
        for rec in self:
            rec.stage = 'sold'

    def action_draft_property(self):
        """Status : Draft"""
        self.stage = "draft"

    def action_in_sale(self):
        """Status : Sale Property"""
        if self.sale_lease == 'for_sale':
            self.stage = 'sale'
        else:
            message = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'title': 'You need to set "Price/Rent" to "For Sale" to proceed',
                    'sticky': False,
                }
            }
            return message

    # G-map Location
    def action_gmap_location(self):
        """Google map location bases on longitude and latitude"""
        if self.longitude and self.latitude:
            longitude = self.longitude
            latitude = self.latitude
            http_url = 'https://maps.google.com/maps?q=loc:' + latitude + ',' + longitude
            return {
                'type': 'ir.actions.act_url',
                'target': 'new',
                'url': http_url,
            }
        else:
            raise ValidationError(
                "! Enter Proper Longitude and Latitude Values")

    # Smart Button
    def action_maintenance_request(self):
        """View maintenance request"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Request',
            'res_model': 'maintenance.request',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
            'view_mode': 'kanban,list,form',
            'target': 'current'
        }

    def action_property_document(self):
        """View property document"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Document',
            'res_model': 'property.documents',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
            'view_mode': 'list',
            'target': 'current'
        }

    def action_sale_booking(self):
        """View Sale Booking"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Booking Information',
            'res_model': 'property.vendor',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
            'view_mode': 'list,form',
            'target': 'current'
        }

    def action_crm_lead(self):
        """View CRM Lead"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leads',
            'res_model': 'crm.lead',
            'domain': [('property_id', '=', self.id), ('type', '=', 'lead')],
            'context': {'default_property_id': self.id, 'default_type': 'lead'},
            'view_mode': 'list,form',
            'target': 'current'
        }

    def action_crm_lead_opp(self):
        """View Lead opportunity"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Opportunity',
            'res_model': 'crm.lead',
            'domain': [('property_id', '=', self.id), ('type', '=', 'opportunity')],
            'context': {'default_property_id': self.id, 'default_type': 'opportunity'},
            'view_mode': 'list,form',
            'target': 'current'
        }

    def action_view_contract(self):
        """View property rent contract"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Rent Contracts',
            'res_model': 'tenancy.details',
            'domain': [('property_id', '=', self.id)],
            'context': {'create': False},
            'view_mode': 'list,form',
            'target': 'current'
        }

    def action_view_sell_contract(self):
        """View property sell contract"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sell Contracts',
            'res_model': 'property.vendor',
            'domain': [('property_id', '=', self.id)],
            'context': {'create': False},
            'view_mode': 'list,form',
            'target': 'current'
        }

    def action_property_tenancy_broker(self):
        """View property tenancy broker"""
        ids = self.env['tenancy.details'].sudo().search(
            [('property_id', '=', self.id), ('is_any_broker', '=', True)]).mapped(
            'broker_id').mapped('id')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Brokers',
            'res_model': 'res.partner',
            'domain': [('id', 'in', ids)],
            'context': {'create': False},
            'view_mode': 'list,form',
            'target': 'current'
        }

    def action_property_sale_broker(self):
        """View property sale brokers"""
        ids = self.env['property.vendor'].sudo().search(
            [('property_id', '=', self.id), ('is_any_broker', '=', True)]).mapped(
            'broker_id').mapped('id')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Brokers',
            'res_model': 'res.partner',
            'domain': [('id', 'in', ids)],
            'context': {'create': False},
            'view_mode': 'list,form',
            'target': 'current'
        }

    def action_view_increment_history(self):
        """View rent increment history"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Increment History',
            'res_model': 'increment.history',
            'domain': [('property_id', '=', self.id)],
            'context': {'create': False},
            'view_mode': 'list,form',
            'target': 'current'
        }

    # Server Action
    def action_available_property(self):
        """Status : Available property"""
        active_ids = self.env.context.get('active_ids')
        property_rec = self.env['property.details'].sudo().browse(active_ids)
        for data in property_rec:
            if data.stage == 'draft':
                data.write({
                    'stage': 'available'
                })

    # DashBoard
    @api.model
    def get_property_stats(self):
        """Get dashboard statics"""
        company_domain = [('company_id', 'in', self.env.companies.ids)]
        # Property Stages
        property = self.env['property.details']
        crm = self.env['crm.lead']
        pdc = self.env['pdc.wizard']
        avail_property = property.sudo().search_count(
            [('stage', '=', 'available')] + company_domain)
        booked_property = property.sudo().search_count(
            [('stage', '=', 'booked')] + company_domain)
        lease_property = property.sudo().search_count(
            [('stage', '=', 'on_lease')] + company_domain)
        sale_property = property.sudo().search_count([('stage', '=', 'sale')] + company_domain)
        sold_property = property.sudo().search_count([('stage', '=', 'sold')] + company_domain)
        currency_symbol = self.env.company.currency_id.symbol
        land_property = property.sudo().search_count([('type', '=', 'land')] + company_domain)
        residential_property = property.sudo().search_count(
            [('type', '=', 'residential')] + company_domain)
        commercial_property = property.sudo().search_count(
            [('type', '=', 'commercial')] + company_domain)
        industrial_property = property.sudo().search_count(
            [('type', '=', 'industrial')] + company_domain)
        property_type = [['Land', 'Residential', 'Commercial', 'Industrial'],
                         [land_property, residential_property, commercial_property,
                          industrial_property]]
        property_stage = [
            ['Available Properties', 'Sold Properties', 'Booked Properties', 'On Sale', 'On Lease'],
            [avail_property, sold_property, booked_property, sale_property, lease_property]]

        # Rent Contract
        rent_contract = self.env['tenancy.details'].sudo()
        draft_contract = rent_contract.search_count(
            [('contract_type', '=', 'new_contract')] + company_domain)
        running_contract = rent_contract.search_count(
            [('contract_type', '=', 'running_contract')] + company_domain)
        expire_contract = rent_contract.search_count(
            [('contract_type', '=', 'expire_contract')] + company_domain)
        extend_contract = rent_contract.search_count(
            [('is_extended', '=', True)] + company_domain)

        # just changed the domain of ( getting about to expire contract instead of close contract )
        close_contract = rent_contract.search_count(
            [('days_left', '!=', 0), ('days_left', '<=', 120)] + company_domain
        )
        close_contract_obj = rent_contract.search(
            [('days_left', '!=', 0), ('days_left', '<=', 120)] + company_domain
        )
            
        full_tenancy_total = sum(self.env['rent.invoice'].search(
            ['|', ('type', '=', 'rent'), ('type', '=', 'full_rent')] + company_domain).mapped(
            'rent_invoice_id').mapped(
            'amount_total'))
        pending_invoice = self.env['rent.invoice'].search_count(
            [('payment_state', '=', 'not_paid')] + company_domain)

        # Sale Contract
        sale_contract = self.env['property.vendor'].sudo()
        booked = sale_contract.search_count([('stage', '=', 'booked')] + company_domain)
        sale_sold = sale_contract.search_count([('stage', '=', 'sold')] + company_domain)
        refund = sale_contract.search_count([('stage', '=', 'refund')] + company_domain)
        sold_total = sum(
            sale_contract.search([('stage', '=', 'sold')] + company_domain).mapped('sale_price'))
        pending_invoice_sale = self.env['account.move'].search_count(
            [('sold_id', '!=', False), ('payment_state', '=', 'not_paid')] + company_domain)

        # Region, Project, Sub Project, Properties
        region_count = self.env['property.region'].search_count([])
        project_count = self.env['property.project'].search_count(company_domain)
        subproject_count = self.env['property.sub.project'].search_count(company_domain)
        total_property = property.search_count(company_domain)

        # Customer & Landlord
        customer_count = self.env['res.partner'].sudo(
        ).search_count([('user_type', '=', 'customer')])
        landlord_count = self.env['res.partner'].sudo(
        ).search_count([('user_type', '=', 'landlord')])

        # CRM
        # new_leads = crm.search_count(
        #     [('type','=','lead')]
        # )

        # domain = [
        #     ('payments_received', 'in', [False, 'not_received']),
        #     ('contract_type', '=', 'running_contract'),
        # ]
        # if not self.env.user._is_admin() and not self.env.user.has_group('ribs_real_estate.property_rental_accountant'):
        #     domain.append(('responsible_id', '=', self.env.user.id))
        # new_leads = self.env['tenancy.details'].search_count(domain)


        new_leads = self.env['tenancy.details'].search_count([
            ('payments_received', 'in', [False,'not_received']),('contract_type','=','running_contract')])
        contract_payments_with_finance_comments = self.env['contract.payments'].search_count([
            ('finance_comment_added', '=', True),
            ('line_payment_received', '=', 'not_received'),
        ])
        contract_payments_with_leasing_comments = self.env['contract.payments'].search_count([
            ('leasing_comment_added', '=', True),
            ('line_payment_received', '=', 'not_received'),
        ])
        contract_payments_not_sent = self.env['tenancy.details'].search_count([
            ('payments_received', '=', 'received'),('is_confirmed_payment_mail_sent','=',False)])
        unapproved_documents = self.env['partner.documents'].search_count([
            ('verified_status', '=', 'pending')])
        
        # PDC
        today = date.today()
        next_7_days = today + timedelta(days=7)
        company_domain = [('company_id', 'in', self.env.companies.ids)]

        upcoming_pdc = pdc.search_count([
            ('due_date', '>=', today),
            ('due_date', '<=', next_7_days),
            ('state', '=', 'draft'),
        ] + company_domain)

        bounced_pdc = pdc.search_count([
            ('state', '=', 'bounced'),
        ] + company_domain)

        not_received_pdc = pdc.search_count([
            ('state', '=', 'deposited'),
        ] + company_domain)

        return {
            # Property
            'avail_property': avail_property,
            'booked_property': booked_property,
            'lease_property': lease_property,
            'sale_property': sale_property,
            'sold_property': sold_property,
            # Rent Contract
            'draft_contract': draft_contract,
            'running_contract': running_contract,
            'expire_contract': expire_contract,
            'extend_contract': extend_contract,
            'close_contract': close_contract,
            'pending_invoice': pending_invoice,
            'rent_total': str(
                round(full_tenancy_total, 2)) + ' ' + currency_symbol if currency_symbol else "",
            # Sale Contract
            'booked': booked,
            'sale_sold': sale_sold,
            'refund': refund,
            'sold_total': str(
                round(sold_total, 2)) + ' ' + currency_symbol if currency_symbol else "",
            'pending_invoice_sale': pending_invoice_sale,
            # Customer & Landlord
            'customer_count': customer_count,
            'landlord_count': landlord_count,
            # Region, Project, Sub Project, Properties
            'region_count': region_count,
            'project_count': project_count,
            'subproject_count': subproject_count,
            'total_property': total_property,
            # Graph
            'property_type': property_type,
            'property_stage': property_stage,
            'property_map_data': self.get_property_map_data(),
            'due_paid_amount': self.due_paid_amount(),
            'tenancy_top_broker': self.get_top_broker(),
            # CRM
            'new_leads':new_leads,
            # PDC
            'upcoming_pdc':upcoming_pdc,
            'bounced_pdc':bounced_pdc,
            'not_received_pdc':not_received_pdc,
            'finance_comment_count':contract_payments_with_finance_comments,
            'leasing_comment_count':contract_payments_with_leasing_comments,
            'contract_payments_not_sent_count':contract_payments_not_sent,
            'unapproved_documents':unapproved_documents,
        }

    @api.model
    def retrieve_list_dashboard_data(self):
        """ This function returns the values to populate the custom dashboard in
            the Property List views.
        """
        property_obj = self.env['property.details'].sudo()

        stages = ['available', 'booked', 'on_lease', 'sale', 'sold', 'draft']
        data = {}

        for stage in stages:
            data[f'{stage}_prop_count'] = property_obj.search_count([('stage', '=', stage)])
            data[f'{stage}_land_prop_count'] = property_obj.search_count([
                ('stage', '=', stage),
                ('type', '=', 'land'),
            ])
            data[f'{stage}_residential_prop_count'] = property_obj.search_count([
                ('stage', '=', stage),
                ('type', '=', 'residential'),
            ])
            data[f'{stage}_commercial_prop_count'] = property_obj.search_count([
                ('stage', '=', stage),
                ('type', '=', 'commercial'),
            ])
            data[f'{stage}_industrial_prop_count'] = property_obj.search_count([
                ('stage', '=', stage),
                ('type', '=', 'industrial'),
            ])

        data['total_prop_count'] = property_obj.search_count([('stage', '!=', 'draft')])
        data['total_land_prop_count'] = property_obj.search_count([
            ('stage', '!=', 'draft'),
            ('type', '=', 'land'),
        ])
        data['total_residential_prop_count'] = property_obj.search_count([
            ('stage', '!=', 'draft'),
            ('type', '=', 'residential'),
        ])
        data['total_commercial_prop_count'] = property_obj.search_count([
            ('stage', '!=', 'draft'),
            ('type', '=', 'commercial'),
        ])
        data['total_industrial_prop_count'] = property_obj.search_count([
            ('stage', '!=', 'draft'),
            ('type', '=', 'industrial'),
        ])
        # FOR RENT
        for_rent_domain = [('stage', '=', 'available'), ('sale_lease', '=', 'for_tenancy')]
        data['total_for_rent_count'] = property_obj.search_count(for_rent_domain)
        data['total_for_rent_land_count'] = property_obj.search_count(
            for_rent_domain + [('type', '=', 'land')])
        data['total_for_rent_residential_count'] = property_obj.search_count(
            for_rent_domain + [('type', '=', 'residential')])
        data['total_for_rent_commercial_count'] = property_obj.search_count(
            for_rent_domain + [('type', '=', 'commercial')])
        data['total_for_rent_industrial_count'] = property_obj.search_count(
            for_rent_domain + [('type', '=', 'industrial')])
        return data

    def get_top_broker(self):
        """Dashboard : Get top broker"""
        company_ids = self.env.companies.ids
        broker_tenancy = {}
        broker_sold = {}
        # Odoo 20 read_group(domain, groupby, aggregates) returns tuples
        for broker, count in self.env['tenancy.details'].read_group(
                [('is_any_broker', '=', True), ('company_id', 'in', company_ids)],
                ['broker_id'], ['__count'], limit=5, order='__count desc'):
            if broker:
                broker_tenancy[broker.sudo().name] = count
        for broker, count in self.env['property.vendor'].read_group(
                [('is_any_broker', '=', True), ('company_id', 'in', company_ids),
                 ('stage', '=', 'sold')],
                ['broker_id'], ['__count'], limit=5, order='__count desc'):
            if broker:
                broker_sold[broker.sudo().name] = count

        brokers_tenancy_list = dict(
            sorted(broker_tenancy.items(), key=lambda x: x[1], reverse=True))
        broker_sold_list = dict(
            sorted(broker_sold.items(), key=lambda x: x[1], reverse=True))
        return [list(brokers_tenancy_list.keys()), list(brokers_tenancy_list.values()),
                list(broker_sold_list.keys()),
                list(broker_sold_list.values())]

    def due_paid_amount(self):
        """Dashboard : Due / Paid Amount"""
        company_domain = [('company_id', 'in', self.env.companies.ids)]
        sold = {}
        tenancy = {}
        not_paid_amount_sold = 0.0
        paid_amount_sold = 0.0
        not_paid_amount_tenancy = 0.0
        paid_amount_tenancy = 0.0
        property_sold = self.env['account.move'].sudo().search(
            [('sold_id', '!=', False)] + company_domain)
        for data in property_sold:
            if data.sold_id.stage == "sold":
                if data.payment_state == "not_paid":
                    not_paid_amount_sold = not_paid_amount_sold + data.amount_total
                if data.payment_state == "paid":
                    paid_amount_sold = paid_amount_sold + data.amount_total
        sold['Due'] = not_paid_amount_sold
        sold['Paid'] = paid_amount_sold
        property_tenancy = self.env['rent.invoice'].sudo().search(company_domain)
        for rec in property_tenancy:
            if rec.payment_state == 'not_paid':
                not_paid_amount_tenancy = not_paid_amount_tenancy + rec.rent_invoice_id.amount_total
            if rec.payment_state == 'paid':
                paid_amount_tenancy = paid_amount_tenancy + rec.rent_invoice_id.amount_total
        tenancy['Due'] = not_paid_amount_tenancy
        tenancy['Paid'] = paid_amount_tenancy
        return [list(sold.keys()), list(sold.values()), list(tenancy.keys()),
                list(tenancy.values())]

    def get_property_map_data(self):
        """Dashboard : Get map data"""
        company_domain = [('company_id', 'in', self.env.companies.ids)]
        data = []
        properties = self.env['property.details'].sudo().search(company_domain)
        for prop in properties:
            if not prop.latitude or not prop.longitude:
                continue
            address_parts = []
            if prop.street:
                address_parts.append(prop.street)
            if prop.city_id and prop.city_id.name:
                address_parts.append(prop.city_id.name)

            address_line = ", ".join(address_parts)
            name_line = prop.name or ""

            if address_line:
                line_length = max(len(name_line), len(address_line)) * 2
                title = f"{name_line}\n{'-' * line_length}\n{address_line}"
            else:
                title = name_line
            data.append({
                'title': title,
                'latitude': prop.latitude,
                'longitude': prop.longitude,
                'status': prop.stage,
            })
        return data


# Area Measurement
class PropertyRoomMeasurement(models.Model):
    """Property Measurement"""
    _name = 'property.room.measurement'
    _description = 'Room Property Measurement Details'
    _rec_name = 'section_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    type_room = fields.Selection([('hall', 'Hall'),
                                  ('bed_room', 'Bed Room'),
                                  ('kitchen', 'Kitchen'),
                                  ('drawing_room', 'Drawing Room'),
                                  ('bathroom', 'Bathroom'),
                                  ('store_room', 'Store Room'),
                                  ('balcony', 'Balcony'),
                                  ('wash_area', 'Wash Area'), ],
                                 string='House Section')
    section_id = fields.Many2one('property.area.type', string="Section", tracking=True)
    length = fields.Integer(string='Length',tracking=True)
    width = fields.Integer(string='Width', tracking=True)
    height = fields.Integer(string='Height', default=1, tracking=True)
    no_of_unit = fields.Integer(string="No of Unit", default=1, tracking=True)
    carpet_area = fields.Integer(string='Total Area',
                                 compute='_compute_carpet_area',
                                 tracking=True)
    measure = fields.Char(string='ft²',
                          default='ft²',
                          readonly=True,
                          translate=True)
    room_measurement_id = fields.Many2one('property.details',
                                          string='Room Details')
    measure_unit = fields.Selection(related="room_measurement_id.measure_unit",
                                    store=True)
    sq_ft = fields.Float(string="Total Square Feet")
    sq_m = fields.Float(string="Total Square Meters")
    sq_yd = fields.Float(string="Total Square Yards")
    cu_ft = fields.Float(string="Total Cubic Feet")
    cu_m = fields.Float(string="Total Cubic Meters")

    @api.depends('length', 'width', 'height', 'measure_unit', 'no_of_unit')
    def _compute_carpet_area(self):
        """Compute total carpet area"""
        for rec in self:
            total = 0.0
            if rec.measure_unit in ['sq_ft', 'sq_m', 'sq_yd']:
                total = rec.length * rec.width * rec.no_of_unit
            elif rec.measure_unit in ['cu_ft', 'cu_m']:
                total = rec.length * rec.width * rec.height * rec.no_of_unit
            rec.carpet_area = total


# Property Documents
class PropertyDocuments(models.Model):
    """Property Documents"""
    _name = 'property.documents'
    _description = 'Document related to Property'
    _rec_name = 'doc_type'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    property_id = fields.Many2one('property.details',
                                  string='Property Name',
                                  readonly=True)
    document_date = fields.Date(string='Date', default=fields.Date.today, tracking=True)
    doc_type = fields.Selection([('photos', 'Photo'),
                                 ('brochure', 'Brochure'),
                                 ('certificate', 'Certificate'),
                                 ('insurance_certificate',
                                  'Insurance Certificate'),
                                 ('utilities_insurance', 'Utilities Certificate')],
                                string='Document Type', required=True,
                                tracking=True)
    document = fields.Binary(string='Documents', required=True, tracking=True)
    file_name = fields.Char(string='File Name', translate=True)


# Property Amentias
class PropertyAmenities(models.Model):
    """Property Amenities"""
    _name = 'property.amenities'
    _description = 'Details About Property Amenities'
    _rec_name = 'title'

    sequence = fields.Integer()
    image = fields.Binary(string='Image')
    title = fields.Char(string='Title', translate=True)


# Property Specification
class PropertySpecification(models.Model):
    """Property Specification"""
    _name = 'property.specification'
    _description = 'Details About Property Specification'
    _rec_name = 'title'

    image = fields.Image(string='Image')
    title = fields.Char(string='Title', translate=True)
    description = fields.Text(string="Description", translate=True)
    description_line1 = fields.Char(string='Description ', translate=True)
    description_line2 = fields.Char(string='Description Line 2',
                                    translate=True)
    description_line3 = fields.Char(string='Description Line 3',
                                    translate=True)


# Property Floor Plan
class FloorPlan(models.Model):
    """Property Flore Plans"""
    _name = 'floor.plan'
    _description = 'Details About Floor Plan'
    _inherit = ["image.mixin"]
    _order = "sequence, id"

    title = fields.Char(string='Title', translate=True)
    sequence = fields.Integer(default=10)
    property_id = fields.Many2one('property.details', string='Property')
    image = fields.Image(string='Image ')
    video_url = fields.Char("Video URL",
                            help="URL of a video for showcasing your property.")
    embed_code = fields.Html(compute="_compute_embed_code",
                             sanitize=False)
    can_image_1024_be_zoomed = fields.Boolean(string="Can Image 1024 be zoomed",
                                              compute="_compute_can_image_1024_be_zoomed",
                                              store=True)

    @api.depends("image", "image_1024")
    def _compute_can_image_1024_be_zoomed(self):
        """Compute image can be zoomed or  not"""
        for image in self:
            image.can_image_1024_be_zoomed = image.image and is_image_size_above(image.image,
                                                                                 image.image_1024)

    @api.onchange("video_url")
    def _onchange_video_url(self):
        """Onchange video URL"""
        if not self.image:
            thumbnail = get_video_thumbnail(self.video_url)
            self.image = thumbnail and base64.b64encode(thumbnail).decode() or False

    @api.depends("video_url")
    def _compute_embed_code(self):
        """Compute embed code"""
        for image in self:
            image.embed_code = get_video_embed_code(image.video_url) or False

    @api.constrains("video_url")
    def _check_valid_video_url(self):
        """Check video url is valid or not"""
        for image in self:
            if image.video_url and not image.embed_code:
                raise ValidationError(_("Provided video URL for '%s' is not valid. "
                                        "Please enter a valid video URL.", image.name, ))


# Property Images
class PropertyImages(models.Model):
    _name = 'property.images'
    _description = 'Property Images'
    _inherit = ["image.mixin"]
    _order = "sequence, id"
    _rec_name = "title"

    title = fields.Char(string='Title', translate=True)
    sequence = fields.Integer(default=10)
    property_id = fields.Many2one('property.details',
                                  string='Property Name',
                                  readonly=True)
    image = fields.Image(string='Images')
    video_url = fields.Char("Video URL",
                            help="URL of a video for showcasing your property.")
    embed_code = fields.Html(compute="_compute_embed_code",
                             sanitize=False)
    can_image_1024_be_zoomed = fields.Boolean(string="Can Image 1024 be zoomed",
                                              compute="_compute_can_image_1024_be_zoomed",
                                              store=True)

    @api.depends("image", "image_1024")
    def _compute_can_image_1024_be_zoomed(self):
        """Compute image can be zoomed or not"""
        for image in self:
            image.can_image_1024_be_zoomed = image.image and is_image_size_above(image.image,
                                                                                 image.image_1024)

    @api.onchange("video_url")
    def _onchange_video_url(self):
        """Onchange video url"""
        if not self.image:
            thumbnail = get_video_thumbnail(self.video_url)
            self.image = thumbnail and base64.b64encode(thumbnail).decode() or False

    @api.depends("video_url")
    def _compute_embed_code(self):
        """Compute embed code"""
        for image in self:
            image.embed_code = get_video_embed_code(image.video_url) or False

    @api.constrains("video_url")
    def _check_valid_video_url(self):
        """Check video url is valid or not"""
        for image in self:
            if image.video_url and not image.embed_code:
                raise ValidationError(_("Provided video URL for '%s' is not valid."
                                        " Please enter a valid video URL.",
                                        image.name, ))


# Property Tags
class PropertyTag(models.Model):
    _name = 'property.tag'
    _description = 'Property Tags'
    _rec_name = 'title'

    title = fields.Char(string='Title', translate=True)
    color = fields.Integer(string='Color')


# Utility Service
class TenancyExtraService(models.Model):
    """Extra Service Product"""
    _inherit = 'product.product'

    is_extra_service_product = fields.Boolean(string="Is Extras Service")


# Utility Service Line
class ExtraServiceLine(models.Model):
    """Extra Service Line"""
    _name = 'extra.service.line'
    _description = "Tenancy Extras Service"
    _rec_name = 'service_id'

    service_id = fields.Many2one('product.product',
                                 string="Service",
                                 domain=[('type','=','service')])
    price = fields.Float(string="Cost")
    service_type = fields.Selection([('once', 'Once'),
                                     ('monthly', 'Recurring')],
                                    string="Type",
                                    default="once")
    property_id = fields.Many2one('property.details',
                                  string="Property")

    @api.onchange('service_id')
    def _onchange_service_id_price(self):
        """Service price bases product"""
        for rec in self:
            if rec.service_id:
                rec.price = rec.service_id.lst_price


# City
class PropertyResCity(models.Model):
    """Res City"""
    _name = 'property.res.city'
    _description = 'Cities'

    color = fields.Integer('Color')
    name = fields.Char(string="City Name", required=True, translate=True)


# Property Connectivity
class PropertyConnectivity(models.Model):
    """Property Connectivity"""
    _name = 'property.connectivity'
    _description = "Property Nearby Connectivity"

    name = fields.Char(string="Title", translate=True)
    distance = fields.Char(string="Distance", translate=True)
    image = fields.Image(string='Images')


# Property Connectivity Line
class PropertyConnectivityLine(models.Model):
    """Property Connectivity Line"""
    _name = 'property.connectivity.line'
    _description = "Property Connectivity Line"

    property_id = fields.Many2one('property.details')
    connectivity_id = fields.Many2one('property.connectivity',
                                      string="Nearby Connectivity")
    name = fields.Char(string="Name", translate=True)
    image = fields.Image(related="connectivity_id.image", string='Images')
    distance = fields.Char(string="Distance", translate=True)


# Tenancy Inquiry
class TenancyInquiry(models.Model):
    """Rent Inquiry Leas"""
    _name = 'tenancy.inquiry'
    _description = "Rent Inquiry"
    _rec_name = 'lead_id'

    property_id = fields.Many2one('property.details',
                                  string="Property Details")
    note = fields.Text(string="Note", translate=True)
    duration_id = fields.Many2one('contract.duration', string='Duration')
    customer_id = fields.Many2one('res.partner', string="Customer")
    lead_id = fields.Many2one('crm.lead', string="Lead")


# Sale Inquiry
class SaleInquiry(models.Model):
    """Sale Inquiry Lead"""
    _name = 'sale.inquiry'
    _description = "Sale Inquiry"
    _rec_name = 'lead_id'

    property_id = fields.Many2one('property.details',
                                  string="Property Details")
    note = fields.Text(string="Note", translate=True)
    company_id = fields.Many2one('res.company',
                                 string='Company',
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency',
                                  related='company_id.currency_id',
                                  string='Currency')
    ask_price = fields.Monetary(string="Ask Price")
    customer_id = fields.Many2one('res.partner',
                                  string="Customer")
    lead_id = fields.Many2one('crm.lead',
                              string="Lead")


# Property Area Type
class PropertyAreaType(models.Model):
    """Property area types"""
    _name = 'property.area.type'
    _description = "Property Area Type"

    name = fields.Char(string="Title")
    type = fields.Selection([('room', 'Rooms'),
                             ('bathroom', 'Bathrooms'),
                             ('parking', 'Parking'),
                             ('hall', 'Hall'),
                             ('kitchen', 'Kitchen'),
                             ('other', 'Other')], string="Type")


# Property Sub Type
class PropertySubType(models.Model):
    """Property subtype"""
    _name = 'property.sub.type'
    _description = "Property Sub Type"

    name = fields.Char(string="Title")
    type = fields.Selection([('land', 'Land'),
                             ('residential', 'Residential'),
                             ('commercial', 'Commercial'),
                             ('industrial', 'Industrial')],
                            string="Type")
    sequence = fields.Integer()


# Furnishing Type
class PropertyFurnishing(models.Model):
    """Property Furnishing"""
    _name = 'property.furnishing'
    _description = "Property Furnishing"

    name = fields.Char(string="Title")


# Increment history
class IncrementHistory(models.Model):
    """Increment History"""
    _name = 'increment.history'
    _description = "Increment History"
    _rec_name = "contract_ref"

    property_id = fields.Many2one('property.details', string="Property")
    date = fields.Date(string="Date", default=fields.Date.today)
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id',
                                  string='Currency')
    contract_ref = fields.Char(string="Contract Ref.")
    rent_type = fields.Selection([('fixed', 'Fixed'), ('area_wise', 'Area Wise')],
                                 string="Pricing Type")
    rent_increment_type = fields.Selection([('fix', 'Fix Amount'), ('percentage', 'Percentage')],
                                           string="Increment Type", default="fix")
    increment_percentage = fields.Float(string="Increment(%)", default=1)
    increment_amount = fields.Monetary(string="Increment Amount")
    previous_rent = fields.Monetary(string="Previous Rent")
    incremented_rent = fields.Monetary(string="Final Rent")
