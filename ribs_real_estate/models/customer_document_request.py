from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessDenied
import base64
from werkzeug.datastructures import FileStorage
from odoo.addons.portal.controllers.portal import CustomerPortal
from datetime import datetime, timedelta



class RentalCustomerPortalInherit(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        response = super()._prepare_home_portal_values(counters)

        partner = request.env.user.partner_id
        documents_count = request.env['partner.documents'].sudo().search_count([
            ('partner_id', '=', partner.id)
        ])
        if 'custom_documents_count' in counters:
            response['custom_documents_count'] = documents_count

        return response

    @http.route(['/my/counters'], type='jsonrpc', auth="user", website=True)
    def portal_counters(self):
        counters = super().portal_counters()
        if isinstance(counters, list) and 'documents_count' not in counters:
            counters.append('documents_count')
        return counters


class DocumentUploadPortal(http.Controller):
    @http.route(['/my/documents/upload/<int:contract_id>'], type='http', auth='user', website=True)
    def document_upload_form(self, contract_id, **kwargs):
        contract = request.env['tenancy.details'].sudo().browse(contract_id)

        if not contract or contract.tenancy_id.id != request.env.user.partner_id.id:
            return request.render('ribs_real_estate.portal_upload_forbidden')

        document_request = request.env['document.request'].sudo().search(
            [('contract_id', '=', contract.id)],
            order='create_date desc',
            limit=1
        )

        if document_request and document_request.request_sent_at:
            now = fields.Datetime.now()
            if now > document_request.request_sent_at + timedelta(minutes=30) or document_request.document_uploaded:
                return request.render('ribs_real_estate.portal_upload_expired')

        if not document_request:
            return request.not_found()

        document_names = document_request.document_ids 

        return request.render('ribs_real_estate.portal_upload_form', {
            'contract': contract,
            'document_names': document_names,
        })

    @http.route(['/my/documents/upload/submit'], type='http', auth='user', website=True, csrf=True)
    def submit_document_upload(self, **post):
        contract_id = int(post.get('contract_id'))
        contract = request.env['tenancy.details'].sudo().browse(contract_id)
        partner = contract.tenancy_id
        notes = post.get('notes', '')

        document_request = request.env['document.request'].sudo().search(
            [('contract_id', '=', contract.id)],
            order='create_date desc',
            limit=1
        )

        if document_request and document_request.request_sent_at:
            now = fields.Datetime.now()
            if now > document_request.request_sent_at + timedelta(minutes=30) or document_request.document_uploaded:
                return request.render('ribs_real_estate.portal_upload_expired')

        for key in post:
            if key.startswith('document_'):
                document_id_str = key.replace('document_', '')
                try:
                    document_id = int(document_id_str)
                except ValueError:
                    continue 

                uploaded_files = request.httprequest.files.getlist(key)  
                expiry_date = post.get(f'expiry_{document_id}', False)

                attachment_ids = []
                for uploaded_file in uploaded_files:
                    if uploaded_file and isinstance(uploaded_file, FileStorage):
                        file_data = uploaded_file.read()
                        file_name = uploaded_file.filename

                        attachment = request.env['ir.attachment'].sudo().create({
                            'name': file_name,
                            'raw': file_data,
                            'res_model': 'partner.documents',
                            'res_id': 0,  
                            'type': 'binary',
                        })
                        attachment_ids.append(attachment.id)

                if attachment_ids:
                    partner_doc = request.env['partner.documents'].sudo().create({
                        'partner_id': partner.id,
                        'document_id': document_id,
                        'attachments': [(6, 0, attachment_ids)],
                        'expiry_date': expiry_date if expiry_date else None,
                        'notes': notes,
                    })

                    request.env['ir.attachment'].sudo().browse(attachment_ids).write({
                        'res_id': partner_doc.id
                    })
                    document_request = request.env['document.request'].sudo().search(
                        [('contract_id', '=', contract.id)],
                        order='create_date desc',
                        limit=1
                    )
                    document_request.document_uploaded = True


        return request.render('ribs_real_estate.portal_upload_success')

    @http.route(['/my/documents/upload/inline'], type='http', auth='user', website=True, csrf=True)
    def inline_document_upload(self, **post):
        document_id = int(post.get('document_id'))
        # expiry_date = post.get('expiry_date')
        expiry_date = post.get(f'expiry_{document_id}', False)
        partner_id = int(post.get('partner_id'))
        notes = post.get('notes', '')

        partner = request.env['res.partner'].sudo().browse(partner_id)

        existing_doc = request.env['partner.documents'].sudo().search([
            ('partner_id', '=', partner.id),
            ('document_id', '=', document_id),
            ('verified_status', '=', 'accepted'),
        ], limit=1)

        if existing_doc:
            return request.redirect('/my/documents') 

        uploaded_files = request.httprequest.files.getlist('attachments')
        attachment_ids = []

        for uploaded_file in uploaded_files:
            if uploaded_file and isinstance(uploaded_file, FileStorage):
                file_data = uploaded_file.read()
                file_name = uploaded_file.filename

                attachment = request.env['ir.attachment'].sudo().create({
                    'name': file_name,
                    'raw': file_data,
                    'res_model': 'partner.documents',
                    'res_id': 0,
                    'type': 'binary',
                })
                attachment_ids.append(attachment.id)

        if attachment_ids:
            partner_doc = request.env['partner.documents'].sudo().create({
                'partner_id': partner.id,
                'document_id': document_id,
                'attachments': [(6, 0, attachment_ids)],
                'expiry_date': expiry_date or False,
                'notes': notes,
            })

            request.env['ir.attachment'].sudo().browse(attachment_ids).write({
                'res_id': partner_doc.id,
            })

        return request.redirect('/my/documents')


    @http.route(['/my/documents'], type='http', auth='user', website=True)
    def view_uploaded_documents(self):
        partner = request.env.user.partner_id

        documents = request.env['partner.documents'].sudo().search([
            ('partner_id', '=', partner.id)
        ])

        summary = {
            'total': len(documents),
            'pending': len(documents.filtered(lambda d: d.verified_status == 'pending')),
            'accepted': len(documents.filtered(lambda d: d.verified_status == 'accepted')),
            'rejected': len(documents.filtered(lambda d: d.verified_status == 'rejected')),
        }

        approved_ids = documents.filtered(
            lambda d: d.verified_status == 'accepted'
        ).mapped('document_id').ids

        if partner.company_types:
            doc_domain = [('document_for', '=', 'b2b')]
        else:
            doc_domain = [('document_for', '=', 'b2c')]

        if approved_ids:
            doc_domain.append(('id', 'not in', approved_ids))

        available_docs = request.env['document.document'].sudo().search(doc_domain)

        return request.render('ribs_real_estate.portal_documents_list', {
        'documents': documents,
        'summary': summary,
        'available_docs': available_docs,
        'partner_id': partner.id,
    })


    @http.route(['/my/documents/download/<int:attachment_id>'], type='http', auth='user')
    def download_document(self, attachment_id):
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id)
        if not attachment or not attachment.raw:
            return request.not_found()

        return request.make_response(
            attachment.raw.content,
            headers=[
                ('Content-Type', attachment.mimetype or 'application/octet-stream'),
                ('Content-Disposition', f'attachment; filename="{attachment.name}"')
            ]
        )


