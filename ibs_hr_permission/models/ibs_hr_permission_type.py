from odoo import fields, models


class IbsHrPermissionType(models.Model):
    """Admin-configurable catalogue of permission types.

    Seeded with Lateness and Early Leave, but deliberately not a fixed
    selection: HR Admins can add, rename or deactivate types from
    Configuration without a code change.
    """

    _name = 'ibs.hr.permission.type'
    _description = 'Permission Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)',
         'A permission type with this name already exists.'),
    ]
