from odoo import _, api, fields, models
from odoo.exceptions import UserError


class IbsHrTimeOffLedger(models.Model):
    _name = 'ibs.hr.time.off.ledger'
    _description = 'Time Off Balance Ledger'
    _order = 'date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', required=True, index=True, ondelete='cascade')
    type_id = fields.Many2one(
        'ibs.hr.time.off.type', required=True, index=True, ondelete='restrict')
    date = fields.Date(required=True, index=True)
    amount = fields.Float(required=True, digits=(8, 4))
    entry_type = fields.Selection([
        ('grant', 'Grant'),
        ('accrual', 'Accrual'),
        ('usage', 'Usage'),
        ('reversal', 'Reversal'),
        ('adjustment', 'Adjustment'),
        ('expiry', 'Expiry'),
    ], required=True)
    request_id = fields.Many2one(
        'ibs.hr.time.off.request', ondelete='restrict', index=True)
    description = fields.Char()
    unique_key = fields.Char(index=True, copy=False)

    _sql_constraints = [
        ('unique_posting_key', 'unique(unique_key)',
         'This balance entry has already been posted.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(
                values.get('entry_type') != 'adjustment' or values.get('request_id')
                for values in vals_list):
            raise UserError(_('Only explicit adjustments can be entered manually.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise UserError(_('Posted ledger entries are immutable. Post an adjustment instead.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_('Posted time off entries cannot be deleted.'))
        return super().unlink()
