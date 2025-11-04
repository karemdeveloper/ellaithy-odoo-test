from odoo import models, fields,api

class CrmTeamMember(models.Model):
    _inherit = 'crm.team.member'
    shift = fields.Many2many('res.shift', string="Shift")
    state = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ], string="Status", default='active', tracking=True)
    date_to= fields.Datetime(string="To")
    team_leader = fields.Many2one(
        'res.users',
        string='Team Leader',
        related='crm_team_id.user_id',  # <-- تأكدي أن اسم الحقل داخل crm.team هو user_id
        store=True,
        readonly=True
    )
    @api.model
    def _cron_check_inactive_members(self):
        """Deactivate members whose date_to has passed."""
        now = fields.Datetime.now()
        now_float = now.hour + now.minute / 60.0

        expired_members = self.search([
            ('date_to', '<', now),
            ('state', '=', 'inactive')
        ])
        expired_members.write({'state': 'active'})