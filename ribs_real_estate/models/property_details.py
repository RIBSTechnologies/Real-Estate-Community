from odoo import api, fields, models, tools, _
from odoo.tools.image import is_image_size_above
from odoo.exceptions import ValidationError
from odoo.addons.rental_management.tools import get_video_embed_code, get_video_thumbnail

class PropertyDetails(models.Model):
    _inherit = 'property.details'

    property_subtype_id = fields.Many2one('property.sub.type',
                                          string="Property Sub Type",
                                          domain="[('type','=',type)]",
                                          required=False,
                                          tracking=True)
    property_purpose = fields.Many2one('property.purpose', string="Purpose")

    property_for = fields.Selection([('rent', 'Rent')], string='Property For',default='rent')
    price_yearly = fields.Float(string='Rent', tracking=True)
    parking_ids = fields.Many2many('parking.slots', domain="[('project_id', '=', property_project_id)]")
    dewa_reading = fields.Boolean('Dewa Meter Reading', default=False)
    meter_type = fields.Many2one('dewa.meter.reading.type', string="Meter Type")
    reading = fields.Char(string="Reading (kWh / m³)")
    reading_date = fields.Date(string="Reading Date", default=fields.Date.today)
    maintenance_person_ids = fields.Many2many(related='property_project_id.maintenance_person_ids', string='Maintenance Team')
    property_manager = fields.Many2one(related='property_project_id.property_manager', string='Property Manager',
                                       store=True, readonly=False)
    security_id = fields.Many2one(related='property_project_id.security_id', string='Security')
    security_number = fields.Char(related='property_project_id.security_number', string='Security Number')
    plot_number = fields.Char(string='Plot Number')
    measure_unit = fields.Selection([('sq_ft', 'sq.ft'),
                                     ('sq_m', 'sq.m'),
                                     ('sq_yd', 'sq.yd'),
                                     ('cu_ft', 'cu.ft'),
                                     ('cu_m', 'cu.m')],
                                    default='sq_ft',
                                    string="Area Measurement Unit", tracking=True)
    unit_size = fields.Float(string="Unit Size", tracking=True)

    @api.model
    def get_property_stats(self):
        stats = super().get_property_stats()
        company_domain = [('company_id', 'in', self.env.companies.ids)]
        rent_contract = self.env['tenancy.details'].sudo()
        stats.update({
            'single_contract': rent_contract.search_count(
                [('is_multi_contract', '=', False)] + company_domain),
            'multi_contract': rent_contract.search_count(
                [('is_multi_contract', '=', True)] + company_domain),
            'renewal_contract': rent_contract.search_count(
                [('is_renewed_contract', '=', True)] + company_domain),
            'termination_contract': rent_contract.search_count(
                [('termination_type', '=', 'early')] + company_domain),
        })
        return stats
    # commercial_subtype_id = fields.Many2one(related='property_project_id.commercial_subtype_id', string="Commercial Subtype")
    commercial_subtype_id = fields.Many2one("commercial.sub.type", string="Commercial Subtype")
    dewa_number = fields.Char(string='DEWA Number', related='property_project_id.dewa_number',
                              store=True, readonly=False)
    makani_number = fields.Char(string='Makani Number', related='property_project_id.makani_number')
    dm_no = fields.Char('Plot No', related='property_project_id.land_number')
    balcony = fields.Integer(string='Balcony', default=1, tracking=True)
    maid_rooms = fields.Integer(string='Maid Rooms', default=1, tracking=True)
    persons_allowed = fields.Integer(string='Persons Allowed', default=1, tracking=True)
    property_owner = fields.Many2one('res.partner',
                                  string='Owner', related='property_project_id.property_owner')
    notes = fields.Text(string="Notes")
    description = fields.Text(string="Description")
    deposit_type = fields.Selection([
        ('percent', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ], default='percent', string="Deposit Type")
    deposit_percentage = fields.Float(
        string="Deposit %",
        compute="_compute_deposit_percentage",
        inverse="_inverse_deposit_percentage",
        store=True,
    )
    deposit_amount = fields.Monetary(
        string="Security Deposit",
        currency_field="currency_id",
        compute="_compute_deposit_amount",
        inverse="_inverse_deposit_amount",
        store=True,
        tracking=True,
    )
    tax_id = fields.Many2one('account.tax')
    unit_account_id = fields.Many2one(
        'account.analytic.account',
        string='Unit Analytic Account',
        domain="[('plan_id.customized_type', '=', 'units')]",
    )
    default_product_id = fields.Many2one(
        'product.product',
        string='Default Product'
    )

    @api.depends('price_yearly', 'deposit_type', 'deposit_percentage', 'type')
    def _compute_deposit_amount(self):
        for rec in self:
            if rec.deposit_type == 'percent':
                percentage = rec.deposit_percentage
                rec.deposit_amount = rec.price_yearly * percentage / 100

    def _inverse_deposit_amount(self):
        for rec in self:
            if rec.deposit_type == 'percent' and rec.price_yearly:
                rec.deposit_percentage = (
                    rec.deposit_amount / rec.price_yearly
                ) * 100

    @api.depends('type')
    def _compute_deposit_percentage(self):
        for rec in self:
            rec.deposit_percentage = 5.0

    def _inverse_deposit_percentage(self):
        # Allows manual editing
        pass

    @api.onchange('dewa_reading')
    def onchange_dewa_reading(self):
        if not self._origin or not self._origin.id:
          return

        property_id = self._origin.id  
        running_contracts = self.env['tenancy.details'].search([
            ('property_id', '=', property_id),
            ('contract_type', '=', 'running_contract')
        ])
        if running_contracts:
            raise ValidationError('Meter reading cannot be added while the current contract is still active.')

    @api.onchange('price_yearly')
    def _onchange_price_yearly(self):
        if self.price_yearly:
          self.price = self.price_yearly / 12

    def contract_wiz_action(self):
      if not self.property_project_id.rent_bank_account_id or not self.property_project_id.vat_sec_bank_account_id or not self.property_project_id.security_bank_account_id:
        raise ValidationError('Please update bank account details in the Building in order to proceed.')
      
      if self.property_project_id.status != 'available':
        raise ValidationError('The Building is not ready yet. Please update the status of the Building to "Available" in order to proceed.')
      return {
        'type': 'ir.actions.act_window',
        'name': ('Contract'),
        'res_model': 'contract.wizard',
        'view_mode': 'form',
        'target': 'new'
      }

    def action_assign_analytic_account(self):
        AnalyticAccount = self.env['account.analytic.account'].sudo()
        lang = self.env.context.get('lang', 'en_US')

        props = self.sudo().search([
            ('analytic_account_id', '=', False),
            ('property_project_id', '!=', False),
        ])

        for prop in props:

            prop_project = prop.property_project_id
            if not prop_project:
                continue

            # property.project → project.project → analytic account
            project_account = prop_project.project_id.account_id

            if not project_account or not project_account.plan_id:
              continue

            # Always translated string
            prop_name = prop.with_context(lang=lang).name
            if not prop_name:
                continue

            analytic = AnalyticAccount.with_context(lang=lang).search([
                ('plan_id', '=', project_account.plan_id.id),
                ('name', '=', prop_name),
            ], limit=1)
            

            if analytic:
                prop.write({
                    'analytic_account_id': analytic.id
                })
  
class PropertyPurpose(models.Model):
  _name = 'property.purpose'
  _description = "Property Purpose"

  name = fields.Char(string='Purpose', required=True)
  arabic_name = fields.Char(string='Arabic')
  priority_type = fields.Integer(string='Priority')
