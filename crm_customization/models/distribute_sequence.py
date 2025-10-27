from odoo import models, fields,api

class DistributeSequence(models.Model):
    _name = 'distribute.sequence'
    _description = 'Distribute Sequence'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence asc'
    _sequence = 'sequence'

    sequence = fields.Integer(string="Sequence", default=10)
    sales_person = fields.Many2one('res.users', string='Sales Person')
    branch = fields.Many2one('res.branch', string='Branch')
    shift = fields.Many2one('res.shift', string='Shift')
    from_date = fields.Float(string="From", related='shift.from_date', readonly=True)
    to_date = fields.Float(string="To", related='shift.to_date', readonly=True)

    state = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ], string="Status", default='active', tracking=True,compute='_compute_team_member_state', store=True)


    @api.depends('sales_person', 'sales_person.crm_team_member_ids.state')
    def _compute_team_member_state(self):
        for rec in self:
            member = self.env['crm.team.member'].search([('user_id', '=', rec.sales_person.id)], limit=1)
            rec.state = member.state if member else False
