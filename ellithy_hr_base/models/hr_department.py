from odoo import api, fields, models

DEPT_TYPE = [
    ('directorate', 'Directorate'),
    ('section', 'Section'),
]


class HrDepartment(models.Model):
    """Department and section.

    The legacy keeps two tables: ``departments`` (17 directorates) and
    ``posts`` (94 sections, each under a department). Odoo departments are
    already hierarchical, so both land here and are told apart by
    ``dept_type`` -- which buys the org chart, manager chain and department
    reporting without a second model.
    """

    _inherit = 'hr.department'

    # Stock Odoo labels this "Manager". The legacy column is dept_head_id and
    # the business calls the role Department Head, so relabel rather than add
    # a second field that would drift out of step with Odoo's own hierarchy.
    manager_id = fields.Many2one(string='Department Head')

    name_ar = fields.Char(string='Arabic Name')
    dept_type = fields.Selection(
        DEPT_TYPE, string='Type', required=True, default='directorate',
        index=True)
    branch_id = fields.Many2one(
        'ellithy.branch', string='Branch', index=True, ondelete='restrict')
    address = fields.Char()
    phone = fields.Char()
    section_ids = fields.One2many(
        'hr.department', 'parent_id', string='Sections',
        domain=[('dept_type', '=', 'section')])
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)
    legacy_table = fields.Char(
        string='Legacy Table', copy=False,
        help='departments or posts -- which source table this row came from.')

    @api.onchange('dept_type')
    def _onchange_dept_type(self):
        if self.dept_type == 'directorate':
            self.parent_id = False
