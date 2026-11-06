import base64
from odoo import http
from odoo.http import request
from ...rental_management.controllers.main import RentalPortalWebsite


class RentalPortalWebsiteInherit(RentalPortalWebsite):

    @http.route(['/my/rent-contract/information/maintenance-request'], type='http', auth="user",
                website=True)
    def rental_rent_maintenance_request(self, **kw):
        res = super(RentalPortalWebsiteInherit, self).rental_rent_maintenance_request(**kw)
        request_record = request.env['maintenance.request'].sudo().search([], order='create_date desc', limit=1)
        # request_record = res.qcontext.get('request')
        if not request_record:
            return res
        files = request.httprequest.files.getlist('attachments')
        preferred_dt = kw.get('client_preferred_time')
        priority = kw.get('priority')
        current_user = request.env.user.id

        if preferred_dt:
            preferred_dt = preferred_dt.replace("T", " ")
            request_record.sudo().write({
                'client_preferred_time': preferred_dt
            })

        request_record.sudo().write({
            'mr_created_person_id': current_user
        })
        if priority:
            request_record.sudo().write({
                'priority': priority
            })

        real_files = [f for f in files if f.filename] 
        if real_files:
            attachment_ids = []
            for file_storage in files:
                file_data = file_storage.read()
                attachment = request.env['ir.attachment'].sudo().create({
                    'name': file_storage.filename,
                    'raw': file_data,
                    'type': 'binary',
                    'res_model': 'maintenance.request',
                    'res_id': request_record.id,
                    'mimetype': file_storage.content_type,
                })
                attachment_ids.append(attachment.id)

            if attachment_ids:
                request_record.write({'attachment_ids': [(6, 0, attachment_ids)]})

        template = request.env.ref('ribs_real_estate.email_template_mr_creation').sudo()
        contract = request.env['tenancy.details'].sudo().search([('id','=',request_record.rent_contract_id.id)])
        
        emails = (
            contract.property_id.maintenance_person_ids.mapped('work_email')
            + [contract.property_landlord_id.email]
            + [contract.responsible_id.login]
        )

        email_to = ",".join(filter(None, emails))
        if template:
            email_values = {
                'email_from': request.env.company.email,
                'email_to': email_to,
            }
            template.sudo().send_mail(request_record.id, force_send=True, email_values=email_values)

        return res

    @http.route(['/my/rent-contract/termination-request'], type='http', auth="user", website=True)
    def rental_rent_termination_request(self, **kw):

        tenancy_id = request.env['tenancy.details'].sudo().browse(
            int(kw.get('rent') or 0)
        )

        if not tenancy_id.exists():
            return request.redirect('/my')

        reason = kw.get('termination_reason')
        preferred_time = kw.get('preferred_closing_time')

        template = request.env.ref(
            'ribs_real_estate.termination_request_portal',
            raise_if_not_found=False
        )

        leasing_group = request.env.ref(
            'rental_management.property_rental_manager'
        ).sudo()

        leasing_team_emails = leasing_group.all_user_ids.mapped('email')

        email_list = list(filter(None, leasing_team_emails))

        if template and email_list:
            template.with_context(
                reason=reason,
                preferred_time=preferred_time
            ).sudo().send_mail(
                tenancy_id.id,
                email_values={
                    'email_to': ','.join(email_list),
                },
                force_send=True,
            )

            request.session['website_notification'] = {
                'type': 'success',
                'message': 'Termination request sent successfully!'
            }

            url = f"/my/rent-contract/information/{tenancy_id.tenancy_seq.replace('/', '-').lower()}-{tenancy_id.id}"

        return request.redirect(url)

    @http.route(['/my/rent-contract/renewal-request'], type='http', auth="user", website=True)
    def rental_rent_renewal_request(self, **kw):

        tenancy_id = request.env['tenancy.details'].sudo().browse(
            int(kw.get('rent') or 0)
        )

        if not tenancy_id.exists():
            return request.redirect('/my')

        note = kw.get('renewal_note')

        template = request.env.ref(
            'ribs_real_estate.renewal_request_portal',
            raise_if_not_found=False
        )

        leasing_group = request.env.ref(
            'rental_management.property_rental_manager'
        ).sudo()

        leasing_team_emails = leasing_group.all_user_ids.mapped('email')
        manager_email = tenancy_id.property_id.property_manager.work_email


        email_list = list({
                email
                for email in [manager_email, *leasing_team_emails]
                if email
            })

        if template and email_list:
            template.with_context(
                note=note).sudo().send_mail(
                tenancy_id.id,
                email_values={
                    'email_to': ','.join(email_list),
                },
                force_send=True,
            )

            request.session['website_notification'] = {
                'type': 'success',
                'message': 'Renewal request sent successfully!'
            }
        url = f"/my/rent-contract/information/{tenancy_id.tenancy_seq.replace('/', '-').lower()}-{tenancy_id.id}"

        return request.redirect(url)