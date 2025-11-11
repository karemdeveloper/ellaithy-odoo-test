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

##########################################################

    @api.onchange('complaint_type_id')
    def _onchange_complaint_type_id(self):
        """Auto-fill department when complaint type is selected"""
        if self.complaint_type_id:
            self.department = self.complaint_type_id.department_id
        else:
            self.department = False
##########################################################
    @api.onchange('department')
    def _onchange_department_wizard(self):
        """Auto-fill assigned_to_ids when department is selected"""
        if self.department and self.department.department_user:
            self.assigned_to_ids = [(6, 0, self.department.department_user.ids)]
        else:
            self.assigned_to_ids = [(5, 0, 0)]  # Clear assigned users

    def action_confirm(self):
        """ Create complaint record """
        self.ensure_one()
        complaint = self.env['res.complaint'].create({
            'date': self.date,
            'customer_id': self.customer_id.id,
            'complaint_reason_id': self.complaint_reason_id.id,
            'branch_id': self.branch_id.id if self.branch_id else False,
            'department': self.department.id,
            'escalation_line_id': self.escalation_line_id.id if self.escalation_line_id else False,
            'assigned_to_ids': [(6, 0, self.assigned_to_ids.ids)],
            'complaint_type_id': self.complaint_type_id.id,
            'complaint_state': 'new',
        })

        # Send email to assigned users
        if self.assigned_to_ids:
            for user in self.assigned_to_ids:
                if user.email:
                    mail_values = {
                        'subject': f'New Complaint Assigned to You',
                        'body_html': f"""
                                  <p>Hello {user.name},</p>
                                  <p>A new complaint has been assigned to you.</p>
                                  <ul>
                                      <li><b>Customer:</b> {self.customer_id.name}</li>
                                      <li><b>Complaint Type:</b> {self.complaint_type_id.name or ''}</li>
                                      <li><b>Date:</b> {self.date}</li>
                                      <li><b>Reason:</b> {self.complaint_reason_id.name or ''}</li>
                                      <li><b>Department:</b> {self.department.name or ''}</li>
                                      <li><b>SLA Duration:</b> {self.sla_duration or 'N/A'}</li>
                                  </ul>
                                  <p>You can view the complaint in the system for more details.</p>
                                  <p>Best regards,<br/>Complaint Management System</p>
                              """,
                        'email_to': user.email,
                        'email_from': self.env.user.email or 'noreply@example.com',
                    }

                    mail = self.env['mail.mail'].create(mail_values)
                    mail.send()

                    complaint.message_post(
                        body=f"📩 Notification email sent to {user.name} ({user.email}) "
                             f"for new complaint assignment.",
                        subject=f"New Complaint Assigned",
                        message_type='notification',
                    )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.complaint',
            'res_id': complaint.id,
            'view_mode': 'form',
            'target': 'current',
        }
