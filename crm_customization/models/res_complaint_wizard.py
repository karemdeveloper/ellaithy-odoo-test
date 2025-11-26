from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ResComplaintWizard(models.TransientModel):
    _name = 'res.complaint.wizard'
    _description = 'Complaint Creation Wizard'

    date = fields.Date(string='Date', default=fields.Date.context_today)
    customer_id = fields.Many2one('res.partner', string='Customer', required=True)
    primary_phone = fields.Char(related='customer_id.phone', string='Primary Phone', store=True, readonly=True)
    complaint_reason_id = fields.Many2one('res.complaint.reason', string='Complaint Reason', required=True)
    branch_id = fields.Many2one('res.branch', string='Branch')
    department = fields.Many2one('res.department', string='Department', required=True)
    escalation_line_id = fields.Many2one('res.escalation', string='Escalation Line')
    
    # Salesperson from customer
    salesperson_id = fields.Many2one(related='customer_id.user_id', string='Salesperson', readonly=True)
    
    # Assigned to (Many2many)
    assigned_to_ids = fields.Many2many('res.users', string='Assigned To', required=True)
    
    # Remove validity and solved_by fields
    complaint_type_id = fields.Many2one('res.complaint.type', string='Type of Complaint', required=True)
    
    # Show SLA from complaint type
    sla_duration = fields.Char(related='complaint_type_id.sla_duration', string='SLA Duration', readonly=True)

    @api.model
    def default_get(self, fields_list):
        """ Pre-fill customer when opened from partner """
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'res.partner':
            res['customer_id'] = self.env.context.get('active_id')
        return res

    @api.onchange('complaint_type_id')
    def _onchange_complaint_type_id(self):
        """Auto-fill department when complaint type is selected"""
        if self.complaint_type_id:
            self.department = self.complaint_type_id.department_id
        else:
            self.department = False
    
    @api.onchange('department')
    def _onchange_department(self):
        """Auto-fill assigned_to_ids when department is selected"""
        if self.department and self.department.department_user:
            self.assigned_to_ids = [(6, 0, self.department.department_user.ids)]
        else:
            self.assigned_to_ids = [(5, 0, 0)]  # Clear assigned users

    def action_send_and_create(self):
        """ Create complaint record and open email composer """
        self.ensure_one()
        
        try:
            _logger.info("=" * 80)
            _logger.info("Creating complaint and preparing email...")
            _logger.info(f"Customer: {self.customer_id.name} (ID: {self.customer_id.id})")
            _logger.info(f"Department: {self.department.name}")
            
            # Create the complaint record using sudo to bypass record rules
            complaint = self.env['res.complaint'].sudo().create({
                'date': self.date,
                'customer_id': self.customer_id.id,
                'complaint_reason_id': self.complaint_reason_id.id,
                'branch_id': self.branch_id.id if self.branch_id else False,
                'department': self.department.id,
                'escalation_line_id': self.escalation_line_id.id if self.escalation_line_id else False,
                'assigned_to_ids': [(6, 0, self.assigned_to_ids.ids)],
                'complaint_type_id': self.complaint_type_id.id,
                'complaint_state': 'under_investigate',
            })
            _logger.info(f"✓ Complaint created: {complaint.name} (ID: {complaint.id})")

            # Prepare email recipients - only partners with valid emails
            partner_ids = []
            partners_without_email = []
            
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
            
            # Get email_from from template (rendered for this complaint)
            email_from = False
            if template_id and hasattr(template_id, 'email_from') and template_id.email_from:
                email_from = template_id._render_field('email_from', [complaint.id])[complaint.id]
                _logger.info(f"Template email_from rendered: {email_from}")
            
            final_email_from = email_from or self.env.user.email_formatted
            
            # SOLUTION: Use mass_mail mode which properly handles email_from
            # This mode creates mail.mail records directly with the correct email_from
            ctx = {
                'default_model': 'res.complaint',
                'default_res_ids': str([complaint.id]),  # Must be string representation
                'default_use_template': bool(template_id),
                'default_template_id': template_id.id if template_id else False,
                'default_composition_mode': 'mass_mail',  # mass_mail properly handles email_from
                'default_partner_ids': partner_ids,  # All recipients
                'default_email_from': final_email_from,  # This will be used in mail.mail creation
                'default_author_id': self.env.user.partner_id.id,
            }
            
            _logger.info("Composer context (mass_mail mode):")
            _logger.info(f"  - Model: {ctx['default_model']}")
            _logger.info(f"  - Res IDs: {ctx['default_res_ids']}")
            _logger.info(f"  - Mode: {ctx['default_composition_mode']}")
            _logger.info(f"  - Template ID: {ctx['default_template_id']}")
            _logger.info(f"  - Partner IDs count: {len(ctx['default_partner_ids'])}")
            _logger.info(f"  - Email From: {final_email_from}")
            _logger.info("✓ Opening email composer...")
            _logger.info("=" * 80)

            # Open the email composer
            return {
                'type': 'ir.actions.act_window',
                'name': 'Send Complaint Notification',
                'res_model': 'mail.compose.message',
                'view_mode': 'form',
                'target': 'new',
                'context': ctx,
            }
            
        except Exception as e:
            _logger.error("=" * 80)
            _logger.error(f"ERROR in complaint creation:")
            _logger.error(f"Error type: {type(e).__name__}")
            _logger.error(f"Error message: {str(e)}")
            _logger.error("=" * 80)
            import traceback
            _logger.error(traceback.format_exc())
            raise
