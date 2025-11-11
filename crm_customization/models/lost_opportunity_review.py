from odoo import models, fields, api
from datetime import date
import random


class LostOpportunityReview(models.Model):
    _name = 'lost.opportunity.review'
    _description = 'Lost Opportunity Review'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'review_date desc'

    name = fields.Char(string='Review Reference', required=True, copy=False, readonly=True, 
                       default='New', tracking=True)
    review_date = fields.Date(string='Review Date', required=True, default=fields.Date.today, 
                              tracking=True)
    line_ids = fields.One2many('lost.opportunity.review.line', 'review_id', 
                               string='Review Lines')
    total_lost_count = fields.Integer(string='Total Lost Today', 
                                       compute='_compute_lost_counts', store=True)
    reviewed_count = fields.Integer(string='Reviewed Count', 
                                    compute='_compute_lost_counts', store=True)
    review_percentage = fields.Float(string='Review Percentage (%)', 
                                     compute='_compute_lost_counts', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('done', 'Done')
    ], string='Status', default='draft', required=True, tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('lost.opportunity.review') or 'New'
        return super(LostOpportunityReview, self).create(vals)

    @api.depends('line_ids', 'review_date')
    def _compute_lost_counts(self):
        """Compute total lost opportunities and reviewed count for the day"""
        for record in self:
            # Get count of lost opportunities for the review date
            lost_stages = self.env['crm.stage'].search([('is_lost', '=', True)])
            if lost_stages:
                total_lost = self.env['crm.lead'].search_count([
                    ('stage_id', 'in', lost_stages.ids),
                    ('date_closed', '>=', fields.Datetime.to_datetime(record.review_date)),
                    ('date_closed', '<', fields.Datetime.to_datetime(
                        fields.Date.add(record.review_date, days=1)))
                ])
            else:
                # Fallback: search by probability = 0 (lost)
                total_lost = self.env['crm.lead'].search_count([
                    ('probability', '=', 0),
                    ('active', '=', False),
                    ('date_closed', '>=', fields.Datetime.to_datetime(record.review_date)),
                    ('date_closed', '<', fields.Datetime.to_datetime(
                        fields.Date.add(record.review_date, days=1)))
                ])
            
            record.total_lost_count = total_lost
            record.reviewed_count = len(record.line_ids)
            record.review_percentage = (record.reviewed_count / record.total_lost_count * 100) if record.total_lost_count > 0 else 0

    def action_pick_randomly(self):
        """Pick 10% of today's lost opportunities randomly"""
        self.ensure_one()
        
        # Get lost stages (is_lost = True)
        lost_stages = self.env['crm.stage'].search([('is_lost', '=', True)])
        
        # Build domain for today's lost opportunities
        domain = [
            ('date_closed', '>=', fields.Datetime.to_datetime(self.review_date)),
            ('date_closed', '<', fields.Datetime.to_datetime(
                fields.Date.add(self.review_date, days=1)))
        ]
        
        if lost_stages:
            domain.append(('stage_id', 'in', lost_stages.ids))
        else:
            # Fallback to probability-based lost opportunities
            domain.extend([('probability', '=', 0), ('active', '=', False)])
        
        # Get all lost opportunities for today
        lost_opportunities = self.env['crm.lead'].search(domain)
        
        if not lost_opportunities:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Lost Opportunities',
                    'message': 'No lost opportunities found for this date.',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Calculate 10% of total count
        total_count = len(lost_opportunities)
        pick_count = max(1, int(total_count * 0.1))  # At least 1 if there are any
        
        # Get already reviewed lead IDs
        existing_lead_ids = self.line_ids.mapped('lead_id').ids
        
        # Filter out already reviewed opportunities
        available_opportunities = lost_opportunities.filtered(lambda l: l.id not in existing_lead_ids)
        
        if not available_opportunities:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'All Reviewed',
                    'message': 'All lost opportunities for this date have already been added for review.',
                    'type': 'info',
                    'sticky': False,
                }
            }
        
        # Randomly select opportunities
        selected_count = min(pick_count, len(available_opportunities))
        selected_opportunities = random.sample(list(available_opportunities), selected_count)
        
        # Create review lines
        for opportunity in selected_opportunities:
            self.env['lost.opportunity.review.line'].create({
                'review_id': self.id,
                'lead_id': opportunity.id,
                'contact_name': opportunity.partner_id.name or opportunity.contact_name or 'N/A',
                'salesperson_id': opportunity.user_id.id if opportunity.user_id else False,
                'phone_primary': opportunity.phone or opportunity.mobile or 'N/A',
            })
        
        # Update state to in_progress if it was draft
        if self.state == 'draft':
            self.state = 'in_progress'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'{selected_count} opportunities have been added for review.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_add_line(self):
        """Open a wizard to manually add lost opportunities to review"""
        self.ensure_one()
        
        # Get lost stages
        lost_stages = self.env['crm.stage'].search([('is_lost', '=', True)])
        
        # Build domain for today's lost opportunities
        domain = [
            ('date_closed', '>=', fields.Datetime.to_datetime(self.review_date)),
            ('date_closed', '<', fields.Datetime.to_datetime(
                fields.Date.add(self.review_date, days=1)))
        ]
        
        if lost_stages:
            domain.append(('stage_id', 'in', lost_stages.ids))
        else:
            domain.extend([('probability', '=', 0), ('active', '=', False)])
        
        # Get already reviewed lead IDs
        existing_lead_ids = self.line_ids.mapped('lead_id').ids
        if existing_lead_ids:
            domain.append(('id', 'not in', existing_lead_ids))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Select Lost Opportunities',
            'res_model': 'crm.lead',
            'view_mode': 'list',
            'domain': domain,
            'target': 'new',
            'context': {'review_id': self.id}
        }

    def action_mark_done(self):
        """Mark review as done"""
        self.write({'state': 'done'})

    def action_reset_to_draft(self):
        """Reset review to draft"""
        self.write({'state': 'draft'})


class LostOpportunityReviewLine(models.Model):
    _name = 'lost.opportunity.review.line'
    _description = 'Lost Opportunity Review Line'
    _order = 'create_date desc'

    review_id = fields.Many2one('lost.opportunity.review', string='Review', 
                                required=True, ondelete='cascade')
    lead_id = fields.Many2one('crm.lead', string='Opportunity', required=True)
    contact_name = fields.Char(string='Contact Name', required=True)
    salesperson_id = fields.Many2one('res.users', string='Salesperson')
    phone_primary = fields.Char(string='Phone Primary')
    feedback = fields.Selection([
        ('valid', 'Valid'),
        ('not_valid', 'Not Valid')
    ], string='Feedback', help='Validation status of the lost opportunity')
    notes = fields.Text(string='Notes')
    
    # Related fields for convenience
    lead_name = fields.Char(related='lead_id.name', string='Opportunity Name', readonly=True)
    lead_stage = fields.Char(related='lead_id.stage_id.name', string='Stage', readonly=True)
    lost_reason_id = fields.Many2one('crm.lost.reason', related='lead_id.lost_reason_id', string='Lost Reason', readonly=True)

    @api.onchange('lead_id')
    def _onchange_lead_id(self):
        """Auto-fill fields when lead is selected"""
        if self.lead_id:
            self.contact_name = self.lead_id.partner_id.name or self.lead_id.contact_name or 'N/A'
            self.salesperson_id = self.lead_id.user_id.id if self.lead_id.user_id else False
            self.phone_primary = self.lead_id.phone or self.lead_id.mobile or 'N/A'

