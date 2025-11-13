from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date
import random


class LostOpportunityReview(models.Model):
    _name = 'lost.opportunity.review'
    _description = 'Lost Opportunity Review'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'review_date desc'

    name = fields.Char(string='Review Reference', required=True, copy=False, readonly=True, 
                       default='New', tracking=True)
    date_from = fields.Date(string='Date From', required=True, default=fields.Date.today, 
                           tracking=True)
    date_to = fields.Date(string='Date To', required=True, default=fields.Date.today, 
                         tracking=True)
    review_date = fields.Date(string='Review Date', required=True, default=fields.Date.today, 
                              tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True)
    line_ids = fields.One2many('lost.opportunity.review.line', 'review_id', 
                               string='Review Lines')
    total_lost_count = fields.Integer(string='Total Lost in Period', 
                                       compute='_compute_lost_counts', store=True)
    reviewed_count = fields.Integer(string='Reviewed Count', 
                                    compute='_compute_lost_counts', store=True)
    ten_percent_count = fields.Integer(string='10% Count', 
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

    @api.onchange('date_from', 'date_to')
    def _onchange_dates(self):
        """Auto-load lost opportunities when dates change"""
        # Only auto-load for existing records (records that have been saved)
        if self.id and self.date_from and self.date_to and self.state != 'done':
            # Auto-load opportunities when dates change
            self._load_opportunities()

    @api.depends('line_ids', 'date_from', 'date_to')
    def _compute_lost_counts(self):
        """Compute total lost opportunities and reviewed count for the date range"""
        for record in self:
            if not record.date_from or not record.date_to:
                record.total_lost_count = 0
                record.ten_percent_count = 0
                record.reviewed_count = 0
                record.review_percentage = 0
                continue
            
            # Get lost stages
            lost_stages = self.env['crm.stage'].search([('is_lost', '=', True)])
            
            # Build base domain
            domain = [
                ('date_closed', '!=', False),
                ('date_closed', '>=', f"{record.date_from} 00:00:00"),
                ('date_closed', '<=', f"{record.date_to} 23:59:59"),
            ]
            
            # Add stage condition
            if lost_stages:
                domain.append(('stage_id', 'in', lost_stages.ids))
            else:
                # Fallback: search by lost_reason_id (if opportunity has lost reason, it's lost)
                domain.append(('lost_reason_id', '!=', False))
            
            total_lost = self.env['crm.lead'].search_count(domain)
            
            record.total_lost_count = total_lost
            record.ten_percent_count = max(1, int(total_lost * 0.1)) if total_lost > 0 else 0
            record.reviewed_count = len(record.line_ids)
            record.review_percentage = (record.reviewed_count / record.total_lost_count * 100) if record.total_lost_count > 0 else 0

    @api.onchange('line_ids')
    def _onchange_line_count(self):
        """Warn if selecting more than 10% of lost opportunities"""
        selected_count = len(self.line_ids.filtered(lambda l: l.selected))
        if self.ten_percent_count > 0 and selected_count > self.ten_percent_count:
            return {
                'warning': {
                    'title': 'Exceeding 10% Target',
                    'message': f'You are selecting {selected_count} opportunities, but 10% of the total ({self.total_lost_count}) is only {self.ten_percent_count}.\n'
                               f'You can proceed, but this exceeds the recommended target.'
                }
            }

    def action_pick_randomly(self):
        """Pick 10% of period's lost opportunities randomly"""
        self.ensure_one()
        
        # Get lost stages (is_lost = True)
        lost_stages = self.env['crm.stage'].search([('is_lost', '=', True)])
        
        # Build domain for date range lost opportunities
        domain = [
            ('date_closed', '!=', False),
            ('date_closed', '>=', f"{self.date_from} 00:00:00"),
            ('date_closed', '<=', f"{self.date_to} 23:59:59"),
        ]
        
        if lost_stages:
            domain.append(('stage_id', 'in', lost_stages.ids))
        else:
            # Fallback: search by lost_reason_id
            domain.append(('lost_reason_id', '!=', False))
        
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

    def _load_opportunities(self):
        """Internal method to load lost opportunities"""
        self.ensure_one()
        
        if not self.date_from or not self.date_to:
            return
        
        # Get lost stages
        lost_stages = self.env['crm.stage'].search([('is_lost', '=', True)])
        
        # Build domain for date range lost opportunities
        domain = [
            ('date_closed', '!=', False),
            ('date_closed', '>=', f"{self.date_from} 00:00:00"),
            ('date_closed', '<=', f"{self.date_to} 23:59:59"),
        ]
        
        if lost_stages:
            domain.append(('stage_id', 'in', lost_stages.ids))
        else:
            # Fallback: search by lost_reason_id
            domain.append(('lost_reason_id', '!=', False))
        
        # Get all lost opportunities in period
        lost_opportunities = self.env['crm.lead'].search(domain)
        
        # Clear existing lines
        self.line_ids.unlink()
        
        if lost_opportunities:
            # Create lines for all lost opportunities (readonly, with tick checkbox)
            for opportunity in lost_opportunities:
                self.env['lost.opportunity.review.line'].create({
                    'review_id': self.id,
                    'lead_id': opportunity.id,
                    'contact_name': opportunity.partner_id.name or opportunity.contact_name or 'N/A',
                    'salesperson_id': opportunity.user_id.id if opportunity.user_id else False,
                    'phone_primary': opportunity.phone or opportunity.mobile or 'N/A',
                    'selected': False,  # Not selected by default
                })
            
            # Update state to in_progress
            if self.state == 'draft':
                self.state = 'in_progress'

    def action_load_lost_opportunities(self):
        """Load all lost opportunities in the date range (button action)"""
        self.ensure_one()
        
        self._load_opportunities()
        
        if not self.line_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Lost Opportunities',
                    'message': 'No lost opportunities found for this date range.',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'{len(self.line_ids)} lost opportunities have been loaded. Please tick the ones to review.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_add_line(self):
        """Open a wizard to manually add lost opportunities to review"""
        self.ensure_one()
        
        # Get lost stages
        lost_stages = self.env['crm.stage'].search([('is_lost', '=', True)])
        
        # Build domain for date range lost opportunities
        domain = [
            ('date_closed', '!=', False),
            ('date_closed', '>=', f"{self.date_from} 00:00:00"),
            ('date_closed', '<=', f"{self.date_to} 23:59:59"),
        ]
        
        if lost_stages:
            domain.append(('stage_id', 'in', lost_stages.ids))
        else:
            # Fallback: search by lost_reason_id
            domain.append(('lost_reason_id', '!=', False))
        
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

    def action_create_feedback(self):
        """Create feedback records for selected lines"""
        self.ensure_one()
        
        # Get selected lines
        selected_lines = self.line_ids.filtered(lambda l: l.selected)
        
        if not selected_lines:
            raise UserError(_('Please select at least one opportunity to create feedback.'))
        
        # Open wizard to create feedback
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Feedback',
            'res_model': 'lost.review.feedback.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_review_id': self.id,
                'selected_line_ids': selected_lines.ids,  # Pass as custom context key
            }
        }


class LostOpportunityReviewLine(models.Model):
    _name = 'lost.opportunity.review.line'
    _description = 'Lost Opportunity Review Line'
    _order = 'create_date desc'

    review_id = fields.Many2one('lost.opportunity.review', string='Review', 
                                required=True, ondelete='cascade')
    lead_id = fields.Many2one('crm.lead', string='Opportunity', required=True, readonly=True)
    selected = fields.Boolean(string='Select', default=False, help='Tick to include in feedback creation')
    contact_name = fields.Char(string='Contact Name', required=True, readonly=True)
    salesperson_id = fields.Many2one('res.users', string='Salesperson', readonly=True)
    phone_primary = fields.Char(string='Phone Primary', readonly=True)
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

