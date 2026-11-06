from odoo import models, fields, api    
from odoo.exceptions import UserError
from datetime import timedelta

class DocumentRequest(models.TransientModel):
    _name = 'document.request'
    _description = 'Document Request'

    contract_id = fields.Many2one('tenancy.details', string='Contract',readonly=True, required=True)
    available_document_ids = fields.Many2many('document.document', compute='_compute_available_document_ids')
    document_ids = fields.Many2many('document.document',string='Document Name')
    request_sent_at = fields.Datetime("Request Sent At")
    document_uploaded = fields.Boolean("Document Uploaded", default=False)


    @api.depends('contract_id.tenancy_id.company_types')
    def _compute_available_document_ids(self): 
        for rec in self:

            if rec.contract_id.tenancy_id.company_types:
                domain = [('document_for', '=', 'b2b')]
            else:
                domain = [('document_for', '=', 'b2c')]

            domain.append(('is_mandatory', '=', True))

            accepted_docs = self.env['partner.documents'].search([
                ('partner_id', '=', rec.contract_id.tenancy_id.id),
                ('verified_status', '=', 'accepted')
            ]).mapped('document_id').ids

            if accepted_docs:
                domain.append(('id', 'not in', accepted_docs))

            documents = self.env['document.document'].search(domain)
            rec.available_document_ids = [(6, 0, documents.ids)]
            # rec.document_ids = [(6, 0, documents.ids)]


    @api.model
    def upload_document_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
        return f'{base_url}/my/documents/upload/{self.contract_id.id}'

    def action_request_contract(self):
        self.ensure_one()
        tenant = self.contract_id.tenancy_id
        if not tenant:
            return 

        already_uploaded_docs = self.env['partner.documents'].search([
            ('partner_id', '=', tenant.id),
            ('document_id', 'in', self.document_ids.ids),
            ('verified_status', '=', 'accepted')
        ])

        if already_uploaded_docs:
            uploaded_doc_names = ", ".join(already_uploaded_docs.mapped('document_id.name'))
            raise UserError(
                f"The following documents have already been uploaded by the tenant:\n\n"
                f"{uploaded_doc_names}\n\n"
                f"Please remove them from the selection or delete the existing uploads first."
            )

        tenant_partner = self.contract_id.tenancy_id

        user = self.env['res.users'].sudo().search([('partner_id', '=', tenant_partner.id)], limit=1)

        if not user or not user.has_group('base.group_portal'):
            raise UserError("The tenant does not have portal access. Please grant portal access to the tenant before sending the document request.")

        self.request_sent_at = fields.Datetime.now()
        expiry_time = self.request_sent_at + timedelta(minutes=30)

        template = self.env.ref('ribs_real_estate.email_template_request_documents')
        if template:
            template.with_context(
                expiry_time=expiry_time,
                request_link="/my/documents/upload/%s" % self.contract_id.id
            ).send_mail(self.id, force_send=True, 
            email_values={'email_from': self.env.company.email, 'email_to': self.contract_id.tenancy_id.email})

        return True

