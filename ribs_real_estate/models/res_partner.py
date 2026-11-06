from odoo import fields, models, api, _
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_verified = fields.Boolean(string="Is Verified", default=False)
    document_count = fields.Integer(compute='compute_documents_count')
    user_type = fields.Selection(selection_add=[('security', 'Security'), ('owner', 'Owner')])
    nationality = fields.Char('Nationality')
    fax = fields.Char('Fax')
    passport_number = fields.Char('Passport No')
    place_issue = fields.Char('Place of Issue')
    alt_phone = fields.Char('Alt.Phone')
    cc = fields.Char('CC')
    address_memo = fields.Text('Address Memo')
    ship_to = fields.Text('Ship To')
    company_types = fields.Char('Company Types')
    print_cheque = fields.Char('Print Cheque As')
    emirates_id = fields.Char('Emirates ID')
    licence_no = fields.Char('Licence No')


    def compute_documents_count(self):
        for rec in self:
            document_count = self.env['partner.documents'].search_count(
                [('partner_id', 'in', [rec.id])])
            rec.document_count = document_count

    def action_documents_details(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Request',
            'res_model': 'partner.documents',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
            'view_mode': 'kanban,list,form',
            'target': 'current'
        }