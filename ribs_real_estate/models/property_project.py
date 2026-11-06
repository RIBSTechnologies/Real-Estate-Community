import base64
from odoo import api, fields, models, _
from odoo.tools.image import is_image_size_above
from odoo.exceptions import ValidationError, AccessError
from odoo.addons.rental_management.tools import get_video_embed_code, get_video_thumbnail


class PropertyProject(models.Model):

    _inherit = "property.project"

    project_for = fields.Selection(default="rent")
    property_subtype_id = fields.Many2one("property.sub.type",
                                          string="Property Subtype",
                                          required=False,
                                          domain="[('type','=',property_type)]")
    building_for = fields.Selection([("rent", "Rent")], string="Building For", default="rent")
    parking_ids = fields.Many2many('parking.slots', string='Parking Slots',
                                   compute='_compute_parking_slots')
    maintenance_person_ids = fields.Many2many('hr.employee', string='Maintenance Team', required=True)
    property_manager = fields.Many2one('hr.employee', string='Property Manager', required=True)
    security_id = fields.Many2one('res.partner', string='Security', required=True, domain=[('user_type', '=', 'security')])
    security_number = fields.Char(string='Security Number', compute='_compute_security_number')
    is_sub_project = fields.Boolean(default=False)
    dewa_reading = fields.Boolean('Dewa Meter Reading', default=False)
    meter_type = fields.Many2one('dewa.meter.reading.type', string="Meter Type")
    reading = fields.Char(string="Reading (kWh / m³)")
    reading_date = fields.Date(string="Reading Date", default=fields.Date.today)
    date_of_project = fields.Date(string="Date of Project", tracking=True, required=False)
    land_number = fields.Char(string="Plot No", tracking=True)
    dewa_number = fields.Char(string="DEWA Number", tracking=True)
    makani_number = fields.Char(string='Makani Number', tracking=True)

    # Accounting Configuration
    # Tenancy Contract
    invoice_creation_id = fields.Many2one('account.account', 'Account for Accounts Receivable (Dr.)')
    account_security_deposit_id = fields.Many2one('account.account', 'Account for Security Deposit (Cr.)')
    income_account_id = fields.Many2one('account.account', 'Account for Income (Cr.)')
    deffered_income_account_id = fields.Many2one('account.account', 'Account for Deferred Income (Cr.)')
    account_retention_id = fields.Many2one('account.account', 'Account for Retention (Dr.)')
    # Payments Received
    cash_receipt_id = fields.Many2one('account.journal', 'Deposit Account for Cash (Dr.)', domain=[('type', 'in', ['cash','bank'])])
    current_date_cheque_id = fields.Many2one('account.account', 'Deposit Account for Current Date Cheque (Dr.)')
    cuc_account_id = fields.Many2one('account.journal', 'Deposit Account for CUC (Dr.)', domain=[('type', 'in', ['cash','bank'])])
    default_bank_account_id = fields.Many2one(
        'res.partner.bank',
        string='Default Bank Account for CUC (Dr.)',
        domain=lambda self: [
            ('partner_id', '=', self.env.user.company_id.partner_id.id)
        ],
    )
    # commercial_subtype_id = fields.Many2one("commercial.sub.type", string="Commercial Subtype")

    is_individual = fields.Boolean(related='property_subtype_id.is_individual_building')
    property_owner = fields.Many2one('res.partner', string='Owner', domain="[('user_type', 'in', ['owner', 'landlord'])]")
    property_age = fields.Integer(string='Age of Property')
    building_contract_increment = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')],
                                           string="Increment Type", default="percentage", required=True)
    contract_increment_percentage = fields.Float('Percentage')
    contract_increment_amount = fields.Monetary('Amount')

    # Bank Accounts for Building
    rent_bank_account_id = fields.Many2one('account.journal', string='Rent Bank Accounts', domain=['|', ('type', 'in', ['bank','cash']), ('is_pdc_journal','=',True)])
    vat_sec_bank_account_id = fields.Many2one('account.journal', string='VAT Bank Accounts', domain=['|', ('type', 'in', ['bank','cash']), ('is_pdc_journal','=',True)])
    security_bank_account_id = fields.Many2one('account.journal', string='Security Deposit Bank Accounts', domain=['|', ('type', 'in', ['bank','cash']), ('is_pdc_journal','=',True)])

    property_type_account_id = fields.Many2one(
        'account.analytic.account',
        string='Property Type Account',
        domain="[('plan_id.customized_type', '=', 'property_type')]",
    )

    building_account_id = fields.Many2one(
        'account.analytic.account',
        string='Building Analytic Account',
        domain="[('plan_id.customized_type', '=', 'building')]",
    )

    def _compute_parking_slots(self):
        for project in self:
            allocations = self.env['parking.allocation'].search([('project_id', '=', project.id)])
            project.parking_ids = allocations.mapped('parking_ids')

    @api.onchange('building_contract_increment', 'contract_increment_percentage', 'contract_increment_amount')
    def _update_contract(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError("Only Admin can perform this action.")

    def action_create_unit(self):
      self.ensure_one()
      return {
          'name': _('Create Unit'),
          'type': 'ir.actions.act_window',
          'view_mode': 'form',
          'res_model': 'property.details',
          'target': 'new',
          'context': {
              'default_property_project_id': self.id,
          }
      }

    @api.onchange('property_manager')
    def _onchange_property_manager(self):
        if self.property_manager and not self.property_manager.work_email:
            raise ValidationError(_("Add Property Manager Email "))


    @api.onchange('maintenance_person_ids')
    def _onchange_maintenance_person_ids(self):
        missing_emails = []
        if self.maintenance_person_ids:
            for employee in self.maintenance_person_ids :
                if not employee.work_email:
                    missing_emails.append(employee.name)

            if missing_emails:
                return {
                    'warning': {
                        'title': _("Missing Email(s)"),
                        'message': _("The following team members have no email set: %s") % ', '.join(missing_emails)
                    }
                }
    
    def create_units(self):
        return {
            'name': _('Create Units'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'unit.creation',
            'target': 'new',
            'context': {
                'project_id': self.id,
                'property_type':self.property_type,
                'property_subtype_id':self.property_subtype_id.id,
                'is_individual':self.is_individual,
                'unit_from':'project'
            }
        }

    @api.depends('security_id.phone')
    def _compute_security_number(self):
        for rec in self:
            if rec.security_id and rec.security_id.exists():
                rec.security_number = rec.security_id.phone
            else:
                rec.security_number = False

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            increment_type = rec.building_contract_increment
            percentage = rec.contract_increment_percentage
            amount = rec.contract_increment_amount
            if increment_type == 'percentage' and percentage < 1:
                raise ValidationError("Increment Percentage is required.")

            if increment_type == 'amount' and amount < 1:
                raise ValidationError("Increment Amount is required.")
        return res
    
    def action_assign_project(self):
        buildings = self.env['property.project'].search([])
        for building in buildings:
            project = self.env['project.project'].search([('name', '=', building.name)])
            building.project_id = project.id if project else False
  
class CommercialSubType(models.Model):
    """Property subtype"""
    _name = 'commercial.sub.type'
    _description = "Commercial Sub Type"

    name = fields.Char(string="Title")





