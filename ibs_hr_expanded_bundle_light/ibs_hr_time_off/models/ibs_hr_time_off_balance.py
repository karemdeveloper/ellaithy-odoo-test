from odoo import _, api, fields, models, tools


class IbsHrTimeOffBalance(models.Model):
    """HR letter item 18: one line per employee, type and year.

    A summary of the ledger -- what was granted or accrued, what was taken
    and what is left -- so nobody has to add up thousands of postings to
    know a balance. Read-only; the ledger stays the record.
    """

    _name = 'ibs.hr.time.off.balance'
    _description = 'Time Off Balance Summary'
    _auto = False
    _order = 'year desc, employee_id, type_id'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', readonly=True)
    type_id = fields.Many2one('ibs.hr.time.off.type', string='Type', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    department_id = fields.Many2one('hr.department', readonly=True)
    year = fields.Integer(readonly=True, aggregator=False)
    entitled = fields.Float(
        string='Entitled', readonly=True, digits=(8, 2),
        help='Grants, monthly accruals and adjustments of the year.')
    used = fields.Float(
        string='Used', readonly=True, digits=(8, 2),
        help='Approved time off of the year, net of reversals.')
    expired = fields.Float(string='Expired', readonly=True, digits=(8, 2))
    remaining = fields.Float(
        string='Remaining', readonly=True, digits=(8, 2),
        help='Entitled minus used.')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    MIN(l.id) AS id,
                    l.employee_id,
                    l.type_id,
                    e.company_id,
                    e.department_id,
                    EXTRACT(YEAR FROM l.date)::int AS year,
                    SUM(CASE WHEN l.entry_type IN ('grant', 'accrual', 'adjustment')
                             THEN l.amount ELSE 0 END) AS entitled,
                    -SUM(CASE WHEN l.entry_type IN ('usage', 'reversal')
                              THEN l.amount ELSE 0 END) AS used,
                    -SUM(CASE WHEN l.entry_type = 'expiry'
                              THEN l.amount ELSE 0 END) AS expired,
                    SUM(CASE WHEN l.entry_type != 'expiry'
                             THEN l.amount ELSE 0 END) AS remaining
                FROM ibs_hr_time_off_ledger l
                JOIN hr_employee e ON e.id = l.employee_id
                GROUP BY l.employee_id, l.type_id, e.company_id, e.department_id,
                         EXTRACT(YEAR FROM l.date)
            )
        """)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def action_view_time_off_balance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Time Off Balance - %(name)s', name=self.name),
            'res_model': 'ibs.hr.time.off.balance',
            'view_mode': 'list',
            'domain': [('employee_id', '=', self.id)],
            'context': {'search_default_this_year': 1},
        }
