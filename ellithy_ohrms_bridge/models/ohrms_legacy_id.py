from odoo import fields, models

# hr.loan and salary.advance both overwrite `name` with their own sequence on
# create, so a reference written into that field does not survive. Without a
# dedicated key a migration re-run has nothing to match on and duplicates
# every record -- which is exactly what happened on the first reload.
#
# Every model the migration writes into therefore gets the same `legacy_id`
# column the Ellithy models already carry, with a unique index so a duplicate
# is refused by the database rather than merely discouraged.


class HrLoan(models.Model):
    _inherit = 'hr.loan'

    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another loan already carries this legacy ID.'),
    ]


class SalaryAdvance(models.Model):
    _inherit = 'salary.advance'

    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another salary advance already carries this legacy ID.'),
    ]


class HrResignation(models.Model):
    _inherit = 'hr.resignation'

    legacy_id = fields.Integer(
        string='Legacy ID', index=True, copy=False,
        help='Primary key of the legacy users row this resignation came from.')

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another resignation already carries this legacy ID.'),
    ]


class HrEmployeeFamily(models.Model):
    _inherit = 'hr.employee.family'

    legacy_id = fields.Char(
        string='Legacy Key', index=True, copy=False,
        help='"<user id>/<slot>" -- the legacy stores two fixed relative '
             'blocks per employee rather than a child table, so the slot '
             'number is part of the identity.')

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another family member already carries this legacy key.'),
    ]
