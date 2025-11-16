from odoo import models, fields, api, _
from odoo.exceptions import UserError


class LostReviewFeedbackWizard(models.TransientModel):
    _name = 'lost.review.feedback.wizard'
    _description = 'Create Feedback from Lost Review'

    review_id = fields.Many2one('lost.opportunity.review', string='Review', required=True)
    line_ids = fields.Many2many('lost.opportunity.review.line', string='Selected Lines')
    feedback_line_ids = fields.One2many('lost.review.feedback.wizard.line', 'wizard_id', 
                                        string='Feedback Lines')

    @api.model
    def default_get(self, fields_list):
        """Pre-fill lines from context"""
        res = super().default_get(fields_list)
        
        # Get selected line IDs from context
        selected_line_ids = self.env.context.get('selected_line_ids', [])
        if selected_line_ids:
            lines = self.env['lost.opportunity.review.line'].browse(selected_line_ids)
            
            feedback_lines = []
            for line in lines:
                if line.lead_id:  # Ensure lead_id exists
                    feedback_lines.append((0, 0, {
                        'review_line_id': line.id,
                        'lead_id': line.lead_id.id,
                        'contact_name': line.contact_name or '',
                        'salesperson_id': line.salesperson_id.id if line.salesperson_id else False,
                        'phone_primary': line.phone_primary or '',
                        'feedback': 'valid',  # Default to valid
                    }))
            
            if feedback_lines:
                res['feedback_line_ids'] = feedback_lines
        
        return res

    def action_create_feedback(self):
        """Create feedback records"""
        self.ensure_one()
        
        if not self.feedback_line_ids:
            raise UserError(_('No feedback lines to create.'))
        
        created_feedbacks = self.env['lost.opportunity.feedback']
        for line in self.feedback_line_ids:
            # Create Lost Opportunity Feedback
            feedback = self.env['lost.opportunity.feedback'].create({
                'review_id': self.review_id.id,
                'lead_id': line.lead_id.id,
                'contact_name': line.contact_name,
                'salesperson_id': line.salesperson_id.id if line.salesperson_id else False,
                'phone_primary': line.phone_primary,
                'feedback': line.feedback,
                'description': line.description if line.feedback == 'not_valid' else '',
                'date': fields.Date.today(),
                'state': 'draft',
            })
            created_feedbacks |= feedback
            
            # Update the review line with feedback
            if line.review_line_id:
                line.review_line_id.write({
                    'feedback': line.feedback,
                    'notes': line.description if line.feedback == 'not_valid' else ''
                })
        
        # Return action to show created feedbacks
        return {
            'type': 'ir.actions.act_window',
            'name': 'Created Feedback',
            'res_model': 'lost.opportunity.feedback',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_feedbacks.ids)],
            'context': {'create': False},
        }


class LostReviewFeedbackWizardLine(models.TransientModel):
    _name = 'lost.review.feedback.wizard.line'
    _description = 'Feedback Wizard Line'

    wizard_id = fields.Many2one('lost.review.feedback.wizard', string='Wizard', required=True, ondelete='cascade')
    review_line_id = fields.Many2one('lost.opportunity.review.line', string='Review Line')
    lead_id = fields.Many2one('crm.lead', string='Opportunity', required=True)
    contact_name = fields.Char(string='Customer Name')
    salesperson_id = fields.Many2one('res.users', string='Salesperson')
    phone_primary = fields.Char(string='Phone')
    feedback = fields.Selection([
        ('valid', 'Valid'),
        ('not_valid', 'Not Valid')
    ], string='Valid/Not Valid', required=True, default='valid')
    description = fields.Text(string='Description', help='Required if feedback is Not Valid')

    @api.onchange('feedback')
    def _onchange_feedback(self):
        """Clear description if feedback is valid"""
        if self.feedback == 'valid':
            self.description = False

    @api.constrains('feedback', 'description')
    def _check_description(self):
        """Ensure description is filled if feedback is not valid"""
        for record in self:
            if record.feedback == 'not_valid' and not record.description:
                raise UserError(_('Description is required when feedback is "Not Valid".'))

