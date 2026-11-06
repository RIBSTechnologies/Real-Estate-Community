# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################

import babel
from datetime import date, datetime, time
from dateutil.relativedelta import relativedelta
from pytz import timezone
from odoo.tools import float_round, date_utils, convert_file, format_amount
from collections import defaultdict
from odoo.tools.safe_eval import safe_eval, datetime as safe_eval_datetime, dateutil as safe_eval_dateutil
from odoo.tools.float_utils import float_compare
from functools import reduce
from odoo.tools.misc import format_date
import math


from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError


class DefaultDictPayroll(defaultdict):
    def get(self, key, default=None):
        if key not in self and default is not None:
            self[key] = default
        return self[key]


class WkHrPayslip(models.Model):
    _name = 'wk.hr.payslip'
    _description = 'Pay Slip'

    struct_id = fields.Many2one(
        'wk.hr.payroll.structure',
        string='Structure',
        help=
        'Defines the rules that have to be applied to this payslip, accordingly '
        'to the contract chosen. If you let empty the field contract, this field isn\'t '
        'mandatory anymore and thus the rules applied will be all the rules set on the '
        'structure of all contracts of the employee valid for the chosen period'
    )
    name = fields.Char(
        string='Payslip Name', required=True,
        compute='_compute_name', store=True, readonly=False)
    number = fields.Char(string='Reference',copy=False)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    date_from = fields.Date(string='Date From',required=True,
                            default=lambda self: fields.Date.to_string(date.today().replace(day=1)))
    date_to = fields.Date(string='Date To', readonly=True, required=True,
                          default=lambda self: fields.Date.to_string(
                              (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()))
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('verify', 'Waiting'),
            ('done', 'Done'),
            ('cancel', 'Rejected'),
        ],
        string='Status', index=True, readonly=True,
        copy=False, default='draft',
        help="""* When the payslip is created the status is \'Draft\'
                \n* If the payslip is under verification, the status is \'Waiting\'.
                \n* If the payslip is confirmed then status is set to \'Done\'.
                \n* When user cancel payslip the status is \'Rejected\'.""")
    line_ids = fields.One2many('wk.hr.payslip.line', 'slip_id',
                               string='Payslip Lines')
    company_id = fields.Many2one('res.company', string='Company',
     copy=False,default=lambda self: self.env.company,)
    worked_days_line_ids = fields.One2many('wk.hr.payslip.worked_days', 'payslip_id',
        string='Payslip Worked Days', copy=True)
    input_line_ids = fields.One2many('wk.hr.payslip.input', 'payslip_id',
                                     string='Payslip Inputs')
    note = fields.Text(string='Internal Note')
    # contract_id = fields.Many2one('hr.contract', string='Contract')
    version_id = fields.Many2one(
        'hr.version',
        string='Employee Record',
        precompute=True,
        tracking=True,
        compute='_compute_version_id',
        store=True,
        readonly=False,
        index=True,
        domain="""[
            ('contract_date_start', '<=', date_end),
            '|', ('contract_date_end', '=', False), ('contract_date_end', '>=', date_from)
        ]""",
    )
    use_worked_day_lines = fields.Boolean()
    details_by_salary_rule_category = fields.One2many('wk.hr.payslip.line',
        compute='_compute_details_by_salary_rule_category',
        string='Details by Salary Rule Category')
    credit_note = fields.Boolean(string='Credit Note',
        help="Indicates this payslip has a refund of another")
    payslip_run_id = fields.Many2one('wk.hr.payslip.run', string='Payslip Batches',copy=False)
    payslip_count = fields.Integer(compute='_compute_payslip_count',
                                   string="Payslip Computation Details")
    ytd_computation = fields.Boolean(related='struct_id.ytd_computation')
    payslip_properties = fields.Properties('Payroll Properties', definition='struct_id.payslip_properties_definition')

    @api.depends('employee_id.legal_name', 'employee_id.lang', 'struct_id', 'date_from', 'date_to')
    def _compute_name(self):
        formated_date_cache = {}
        for slip in self.filtered(lambda p: p.employee_id and p.date_from and p.date_to):
            lang = slip.employee_id.lang or self.env.user.lang
            context = {'lang': lang}
            payslip_name =  _('Salary Slip')
            del context

            slip.name = '%(payslip_name)s - %(employee_name)s - %(dates)s' % {
                'payslip_name': payslip_name,
                'employee_name': slip.employee_id.legal_name,
                'dates': slip._get_period_name(formated_date_cache),
            }

    def _format_date_cached(self, cache, date, date_format=False):
        key = (date, date_format)
        if key not in cache:
            lang = self.employee_id.lang or self.env.user.lang
            cache[key] = format_date(env=self.env, value=date, lang_code=lang, date_format=date_format)
        return cache[key]

    def _get_period_name(self, cache):
        self.ensure_one()
        period_name = '%s - %s' % (
            self._format_date_cached(cache, self.date_from),
            self._format_date_cached(cache, self.date_to))
        start_date = self.date_from
        end_date = self.date_to
        lang = self.employee_id.lang or self.env.user.lang
        week_start = self.env["res.lang"]._get_data(code=lang).week_start
        schedule = self.version_id.schedule_pay or self.version_id.structure_type_id.default_schedule_pay
        if schedule == 'monthly':
            period_name = self._format_date_cached(cache, start_date, "MMMM Y")
        elif schedule == 'quarterly':
            current_year_quarter = math.ceil(start_date.month / 3)
            period_name = _("Quarter %(quarter)s of %(year)s", quarter=current_year_quarter, year=start_date.year)
        elif schedule == 'semi-annually':
            year_half = start_date.replace(day=1, month=6)
            is_first_half = start_date < year_half
            period_name = _("1st semester of %s", start_date.year)\
                if is_first_half\
                else _("2nd semester of %s", start_date.year)
        elif schedule == 'annually':
            period_name = start_date.year
        elif schedule == 'weekly':
            wk_num = start_date.strftime('%U') if week_start == '7' else start_date.strftime('%W')
            period_name = _('Week %(week_number)s of %(year)s', week_number=wk_num, year=start_date.year)
        elif schedule == 'bi-weekly':
            week = int(start_date.strftime("%U") if week_start == '7' else start_date.strftime("%W"))
            first_week = week - 1 + week % 2
            period_name = _("Weeks %(week)s and %(week1)s of %(year)s",
                week=first_week, week1=first_week + 1, year=start_date.year)
        elif schedule == 'bi-monthly':
            start_date_string = self._format_date_cached(cache, start_date, "MMMM Y")
            end_date_string = self._format_date_cached(cache, end_date, "MMMM Y")
            period_name = _("%(start_date_string)s and %(end_date_string)s", start_date_string=start_date_string, end_date_string=end_date_string)
        return period_name

    @api.depends('employee_id')
    def _compute_version_id(self):
        for slip in self:
            slip.version_id = slip.employee_id.current_version_id if slip.employee_id else False

    def _compute_details_by_salary_rule_category(self):
        for payslip in self:
            payslip.details_by_salary_rule_category = payslip.mapped(
                'line_ids').filtered(lambda line: line.category_id)

    def _compute_payslip_count(self):
        for payslip in self:
            payslip.payslip_count = len(payslip.line_ids)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        if any(
                self.filtered(lambda payslip: payslip.date_from > payslip.date_to)):
            raise ValidationError(_("Payslip 'Date From' must be earlier 'Date To'."))

    def action_payslip_draft(self):
        return self.write({'state': 'draft'})

    def action_payslip_done(self):
        self.compute_sheet()
        return self.write({'state': 'done'})

    def action_payslip_cancel(self):
        if self.filtered(lambda slip: slip.state == 'done'):
            raise UserError(_("Cannot cancel a payslip that is done."))
        return self.write({'state': 'cancel'})

    def refund_sheet(self):
        for payslip in self:
            copied_payslip = payslip.copy({
                'credit_note': True,
                'name': _('Refund: ') + payslip.name
            })
            copied_payslip.compute_sheet()
            copied_payslip.action_payslip_done()
        formview_ref = self.env.ref('wk_hr_payroll.view_wk_hr_payslip_form', False)
        treeview_ref = self.env.ref('wk_hr_payroll.view_wk_hr_payslip_tree', False)
        return {
            'name': ("Refund Payslip"),
            'view_mode': 'list, form',
            'view_id': False,
            'res_model': 'wk.hr.payslip',
            'type': 'ir.actions.act_window',
            'target': 'current',
            'domain': "[('id', 'in', %s)]" % copied_payslip.ids,
            'views': [(treeview_ref and treeview_ref.id or False, 'list'),
                      (formview_ref and formview_ref.id or False, 'form')],
            'context': {}
        }

    def check_done(self):
        return True

    def unlink(self):
        if any(self.filtered(lambda payslip: payslip.state not in ('draft', 'cancel'))):
            raise UserError(
                _('You cannot delete a payslip which is not draft or cancelled!'))
        return super(WkHrPayslip, self).unlink()

    # TODO move this function into hr_contract module, on hr.employee object
    @api.model
    def get_contract(self, employee, date_from, date_to):
        """
        @param employee: recordset of employee
        @param date_from: date field
        @param date_to: date field
        @return: returns the ids of all the contracts for the given employee that need to be considered for the given dates
        """
        # a contract is valid if it ends between the given dates
        clause_1 = ['&', ('date_end', '<=', date_to), ('date_end', '>=', date_from)]
        # OR if it starts between the given dates
        clause_2 = ['&', ('date_start', '<=', date_to), ('date_start', '>=', date_from)]
        # OR if it starts before the date_from and finish after the date_end (or never finish)
        clause_3 = ['&', ('date_start', '<=', date_from), '|',
            ('date_end', '=', False), ('date_end', '>=', date_to)]
        clause_final = [('employee_id', '=', employee.id),
                        ('state', '=', 'open'), '|', '|'] + clause_1 + clause_2 + clause_3
        return self.env['hr.contract'].search(clause_final).ids

    # def compute_sheet(self):
    #     for payslip in self:
    #         number = payslip.number or self.env['ir.sequence'].next_by_code('salary.slip')
    #         # delete old payslip lines
    #         payslip.line_ids.unlink()
    #         # set the list of contract for which the rules have to be applied
    #         # if we don't give the contract, then the rules to apply should be for all current contracts of the employee
    #         contract_ids = payslip.contract_id.ids or \
    #             self.get_contract(payslip.employee_id, payslip.date_from, payslip.date_to)
    #         lines = [(0, 0, line) for line in self._get_payslip_lines(contract_ids, payslip.id)]
    #         payslip.write({'line_ids': lines, 'number': number})
    #     return True

    def compute_sheet(self):
        payslips = self.filtered(lambda slip: slip.state == 'draft')
        # if payslips.filtered('error_count'):
        #     self._get_error_message()
        # delete old payslip lines
        payslips.line_ids.unlink()
        # this guarantees consistent results
        self.env.flush_all()
        today = fields.Date.today()
        for payslip in payslips:
            payslip.write({
                'state': 'draft',
            })
        self.env['wk.hr.payslip.line'].create(payslips._get_payslip_lines())
        if any(payslips.mapped('ytd_computation')):
            self._compute_worked_days_ytd()
        return True



    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        """
        @param contract: Browse record of contracts
        @return: returns a list of dict containing the input that should be applied for the given contract between date_from and date_to
        """
        res = []
        # fill only if the contract as a working schedule linked
        for contract in contracts.filtered(
                lambda contract: contract.resource_calendar_id):
            day_from = datetime.combine(fields.Date.from_string(date_from), time.min)
            day_to = datetime.combine(fields.Date.from_string(date_to), time.max)

            # compute leave days
            leaves = {}
            calendar = contract.resource_calendar_id
            tz = timezone(calendar.tz)
            day_leave_intervals = contract.employee_id.list_leaves(
                day_from, day_to, calendar=contract.resource_calendar_id)
            for day, hours, leave in day_leave_intervals:
                holiday = leave.holiday_id
                current_leave_struct = leaves.setdefault(
                    holiday.work_entry_type_id, {
                        'name': holiday.work_entry_type_id.name or _('Global Leaves'),
                        'sequence': 5,
                        'code': holiday.work_entry_type_id.name or 'GLOBAL',
                        'number_of_days': 0.0,
                        'number_of_hours': 0.0,
                        'contract_id': contract.id,
                    })
                current_leave_struct['number_of_hours'] += hours
                work_hours = calendar.get_work_hours_count(
                    tz.localize(datetime.combine(day, time.min)),
                    tz.localize(datetime.combine(day, time.max)),
                    compute_leaves=False,
                )
                if work_hours:
                    current_leave_struct['number_of_days'] += hours / work_hours

            # compute worked days
            work_data = contract.employee_id._get_work_days_data_batch(
                day_from, day_to, calendar=contract.resource_calendar_id)
            attendances = {
                'name': _("Normal Working Days paid at 100%"),
                'sequence': 1,
                'code': 'WORK100',
                'number_of_days': work_data[contract.employee_id.id]['days'],
                'number_of_hours': work_data[contract.employee_id.id]['hours'],
                'contract_id': contract.id,
            }

            res.append(attendances)
            res.extend(leaves.values())
        return res

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        res = []

        structure_ids = contracts.get_all_structures()
        rule_ids = self.env['wk.hr.payroll.structure'].browse(structure_ids).get_all_rules()
        sorted_rule_ids = [id for id, sequence in sorted(rule_ids, key=lambda x: x[1])]
        inputs = self.env['wk.hr.salary.rule'].browse(sorted_rule_ids).mapped('input_ids')

        for contract in contracts:
            for input in inputs:
                input_data = {
                    'name': input.name,
                    'code': input.code,
                    'contract_id': contract.id,
                }
                res += [input_data]
        return res

    def _get_line_values(self, code_list, vals_list=None, compute_sum=False):
        if vals_list is None:
            vals_list = ['total']
        valid_values = {'quantity', 'amount', 'total', 'ytd'}
        if set(vals_list) - valid_values:
            raise UserError(_('The following values are not valid:\n%s', '\n'.join(list(set(vals_list) - valid_values))))
        result = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(vals_list, 0.0)))
        if not self or not code_list:
            return result
        self.env.flush_all()
        selected_fields = ','.join('SUM(%s) AS %s' % (vals, vals) for vals in vals_list)
        self.env.cr.execute("""
            SELECT
                p.id,
                pl.code,
                %s
            FROM hr_payslip_line pl
            JOIN hr_payslip p
            ON p.id IN %s
            AND pl.slip_id = p.id
            AND pl.code IN %s
            GROUP BY p.id, pl.code
        """ % (selected_fields, '%s', '%s'), (tuple(self.ids), tuple(code_list)))
        request_rows = self.env.cr.dictfetchall()
        for row in request_rows:
            code = row['code']
            payslip_id = row['id']
            for vals in vals_list:
                if compute_sum:
                    result[code]['sum'][vals] += row[vals] or 0.0
                result[code][payslip_id][vals] += row[vals] or 0.0
        return result

    def _get_localdict(self):
        self.ensure_one()
        same_type_input_lines = defaultdict(lambda x: self.env['hr.payslip.input'])
        input_line_ids_by_code = self.input_line_ids.grouped('code')
        for code, input_lines in input_line_ids_by_code.items():
            if len(input_lines) > 1:
                same_type_input_lines[code] = input_lines

        employee_properties = dict(self.version_id.payroll_properties)
        payslip_properties = dict(self.payslip_properties)
        employee_properties.update(payslip_properties)

        localdict = {
            **self._get_base_local_dict(),
            **{
                'categories': DefaultDictPayroll(lambda: 0),
                'rules': DefaultDictPayroll(lambda: dict(total=0, amount=0, quantity=0)),
                'payslip': self,
                'worked_days': {line.code: line for line in self.worked_days_line_ids if line.code},
                'property_inputs': {self.env['hr.salary.rule'].browse(int(rule_id)).id: float(value) for rule_id, value in employee_properties.items()},
                'inputs': {line.code: line for line in self.input_line_ids if line.code},
                'employee': self.employee_id,
                'version': self.version_id,
                'result_rules': DefaultDictPayroll(lambda: dict(total=0, amount=0, quantity=0, rate=0, ytd=0)),
                'same_type_input_lines': same_type_input_lines,
            }
        }
        for code, input_lines in same_type_input_lines.items():
            input_line_ids = input_lines.ids
            localdict['inputs'][code] = self.__get_aggregator_hr_payslip_input_model()(
                env=self.env, ids=input_line_ids, prefetch_ids=input_line_ids,
            )
        return localdict
    
    @property
    def paid_amount(self):
        self.ensure_one()
        return self._get_paid_amount()
    
    def _get_paid_amount(self):
        self.ensure_one()
        if self.env.context.get('no_paid_amount'):
            return 0.0
        if self.env.context.get('salary_simulation') or not self.struct_id.use_worked_day_lines:
            return self._get_contract_wage()
        total_amount = 0
        for line in self.worked_days_line_ids:
            total_amount += line.amount
        return total_amount
    
    def _get_base_local_dict(self):
        return {
            'float_round': float_round,
            'float_compare': float_compare,
            'relativedelta': safe_eval_dateutil.relativedelta.relativedelta,
            'ceil': math.ceil,
            'floor': math.floor,
            'UserError': UserError,
            'date': safe_eval_datetime.date,
            'datetime': safe_eval_datetime.datetime,
            'defaultdict': defaultdict,
        }
    
    def _get_payslip_line_total(self, amount, quantity, rate, rule):
        self.ensure_one()
        return amount * quantity * rate / 100.0

    def _get_payslip_lines(self):
        def get_rule_name(localdict, rule):
            if localdict['result_name']:
                return localdict['result_name']
            if rule.amount_select == "input"\
                and rule.amount_other_input_id.code in localdict['inputs']\
                    and (name := localdict['inputs'][rule.amount_other_input_id.code].name):
                return name
            return rule.name

        line_vals = []

        if any(self.mapped('ytd_computation')):
            last_ytd_payslips = self._get_last_ytd_payslips()
            code_set = set(self.struct_id.rule_ids.mapped('code'))
        else:
            last_ytd_payslips = defaultdict(lambda: self.env['wk.hr.payslip'])
            code_set = set()
        ytd_payslips = reduce(
            lambda ytd_payslips, payslip: ytd_payslips | payslip, last_ytd_payslips.values(),
            self.env['wk.hr.payslip']
        )

        line_values = ytd_payslips._get_line_values(code_set, ['ytd'])

        for payslip in self:
            if lang := payslip.employee_id.lang:
                # /!\ Don't remove /!\ ensure that the employee will receive their payslip in their language.
                payslip = payslip.with_context(lang=lang)

            localdict = self.env.context.get('force_payslip_localdict', payslip._get_localdict())
            result_rules_dict = localdict['result_rules']

            blacklisted_rule_ids = self.env.context.get('prevent_payslip_computation_line_ids', [])

            result = {}
            for rule in sorted(payslip.struct_id.rule_ids, key=lambda x: x.sequence):
                if rule.id in blacklisted_rule_ids:
                    continue
                localdict.update({
                    'result': None,
                    'result_qty': 1.0,
                    'result_rate': 100,
                    'result_name': False
                })
                if rule._satisfy_condition(localdict):
                    if rule.code in localdict['same_type_input_lines']:
                        for multi_line_rule in localdict['same_type_input_lines'][rule.code]:
                            localdict['inputs'][rule.code] = multi_line_rule
                            amount, qty, rate = rule._compute_rule(localdict)
                            tot_rule = payslip._get_payslip_line_total(amount, qty, rate, rule)
                            ytd = line_values[rule.code][last_ytd_payslips[payslip].id]['ytd'] + tot_rule

                            result_rules_dict[rule.code]['total'] += tot_rule
                            result_rules_dict[rule.code]['amount'] += tot_rule
                            result_rules_dict[rule.code]['quantity'] = 1
                            result_rules_dict[rule.code]['rate'] = 100
                            result_rules_dict[rule.code]['ytd'] = ytd

                            localdict = rule.category_id._sum_salary_rule_category(
                                localdict, tot_rule)
                            line_vals.append({
                                'sequence': rule.sequence,
                                'code': rule.code,
                                'name':  get_rule_name(localdict, rule),
                                'salary_rule_id': rule.id,
                                'version_id': localdict['version'].id,
                                'employee_id': localdict['employee'].id,
                                'amount': amount,
                                'quantity': qty,
                                'rate': rate,
                                'total': tot_rule,
                                'slip_id': payslip.id,
                                'ytd': ytd,
                            })
                        input_line_ids = localdict['same_type_input_lines'][rule.code].ids
                        localdict['inputs'][rule.code] = self.__get_aggregator_hr_payslip_input_model()(
                            env=self.env, ids=input_line_ids, prefetch_ids=input_line_ids,
                        )
                    else:
                        amount, qty, rate = rule._compute_rule(localdict)
                        #check if there is already a rule computed with that code
                        previous_amount = localdict.get(rule.code, 0.0)
                        #set/overwrite the amount computed for this rule in the localdict
                        tot_rule = payslip._get_payslip_line_total(amount, qty, rate, rule)
                        ytd = line_values[rule.code][last_ytd_payslips[payslip].id]['ytd'] + tot_rule
                        localdict[rule.code] = tot_rule
                        result_rules_dict[rule.code] = {
                            'total': tot_rule, 'amount': amount, 'quantity': qty, 'rate': rate, 'ytd': ytd
                        }
                        # sum the amount for its salary category
                        localdict = rule.category_id._sum_salary_rule_category(localdict, tot_rule - previous_amount)
                        # create/overwrite the rule in the temporary results
                        result[rule.code] = {
                            'sequence': rule.sequence,
                            'code': rule.code,
                            'name': get_rule_name(localdict, rule),
                            'salary_rule_id': rule.id,
                            'version_id': localdict['version'].id,
                            'employee_id': localdict['employee'].id,
                            'amount': amount,
                            'quantity': qty,
                            'rate': rate,
                            'total': tot_rule,
                            'slip_id': payslip.id,
                            'ytd': ytd,
                        }
            line_vals += list(result.values())
        return line_vals

    def get_salary_line_total(self, code):
        self.ensure_one()
        line = self.line_ids.filtered(lambda line: line.code == code)
        if line:
            return line[0].total
        else:
            return 0.0


class WkHrPayslipLine(models.Model):
    _name = 'wk.hr.payslip.line'
    _inherit = 'wk.hr.salary.rule'
    _description = 'Payslip Line'
    _order = 'version_id, sequence'

    slip_id = fields.Many2one('wk.hr.payslip', string='Pay Slip', required=True, ondelete='cascade')
    salary_rule_id = fields.Many2one('wk.hr.salary.rule', string='Rule', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    version_id = fields.Many2one('hr.version', string='Contract', required=True, index=True)
    # contract_id = fields.Many2one('hr.contract', string='Contract', required=True, index=True)
    rate = fields.Float(string='Rate (%)', digits='Payroll Rate', default=100.0)
    amount = fields.Float(digits='Payroll')
    quantity = fields.Float(digits='Payroll', default=1.0)
    total = fields.Float(compute='_compute_total', string='Total', digits='Payroll', store=True)
    ytd = fields.Monetary(string='YTD')
    currency_id = fields.Many2one('res.currency')

    @api.depends('quantity', 'amount', 'rate')
    def _compute_total(self):
        for line in self:
            line.total = float(line.quantity) * line.amount * line.rate / 100

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if 'employee_id' not in values or 'version_id' not in values:
                payslip = self.env['wk.hr.payslip'].browse(values.get('slip_id'))
                values['employee_id'] = values.get('employee_id') or payslip.employee_id.id
                values['version_id'] = values.get('version_id') or payslip.version_id and payslip.version_id.id
                if not values['version_id']:
                    raise UserError(_('You must set a contract to create a payslip line.'))
        
        return super(WkHrPayslipLine, self).create(vals_list)


class WkHrPayslipWorkedDays(models.Model):
    _name = 'wk.hr.payslip.worked_days'
    _description = 'Payslip Worked Days'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Description', required=True)
    payslip_id = fields.Many2one('wk.hr.payslip', string='Pay Slip',
                                 required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(required=True, index=True, default=10)
    code = fields.Char(required=True,
                       help="The code that can be used in the salary rules")
    number_of_days = fields.Float(string='Number of Days')
    number_of_hours = fields.Float(string='Number of Hours')
    # contract_id = fields.Many2one('hr.contract', string='Contract',
    #     required=True, help="The contract for which applied this input")
    version_id = fields.Many2one(related='payslip_id.version_id', string='Contract',
        help="The contract this worked days should be applied to")


class WkHrPayslipInput(models.Model):
    _name = 'wk.hr.payslip.input'
    _description = 'Payslip Input'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Description', required=True)
    payslip_id = fields.Many2one('wk.hr.payslip', string='Pay Slip',
                                 required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(required=True, index=True, default=10)
    code = fields.Char(required=True, help="The code that can be used in the salary rules")
    amount = fields.Float(
        help="It is used in computation. For e.g. A rule for sales having "
        "1% commission of basic salary for per product can defined in expression "
        "like result = inputs.SALEURO.amount * employee.wage*0.01.")
    # contract_id = fields.Many2one('hr.contract', string='Contract', required=True,
    #     help="The contract for which applied this input")
    version_id = fields.Many2one(
        related='payslip_id.version_id', string='Employee Record', required=True,
        help="The version this input should be applied to")


class WkHrPayslipRun(models.Model):
    _name = 'wk.hr.payslip.run'
    _description = 'Payslip Batches'

    name = fields.Char(required=True)
    slip_ids = fields.One2many('wk.hr.payslip', 'payslip_run_id',
                               string='Payslips')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('close', 'Close'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft')
    date_start = fields.Date(string='Date From', required=True,
                             default=lambda self: fields.Date.to_string(date.today().replace(day=1)))
    date_end = fields.Date(string='Date To', required=True,
                           default=lambda self: fields.Date.to_string(
                               (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()))
    credit_note = fields.Boolean(string='Credit Note',
        help="If its checked, indicates that all payslips generated from here are refund payslips."
    )

    def draft_payslip_run(self):
        return self.write({'state': 'draft'})

    def close_payslip_run(self):
        return self.write({'state': 'close'})
