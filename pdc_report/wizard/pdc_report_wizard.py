# -*- coding: utf-8 -*-

import io
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class PDCReportState(models.Model):
    _name = 'pdc.report.state'
    _description = 'PDC Cheque State Option'

    name = fields.Char(string="State Name", required=True)
    code = fields.Char(string="State Code", required=True)

    _code_unique = models.Constraint(
        'unique(code)',
        'State code must be unique!',
    )


class PDCReportWizard(models.TransientModel):
    _name = 'pdc.report.wizard'
    _description = 'PDC Cheque Payment Report Wizard'

    date_from = fields.Date(
        string="Date From",
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    date_to = fields.Date(
        string="Date To",
        required=True,
        default=lambda self: fields.Date.today()
    )
    date_filter_by = fields.Selection([
        ('due_date', 'Cheque Due Date'),
        ('payment_date', 'Payment / Receipt Date')
    ], string="Date Filter Field", default='due_date', required=True)

    payment_type = fields.Selection([
        ('receive_money', 'Customer (Receive Money)'),
        ('send_money', 'Vendor (Send Money)'),
        ('all', 'All Payments (Customer & Vendor)')
    ], string="Payment Type", default='receive_money', required=True)

    partner_ids = fields.Many2many(
        'res.partner',
        'pdc_report_wizard_partner_rel',
        'wizard_id',
        'partner_id',
        string="Customer / Partner Selection",
        help="Select specific customer(s)/partner(s). Leave blank to include all partners."
    )

    state_ids = fields.Many2many(
        'pdc.report.state',
        'pdc_report_wizard_state_rel',
        'wizard_id',
        'state_id',
        string="Cheque States Selection",
        help="Select specific state(s). Leave blank to include ALL states."
    )

    report_type = fields.Selection([
        ('pdf', 'PDF Report'),
        ('xlsx', 'Excel (XLSX) Report')
    ], string="Report Format", default='pdf', required=False)

    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        self._ensure_pdc_states()
        return res

    @api.model
    def _ensure_pdc_states(self):
        """Ensure default state options exist in database."""
        State = self.env['pdc.report.state']
        states_data = [
            ('draft', 'Draft'),
            ('registered', 'Registered'),
            ('hold', 'On Hold'),
            ('deposited', 'Deposited'),
            ('bounced', 'Bounced'),
            ('done', 'Done / Paid'),
            ('returned', 'Returned'),
            ('cancel', 'Cancelled'),
        ]
        for code, name in states_data:
            if not State.search([('code', '=', code)], limit=1):
                State.create({'code': code, 'name': name})

    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        """Reset partner selection domain when payment type changes."""
        self.partner_ids = False

    def _get_pdc_domain(self):
        """Construct domain for searching pdc.wizard records based on user filter selections."""
        self.ensure_one()
        date_field = self.date_filter_by or 'due_date'
        domain = [
            (date_field, '>=', self.date_from),
            (date_field, '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]

        if self.payment_type != 'all':
            domain.append(('payment_type', '=', self.payment_type))

        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))

        if self.state_ids:
            domain.append(('state', 'in', self.state_ids.mapped('code')))

        return domain

    def _get_pdc_records(self):
        """Fetch matching PDC records ordered by due date, partner, and name."""
        self.ensure_one()
        domain = self._get_pdc_domain()
        return self.env['pdc.wizard'].search(domain, order='due_date asc, partner_id asc, name asc')

    def action_print_report(self):
        """Main action handler for wizard submission."""
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError(_("Date From cannot be greater than Date To."))

        records = self._get_pdc_records()
        if not records:
            raise UserError(_("No PDC Cheque records found matching the selected filter criteria."))

        if self.report_type == 'pdf':
            return self.action_print_pdf()
        else:
            return self.action_export_xlsx()

    def action_print_pdf(self):
        """Action handler to trigger PDF QWeb report generation."""
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError(_("Date From cannot be greater than Date To."))

        records = self._get_pdc_records()
        if not records:
            raise UserError(_("No PDC Cheque records found matching the selected filter criteria."))

        return self.env.ref('pdc_report.action_report_pdc_cheque_pdf').report_action(self)

    def action_export_xlsx(self):
        """Action handler to trigger Excel spreadsheet download via controller."""
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError(_("Date From cannot be greater than Date To."))

        records = self._get_pdc_records()
        if not records:
            raise UserError(_("No PDC Cheque records found matching the selected filter criteria."))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/pdc_report/export_xlsx/{self.id}',
            'target': 'self',
        }

    def _generate_xlsx_report(self, workbook):
        """Generate high-quality Excel report workbook for PDC Cheque Payments."""
        self.ensure_one()
        sheet = workbook.add_worksheet('PDC Cheque Report')
        sheet.set_zoom(95)
        sheet.freeze_panes(10, 0)

        # Palette colors
        NAVY_BG     = '#1E3A8A'
        NAVY_FG     = '#FFFFFF'
        HEADER_BG   = '#2563EB'
        SECTION_BG  = '#E0F2FE'
        SECTION_FG  = '#0369A1'
        ROW_W       = '#FFFFFF'
        ROW_G       = '#F8FAFC'
        BORDER_CLR  = '#CBD5E1'
        GRAND_BG    = '#0F172A'
        GRAND_FG    = '#FFFFFF'
        MUTED_TXT   = '#64748B'

        # Formats
        f_co_name = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 16, 'bold': True,
            'font_color': NAVY_BG, 'align': 'left', 'valign': 'vcenter'
        })
        f_co_addr = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 9, 'font_color': MUTED_TXT,
            'align': 'left', 'valign': 'vcenter'
        })
        f_title = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 12, 'bold': True,
            'font_color': '#1E293B', 'align': 'left', 'valign': 'vcenter'
        })

        f_meta_lbl = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 9, 'bold': True,
            'bg_color': '#F1F5F9', 'font_color': '#334155', 'align': 'right',
            'border': 1, 'border_color': BORDER_CLR, 'valign': 'vcenter'
        })
        f_meta_val = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 9, 'bg_color': '#FFFFFF',
            'font_color': '#0F172A', 'align': 'left', 'border': 1,
            'border_color': BORDER_CLR, 'valign': 'vcenter'
        })

        f_col_hdr = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 9.5, 'bold': True,
            'bg_color': NAVY_BG, 'font_color': NAVY_FG, 'align': 'center',
            'valign': 'vcenter', 'text_wrap': True, 'border': 1, 'border_color': '#0F172A'
        })

        f_sec_hdr = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 10, 'bold': True,
            'bg_color': SECTION_BG, 'font_color': SECTION_FG, 'align': 'left',
            'valign': 'vcenter', 'border': 1, 'border_color': BORDER_CLR
        })

        def get_row_formats(bg):
            return {
                'txt_l': workbook.add_format({
                    'font_name': 'Calibri', 'font_size': 9, 'bg_color': bg,
                    'align': 'left', 'valign': 'vcenter', 'border': 1, 'border_color': BORDER_CLR
                }),
                'txt_c': workbook.add_format({
                    'font_name': 'Calibri', 'font_size': 9, 'bg_color': bg,
                    'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': BORDER_CLR
                }),
                'date': workbook.add_format({
                    'font_name': 'Calibri', 'font_size': 9, 'bg_color': bg,
                    'align': 'center', 'valign': 'vcenter', 'num_format': 'dd-mmm-yyyy',
                    'border': 1, 'border_color': BORDER_CLR
                }),
                'num': workbook.add_format({
                    'font_name': 'Calibri', 'font_size': 9, 'bg_color': bg,
                    'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0.00',
                    'border': 1, 'border_color': BORDER_CLR
                }),
                'bold_l': workbook.add_format({
                    'font_name': 'Calibri', 'font_size': 9, 'bold': True, 'bg_color': bg,
                    'align': 'left', 'valign': 'vcenter', 'border': 1, 'border_color': BORDER_CLR
                }),
            }

        f_row_w = get_row_formats(ROW_W)
        f_row_g = get_row_formats(ROW_G)

        f_sub_lbl = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 9.5, 'bold': True,
            'bg_color': '#E2E8F0', 'font_color': '#1E293B', 'align': 'right',
            'valign': 'vcenter', 'border': 1, 'border_color': BORDER_CLR
        })
        f_sub_num = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 9.5, 'bold': True,
            'bg_color': '#E2E8F0', 'font_color': '#1E293B', 'align': 'right',
            'valign': 'vcenter', 'num_format': '#,##0.00', 'border': 1, 'border_color': BORDER_CLR
        })

        f_gt_lbl = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 10.5, 'bold': True,
            'bg_color': GRAND_BG, 'font_color': GRAND_FG, 'align': 'right',
            'valign': 'vcenter', 'border': 1, 'border_color': '#000000'
        })
        f_gt_num = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 10.5, 'bold': True,
            'bg_color': GRAND_BG, 'font_color': GRAND_FG, 'align': 'right',
            'valign': 'vcenter', 'num_format': '#,##0.00', 'border': 1, 'border_color': '#000000'
        })

        # Set Column Widths (11 columns)
        cols = [
            ('A:A', 6),    # Sr No
            ('B:B', 16),   # PDC Ref
            ('C:C', 16),   # Cheque No
            ('D:D', 26),   # Customer / Partner
            ('E:E', 13),   # Due Date
            ('F:F', 13),   # Payment Date
            ('G:G', 22),   # Beneficiary Bank
            ('H:H', 20),   # Remitter Bank
            ('I:I', 20),   # Memo / Reference
            ('J:J', 16),   # Amount
            ('K:K', 14),   # State
        ]
        for col_range, width in cols:
            sheet.set_column(col_range, width)

        # Company Details
        company = self.company_id
        co_name = company.name or ''
        co_addr_parts = [
            company.street or '',
            company.street2 or '',
            f"{company.city or ''} {company.zip or ''}".strip(),
            company.country_id.name or '' if company.country_id else ''
        ]
        co_addr_str = ", ".join([p for p in co_addr_parts if p])
        contact_str = f"Phone: {company.phone or 'N/A'} | Email: {company.email or 'N/A'} | VAT: {company.vat or 'N/A'}"

        # Header Block
        sheet.set_row(0, 24)
        sheet.merge_range('A1:K1', co_name, f_co_name)
        sheet.set_row(1, 14)
        sheet.merge_range('A2:K2', co_addr_str, f_co_addr)
        sheet.set_row(2, 14)
        sheet.merge_range('A3:K3', contact_str, f_co_addr)

        sheet.set_row(3, 20)
        sheet.merge_range('A4:K4', 'POST DATED CHEQUE (PDC) PAYMENT REPORT - BANK SUBMISSION', f_title)

        # Meta Info Block (Rows 5 to 7)
        sheet.set_row(5, 17)
        sheet.set_row(6, 17)
        sheet.set_row(7, 17)

        partner_label = ", ".join(self.partner_ids.mapped('name')) if self.partner_ids else 'All Customers / Partners'
        state_label = ", ".join(self.state_ids.mapped('name')) if self.state_ids else 'All States'
        date_type_label = dict(self._fields['date_filter_by'].selection).get(self.date_filter_by, 'Due Date')

        sheet.write(5, 0, 'Date From', f_meta_lbl)
        sheet.merge_range(5, 1, 5, 3, str(self.date_from), f_meta_val)
        sheet.write(5, 4, 'Date To', f_meta_lbl)
        sheet.merge_range(5, 5, 5, 6, str(self.date_to), f_meta_val)
        sheet.write(5, 7, 'Filter By', f_meta_lbl)
        sheet.merge_range(5, 8, 5, 10, date_type_label, f_meta_val)

        sheet.write(6, 0, 'Partners', f_meta_lbl)
        sheet.merge_range(6, 1, 6, 3, partner_label, f_meta_val)
        sheet.write(6, 4, 'State Filter', f_meta_lbl)
        sheet.merge_range(6, 5, 6, 6, state_label, f_meta_val)
        sheet.write(6, 7, 'Payment Type', f_meta_lbl)
        sheet.merge_range(6, 8, 6, 10, dict(self._fields['payment_type'].selection).get(self.payment_type), f_meta_val)

        sheet.write(7, 0, 'Company', f_meta_lbl)
        sheet.merge_range(7, 1, 7, 3, company.name, f_meta_val)
        sheet.write(7, 4, 'Currency', f_meta_lbl)
        sheet.merge_range(7, 5, 7, 6, company.currency_id.name, f_meta_val)
        sheet.write(7, 7, 'Generated On', f_meta_lbl)
        sheet.merge_range(7, 8, 7, 10, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), f_meta_val)

        # Blank row 8
        sheet.set_row(8, 6)

        # Column Headers (Row 9)
        sheet.set_row(9, 26)
        headers = [
            '#', 'PDC Ref', 'Cheque No', 'Customer / Partner',
            'Due Date', 'Payment Date', 'Beneficiary Bank',
            'Remitter Bank', 'Memo / Reference', f'Amount ({company.currency_id.symbol})', 'Status'
        ]
        for col_idx, text in enumerate(headers):
            sheet.write(9, col_idx, text, f_col_hdr)

        # Fetch records
        pdc_records = self._get_pdc_records()
        row = 10
        sr_no = 1
        total_amount = 0.0

        state_labels = dict(self.env['pdc.wizard']._fields['state'].selection)

        alt = False
        for pdc in pdc_records:
            rf = f_row_g if alt else f_row_w
            st_name = state_labels.get(pdc.state, pdc.state.capitalize() if pdc.state else '')

            sheet.set_row(row, 18)
            sheet.write(row, 0, sr_no, rf['txt_c'])
            sheet.write(row, 1, pdc.name or '', rf['bold_l'])
            sheet.write(row, 2, pdc.reference or pdc.cheque_number or '', rf['txt_c'])
            sheet.write(row, 3, pdc.partner_id.name or '', rf['txt_l'])
            
            if pdc.due_date:
                sheet.write_datetime(row, 4, pdc.due_date, rf['date'])
            else:
                sheet.write(row, 4, '', rf['txt_c'])

            if pdc.payment_date:
                sheet.write_datetime(row, 5, pdc.payment_date, rf['date'])
            else:
                sheet.write(row, 5, '', rf['txt_c'])

            sheet.write(row, 6, pdc.journal_id.name or '', rf['txt_l'])
            sheet.write(row, 7, pdc.bank_id.name or pdc.remitter_bank or '', rf['txt_l'])
            sheet.write(row, 8, pdc.memo or '', rf['txt_l'])
            sheet.write(row, 9, pdc.payment_amount or 0.0, rf['num'])
            sheet.write(row, 10, st_name, rf['txt_c'])

            total_amount += (pdc.payment_amount or 0.0)
            sr_no += 1
            row += 1
            alt = not alt

        # Grand Total Row
        sheet.set_row(row, 22)
        sheet.merge_range(row, 0, row, 8, f'GRAND TOTAL ({sr_no - 1} Cheques)', f_gt_lbl)
        sheet.write(row, 9, total_amount, f_gt_num)
        sheet.write(row, 10, '', f_gt_lbl)
        row += 2

        # Summary Breakdown by State Section
        sheet.set_row(row, 20)
        sheet.merge_range(row, 0, row, 4, 'SUMMARY BY CHEQUE STATE', f_sec_hdr)
        row += 1

        state_summary = {}
        for pdc in pdc_records:
            st = pdc.state or 'draft'
            if st not in state_summary:
                state_summary[st] = {'count': 0, 'amount': 0.0}
            state_summary[st]['count'] += 1
            state_summary[st]['amount'] += (pdc.payment_amount or 0.0)

        for st_code, st_data in state_summary.items():
            st_name = state_labels.get(st_code, st_code.capitalize())
            sheet.set_row(row, 18)
            sheet.merge_range(row, 0, row, 2, st_name, f_sub_lbl)
            sheet.write(row, 3, f"{st_data['count']} Cheque(s)", f_sub_lbl)
            sheet.write(row, 4, st_data['amount'], f_sub_num)
            row += 1

        # Bank Submission Signature Block
        row += 2
        sheet.set_row(row, 18)
        sheet.merge_range(row, 0, row, 10,
                          "Declaration: We hereby confirm that the PDC Cheques listed above are verified against official company books for bank submission.",
                          workbook.add_format({'font_name': 'Calibri', 'font_size': 9, 'italic': True, 'font_color': '#475569'}))
        row += 2

        f_sig_title = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 9, 'bold': True, 'align': 'center', 'valign': 'top'
        })
        f_sig_line = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 9, 'align': 'center', 'valign': 'top',
            'top': 1, 'top_color': '#000000'
        })

        sheet.set_row(row, 35) # spacing for signature
        row += 1
        sheet.set_row(row, 18)

        sheet.merge_range(row, 0, row, 2, 'Prepared By\n(Accountant)', f_sig_line)
        sheet.merge_range(row, 4, row, 6, 'Checked & Verified By\n(Finance Manager)', f_sig_line)
        sheet.merge_range(row, 8, row, 10, 'Authorized Signatory\n(Company Stamp & Signature)', f_sig_line)
