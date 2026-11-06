from odoo import http
from odoo.http import request

class UserAcceptance(http.Controller):

    @http.route(['/acknowledge/<int:record_id>'], type='http', auth="public", website=True)
    def acknowledge_mail(self, record_id, **kwargs):
        record = request.env['crm.lead'].sudo().browse(record_id)
        if record:
            record.message_post(body="✅ User acknowledged this mail.")
            return request.render("ribs_real_estate.acknowledge_thankyou")
        else:
            pass