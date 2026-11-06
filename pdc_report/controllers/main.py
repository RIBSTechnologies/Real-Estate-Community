# -*- coding: utf-8 -*-

import io
import xlsxwriter
from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition


class PDCReportController(http.Controller):

    @http.route('/pdc_report/export_xlsx/<int:wizard_id>', type='http', auth='user')
    def export_pdc_xlsx(self, wizard_id, **kw):
        """HTTP controller route to generate and stream PDC Excel report."""
        wizard = request.env['pdc.report.wizard'].browse(wizard_id)
        if not wizard.exists():
            return request.not_found()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        wizard._generate_xlsx_report(workbook)

        workbook.close()
        output.seek(0)

        filename = f"PDC_Cheque_Report_{wizard.date_from}_to_{wizard.date_to}.xlsx"
        headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(filename))
        ]
        return request.make_response(output.getvalue(), headers=headers)
