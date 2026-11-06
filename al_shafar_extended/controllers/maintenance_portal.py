# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class MaintenanceTenantFeedbackController(http.Controller):

    @http.route(['/my/maintenance-request/information/<model("maintenance.request"):mr>/feedback'],
                type='http', auth='user', website=True, methods=['POST'])
    def maintenance_tenant_feedback(self, mr, **kw):
        tenancies = request.env['tenancy.details'].sudo().search(
            [('tenancy_id', '=', request.env.user.partner_id.id)]).ids
        if mr.sudo().tenancy_id.id not in tenancies:
            return request.redirect('/my/maintenance-request/')

        mr.sudo().action_tenant_feedback(
            resolved=kw.get('resolved') == 'yes',
            rating=kw.get('rating') or False,
            comment=kw.get('comment') or False,
        )
        return request.redirect(
            '/my/maintenance-request/information/%s' % request.env['ir.http']._slug(mr))
