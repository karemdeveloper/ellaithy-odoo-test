from odoo import models, fields, api
from datetime import date
import logging

_logger = logging.getLogger(__name__)

class ResComplaint(models.Model):
    _name = 'res.complaint'
    _description = 'Complaint'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Complaint Reference', required=True, copy=False, readonly=True, 
                       default='New', tracking=True)
    date = fields.Date(string='Date', tracking=True, default=fields.Date.context_today)
    customer_id = fields.Many2one('res.partner', string='Customer', tracking=True, required=True)
    primary_phone = fields.Char(related='customer_id.phone', string='Primary Phone', store=True, readonly=True)
    complaint_reason_id = fields.Many2one('res.complaint.reason', string='Complaint Reason', 
                                          tracking=True, required=True)
    branch_id = fields.Many2one('res.branch', string='Branch', tracking=True)
    department = fields.Many2one('res.department', string='Department', tracking=True, required=True)
    escalation_line_id = fields.Many2one('res.escalation', string='Escalation Line', tracking=True)
    
    # Salesperson from customer
    salesperson_id = fields.Many2one(related='customer_id.user_id', string='Salesperson', 
                                     store=True, readonly=True, tracking=True)
    
    # Assigned to (Many2many)
    assigned_to_ids = fields.Many2many('res.users', string='Assigned To', tracking=True, required=True)
    
    # Remove validity field (valid/not valid)
    # Remove solved_by field
    
    solving_date = fields.Date(string='Solving Date', tracking=True)
    complaint_duration = fields.Integer(string='Complaint Duration (Days)', compute='_compute_complaint_duration', 
                                        store=True, tracking=True)
    complaint_type_id = fields.Many2one('res.complaint.type', string='Type of Complaint', 
                                        tracking=True, required=True)
    
    # SLA Duration from complaint type
    sla_duration = fields.Char(related='complaint_type_id.sla_duration', string='SLA Duration', 
                               store=True, readonly=True)
    
    # Late days (Complaint duration - SLA duration)
    late_days = fields.Integer(string='Late Days', 
                               compute='_compute_late_days', store=True)
    
    # Difference between created on and today
    days_since_creation = fields.Integer(string='Days Since Creation', 
                                         compute='_compute_days_since_creation')
    
    # Creation late days (Days Since Creation - SLA Duration)
    creation_late_days = fields.Integer(string='Creation Late Days',
                                        compute='_compute_creation_late_days')
    
    complaint_state = fields.Selection([
        ('new', 'New'),
        ('under_investigate', 'Under Investigate'),
        ('solved', 'Solved'),
    ], string='Complaint State', tracking=True, default='new')
    
    # Validity field - only in complaint model, not in wizard
    validity = fields.Selection([
        ('valid', 'Valid'),
        ('not_valid', 'Not Valid')
    ], string='Validity', tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('res.complaint') or 'New'
        return super(ResComplaint, self).create(vals)

    @api.onchange('department')
    def _onchange_department(self):
        """Auto-fill assigned_to_ids when department is selected"""
        if self.department and self.department.department_user:
            self.assigned_to_ids = [(6, 0, self.department.department_user.ids)]
        else:
            self.assigned_to_ids = [(5, 0, 0)]  # Clear assigned users

    @api.depends('date', 'solving_date')
    def _compute_complaint_duration(self):
        """Calculate complaint duration in days"""
        for record in self:
            if record.date and record.solving_date:
                start_date = fields.Date.from_string(str(record.date))
                end_date = fields.Date.from_string(str(record.solving_date))
                record.complaint_duration = (end_date - start_date).days
            else:
                record.complaint_duration = 0
    
    @api.depends('complaint_duration', 'sla_duration')
    def _compute_late_days(self):
        """Calculate late days (complaint duration - SLA duration)"""
        for record in self:
            if record.sla_duration and record.complaint_duration:
                try:
                    # Try to parse SLA duration as integer (days)
                    sla_days = int(record.sla_duration)
                    difference = record.complaint_duration - sla_days
                    # If zero or negative, set to 0
                    record.late_days = max(0, difference)
                except ValueError:
                    # If SLA is not a number, set to 0
                    record.late_days = 0
            else:
                record.late_days = 0
    
    @api.depends('create_date')
    def _compute_days_since_creation(self):
        """Calculate days between creation date and today"""
        for record in self:
            if record.create_date:
                created_date = fields.Date.from_string(str(record.create_date.date()))
                today = fields.Date.context_today(record)
                record.days_since_creation = (today - created_date).days
            else:
                record.days_since_creation = 0
    
    @api.depends('days_since_creation', 'sla_duration')
    def _compute_creation_late_days(self):
        """Calculate creation late days (days since creation - SLA duration)"""
        for record in self:
            if record.sla_duration and record.days_since_creation:
                try:
                    # Try to parse SLA duration as integer (days)
                    sla_days = int(record.sla_duration)
                    difference = record.days_since_creation - sla_days
                    # If zero or negative, set to 0
                    record.creation_late_days = max(0, difference)
                except ValueError:
                    # If SLA is not a number, set to 0
                    record.creation_late_days = 0
            else:
                record.creation_late_days = 0

    def action_under_investigate(self):
        for record in self:
            record.complaint_state = 'under_investigate'
            record.message_post(body="Complaint moved to <b>Under Investigation</b> stage.")
        return True

    def action_mark_solved(self):
        for record in self:
            record.complaint_state = 'solved'
            record.solving_date = fields.Date.context_today(self)
            record.message_post(
                body=f"Complaint marked as <b>Solved</b>. Duration: {record.complaint_duration} days.")
        return True

    def action_send_complaint_email(self):
        """Open email composer to send/resend complaint notification"""
        self.ensure_one()
        
        try:
            _logger.info("=" * 80)
            _logger.info(f"Resending email for complaint: {self.name}")
            _logger.info(f"Customer: {self.customer_id.name} (ID: {self.customer_id.id})")
            _logger.info(f"Department: {self.department.name}")
            
            # Prepare email recipients - only partners with valid emails
            partner_ids = []
            partners_without_email = []
            
            # Add customer as first recipient (only if has email)
            if self.customer_id:
                if self.customer_id.email:
                    partner_ids.append(self.customer_id.id)
                    _logger.info(f"✓ Added customer to recipients: {self.customer_id.name} ({self.customer_id.email})")
                else:
                    partners_without_email.append(self.customer_id.name)
                    _logger.warning(f"✗ Customer {self.customer_id.name} has no email address!")
            
            # Add entire department team (all users with matching email domain)
            if self.department and self.department.alias_email:
                _logger.info(f"Department alias email: {self.department.alias_email}")
                # Extract domain from alias email (part after @)
                if '@' in self.department.alias_email:
                    domain = self.department.alias_email.split('@')[1]
                    _logger.info(f"Extracted domain: {domain}")
                    
                    # Find all users with the same email domain and valid email
                    users = self.env['res.users'].search([
                        ('email', 'ilike', f'@{domain}'),
                        ('email', '!=', False)
                    ])
                    _logger.info(f"Found {len(users)} users with domain @{domain}")
                    
                    # Add their partner IDs to recipients (only if partner has email)
                    for user in users:
                        if user.partner_id and user.partner_id.id not in partner_ids:
                            if user.partner_id.email:
                                partner_ids.append(user.partner_id.id)
                                _logger.info(f"  ✓ Added: {user.name} ({user.email})")
                            else:
                                partners_without_email.append(user.name)
                                _logger.warning(f"  ✗ Skipped {user.name} - no email on partner record")

            _logger.info(f"Total recipients with valid emails: {len(partner_ids)}")
            if partners_without_email:
                _logger.warning(f"Partners skipped (no email): {', '.join(partners_without_email)}")
            _logger.info(f"Partner IDs: {partner_ids}")

            # Get email template from complaint type
            template_id = self.complaint_type_id.email_template_id
            
            if not template_id:
                # If no template is set, use default one
                template_id = self.env.ref('crm_customization.email_template_complaint_default', raise_if_not_found=False)
            
            _logger.info(f"Email template: {template_id.display_name if template_id else 'None'}")
            
            # Send individual emails to avoid bulk email limits
            # Mail servers often reject emails with 30+ recipients
            _logger.info("Sending individual emails to each recipient...")
            emails_sent = 0
            emails_failed = 0
            
            for partner_id in partner_ids:
                try:
                    partner = self.env['res.partner'].browse(partner_id)
                    _logger.info(f"Sending to: {partner.name} ({partner.email})")
                    
                    # Use template to send email
                    if template_id:
                        template_id.send_mail(
                            self.id,
                            force_send=True,
                            email_values={
                                'email_to': partner.email,
                                'recipient_ids': [(4, partner_id)],
                            }
                        )
                    else:
                        # Fallback: create mail.mail directly
                        self.env['mail.mail'].sudo().create({
                            'email_to': partner.email,
                            'recipient_ids': [(4, partner_id)],
                            'subject': f'Complaint {self.name}',
                            'body_html': f'<p>Complaint notification for {self.name}</p>',
                            'model': 'res.complaint',
                            'res_id': self.id,
                        }).send()
                    
                    emails_sent += 1
                    _logger.info(f"  ✓ Sent successfully")
                    
                except Exception as e:
                    emails_failed += 1
                    _logger.error(f"  ✗ Failed to send: {str(e)}")
            
            _logger.info("=" * 80)
            _logger.info(f"Email Summary: {emails_sent} sent, {emails_failed} failed")
            _logger.info("=" * 80)
            
            # Return success message
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Emails Sent',
                    'message': f'{emails_sent} emails sent successfully for complaint {self.name}.',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error("=" * 80)
            _logger.error(f"ERROR in complaint email resend:")
            _logger.error(f"Error type: {type(e).__name__}")
            _logger.error(f"Error message: {str(e)}")
            _logger.error("=" * 80)
            import traceback
            _logger.error(traceback.format_exc())
            raise