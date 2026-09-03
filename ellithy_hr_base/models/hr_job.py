from odoo import fields, models


class HrJob(models.Model):
    """Position.

    The legacy ``company_jobs`` table (114 rows) links a position to both a
    department and a section.
    """

    _inherit = 'hr.job'

    name_ar = fields.Char(string='Arabic Name')
    section_id = fields.Many2one(
        'hr.department', string='Section', index=True, ondelete='restrict',
        domain="[('dept_type', '=', 'section')]")
    is_kpi_locked = fields.Boolean(
        string='KPI Locked',
        help='Legacy flag preventing further edits to this position\'s KPI set.')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)
