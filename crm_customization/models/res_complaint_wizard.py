from odoo import models, fields, api

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
        
        # Create the complaint record using sudo to bypass record rules
        # This allows creating complaints assigned to others without seeing them
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

        # Prepare email recipients based on department alias domain
        partner_ids = []
        email_to_list = []
        
        # Add department alias email if exists
        if self.department and self.department.alias_email:
            email_to_list.append(self.department.alias_email)
            
            # Extract domain from alias email (part after @)
            if '@' in self.department.alias_email:
                domain = self.department.alias_email.split('@')[1]
                
                # Find all users with the same email domain
                users = self.env['res.users'].search([
                    ('email', 'ilike', f'@{domain}')
                ])
                
                # Add their partner IDs for notification
                for user in users:
                    if user.partner_id and user.partner_id.email:
                        partner_ids.append(user.partner_id.id)
        
        # Also add assigned users to recipients
        for user in self.assigned_to_ids:
            if user.partner_id and user.partner_id.email and user.partner_id.id not in partner_ids:
                partner_ids.append(user.partner_id.id)

        # Get email template from complaint type
        template_id = self.complaint_type_id.email_template_id
        
        if not template_id:
            # If no template is set, use default one
            template_id = self.env.ref('crm_customization.email_template_complaint_default', raise_if_not_found=False)
        
        # Send email automatically using template
        if template_id:
            # Create email values
            email_values = {}
            
            # Add additional recipients if needed
            if email_to_list:
                email_values['email_to'] = ','.join(email_to_list)
            
            if partner_ids:
                email_values['recipient_ids'] = [(4, pid) for pid in partner_ids]
            
            # Send the email immediately
            template_id.send_mail(
                complaint.id,
                force_send=True,
                email_values=email_values,
                notif_layout='mail.mail_notification_light'
            )
            
            # Post message in chatter
            complaint.message_post(
                body="Complaint notification email has been sent to the assigned team.",
                subject=f"Email Sent: {complaint.name}",
                message_type='notification',
                subtype_xmlid='mail.mt_comment'
            )
        
        # Return success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Complaint created and notification email sent successfully.',
                'type': 'success',
                'sticky': False,
            }
        }
