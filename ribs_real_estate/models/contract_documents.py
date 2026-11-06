from odoo.exceptions import ValidationError, UserError
from odoo import api, fields, models, _


class Documents(models.Model):
    _name = 'document.document'
    _description = "Document Document"
    _unique_document_name = models.Constraint(
        'unique(name)',
        'Document with this name already exists!',
    )
    
    name = fields.Char(string='Name')
    document_for = fields.Selection([
        ('b2b', 'B2B'), ('b2c', 'B2C'), ('welcome_pack', 'Welcome Pack'), ('others', 'Others')
    ], default='others')
    is_mandatory = fields.Boolean(string="Is Mandatory", default=False)

    
class ContractDocuments(models.Model):
    _name = 'contract.documents'
    _rec_name = 'document_name'
    _description = "Contract Documents"
    
    document_name = fields.Char(related='document_id.name')
    contract_id = fields.Many2one('tenancy.details')
    document_ids = fields.Many2many('document.document', string="Documents",
                                    compute="_compute_document_ids")
    document_id = fields.Many2one('document.document', string="Document Name", required=True)
    attachments = fields.Many2many(
        'ir.attachment',
        'contract_documents_attachment_rel',
        'contract_document_id',
        'attachment_id',
        string="Attachments",
        required=True
    )
    expiry_date = fields.Date(string='Expiry Date')
    include_in_email = fields.Boolean(string='Send In Welcome Pack', default=False)
    notes = fields.Text(string="Notes")
    
    @api.onchange('expiry_date')
    def _onchange_expiry_date(self):
        if self.expiry_date and self.expiry_date < fields.Date.today():
            raise ValidationError('Expiry date cannot be in the Past')

    @api.depends('contract_id.tenancy_id.company_types')
    def _compute_document_ids(self):
        for rec in self:
            document_record = self.env['document.document']
            domain = [('document_for', 'in', ['welcome_pack','others'])]
            docs = document_record.search(domain)
            rec.document_ids = docs   

    @api.onchange('document_id')
    def _onchange_document_id(self):
        for record in self:
            if record.document_id:
                existing_record = self.search([
                    ('contract_id', '=', record.contract_id.id),
                    ('document_id', '=', record.document_id.id),
                    ('id', '!=', record.id),
                ])
                if existing_record:
                    raise ValidationError(_('''This document has already been added. Please select a different document or delete the existing one.'''))

    
class ClearanceCertificate(models.Model):
    _name = 'issue.clearance.certificate'
    _description = "Issue Clearance Certificate"
    
    contract_id = fields.Many2one('tenancy.details', required=True)
    issue_clearance_certificate = fields.Many2many('ir.attachment', string='Attachements', required=True)
    
    def send_issue_clearance(self):
        self.ensure_one()
        contract_id = self.env.context.get('default_contract_id')

        if not contract_id:
            raise UserError("No contract ID found in context.")

        document_name = self.env['document.document'].search([('name', '=', 'Issue Clearance Certificate')], limit=1)
        if not document_name:
            document_name = self.env['document.document'].create({
                'name': 'Issue Clearance Certificate'
            })

        self.env['contract.documents'].create({
            'contract_id': contract_id,
            'document_id': document_name.id,
            'attachments': self.issue_clearance_certificate,  
            'expiry_date': fields.Date.today(),
            'include_in_email': False,
        })

        template = self.env.ref('ribs_real_estate.send_issue_clearance_template', raise_if_not_found=False)

        email_values = {
            'email_from': self.env.company.email,
            'email_to': self.contract_id.tenancy_id.email,
            'attachment_ids': self.issue_clearance_certificate.ids, 
        }

        template.send_mail(self.id, force_send=True, email_values=email_values)

        return True


