from odoo import models, fields, api

class CrmFeedbackWizard(models.TransientModel):
    _name = 'crm.feedback.wizard'
    _description = 'CRM Feedback Wizard'

    date = fields.Datetime(string="Date", default=fields.Datetime.now,)
    salesperson_id = fields.Many2one('res.users', string="Salesperson")
    feedback = fields.Text(string="Feedback")
    feedback2 = fields.Selection([
        ('not_contacted', 'Not contacted'),
        ('answered', 'Answered'),
        ('no_answer', 'No answer – Phone off'),
        ('wrong_number', 'Wrong number'),
        ('callback_required', 'Callback required'),
    ], string="Feedback")
    lead_ids = fields.Many2many('crm.lead', string="Opportunities")

    def action_add_feedback(self):
        """Create feedback lines for selected leads"""
        for lead in self.lead_ids:
            self.env['crm.feedback'].create({
                'lead_id': lead.id,
                # 'date': self.date,
                'salesperson_id': self.salesperson_id.id,
                'feedback2': self.feedback2,
            })
        return {'type': 'ir.actions.act_window_close'}
    ###########################################################################
    @api.model
    def default_get(self, fields_list):
        """Set default salesperson from first selected lead"""
        res = super(CrmFeedbackWizard, self).default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        if active_ids:
            leads = self.env['crm.lead'].browse(active_ids)

            if leads:
                res['lead_ids'] = [(6, 0, leads.ids)]
                res['salesperson_id'] = leads[0].user_id.id if leads[0].user_id else False
        return res
