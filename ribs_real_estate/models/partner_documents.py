from odoo.exceptions import ValidationError, UserError
from odoo import api, fields, models, _


class PartnerDocumentName(models.Model):
    _name = 'partner.document.name'
    _unique_document_name = models.Constraint(
        'unique(name)',
        'Document with this name already exists!',
    )
    _description = "Partner Document Name"
    
    name = fields.Char(string='Name')
    
class PartnerDocuments(models.Model):
    _name = 'partner.documents'
    _rec_name = 'document_name'
    _description = "Partner Documents"
    
    partner_id = fields.Many2one('res.partner', string="Partner")
    document_name = fields.Char(related='document_id.name')
    document_ids = fields.Many2many('document.document', string="Documents",
                                    compute="_compute_document_ids")
    document_id = fields.Many2one('document.document', string="Document Name", required=True)
    attachments = fields.Many2many(
    'ir.attachment',
    'partner_document_attachment_rel',  
    'partner_document_id',              
    'attachment_id',                    
    string='Attachments',
    required=True
    )
    expiry_date = fields.Date(string='Expiry Date')
    notes = fields.Text(string='Notes')
    verified_status = fields.Selection([
        ('pending', 'Pending'),
        ('accepted', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ], string="Verification Status", default='pending', required=True)

    def action_approved_partner_document(self):
        """Status : Available property"""
        active_ids = self.env.context.get('active_ids')
        partner_rec = self.env['partner.documents'].sudo().browse(active_ids)
        for rec in partner_rec:
            if rec.verified_status in ['pending', 'rejected']:
                rec.write({
                    'verified_status': 'accepted'
                })

    def action_accept(self):
        for rec in self:
            existing_accepted = self.search([
                ('partner_id', '=', rec.partner_id.id),
                ('document_id', '=', rec.document_id.id),
                ('verified_status', '=', 'accepted'),
                ('id', '!=', rec.id)
            ])
            if existing_accepted:  
                raise ValidationError(_('This document has already been approved for this partner. Please select a different document or delete the existing approved one.'))
            rec.verified_status = 'accepted'

    def action_reject(self):
        for rec in self:
            rec.verified_status = 'rejected'

    @api.onchange('document_id')
    def _onchange_document_id(self):
        for record in self:
            if record.document_id:
                existing_record = self.search([
                    ('partner_id', '=', record.partner_id.id),
                    ('document_id', '=', record.document_id.id),
                    ('id', '!=', record.id),
                    ('verified_status', '=', 'accepted')
                ])
                if existing_record:
                    raise ValidationError(_('''This document has already been added for this partner. Please select a different document or delete the existing one.'''))

    @api.depends('partner_id.company_types')
    def _compute_document_ids(self):
        for rec in self:
            document_record = self.env['document.document']
            if rec.partner_id.company_types:
                domain = [('document_for', '=', 'b2b')]
            else:
                domain = [('document_for', '=', 'b2c')]
            docs = self.env['document.document'].search(domain)
            rec.document_ids = docs   