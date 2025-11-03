from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    branch_id = fields.Many2one('res.branch', string="Branch")
    area_id = fields.Many2one('res.area', string="Area")
    company_custom_id = fields.Many2one('res.company.custom', string="Company")
    is_opportunity = fields.Boolean(string='Is Opportunity', default=False)
    survey_ids = fields.One2many('res.survey', 'partner_id', string="Surveys")
    crm_source_id = fields.Many2one('res.source', string="Source", required=True)

    def action_open_create_opportunity_wizard(self):
        """Open the wizard popup"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Opportunity',
            'res_model': 'opportunity.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id},
        }

    #############################################################################################

    def action_create_survey(self):
        """Create a new survey for this customer and open it"""
        self.ensure_one()
        survey = self.env['res.survey'].create({
            'partner_id': self.id,  # Customer name automatically filled
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.survey',
            'res_id': survey.id,
            'view_mode': 'form',
            'target': 'current',
        }

    #########################################################################################
    survey_count = fields.Integer(string="Survey Count", compute="_compute_survey_count")

    def _compute_survey_count(self):
        for rec in self:
            rec.survey_count = self.env['res.survey'].search_count([('partner_id', '=', rec.id)])

    def action_view_survey(self):
        """View all surveys linked to this customer"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("crm_customization.action_res_survey")
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action

    #########################################################################################

    @api.onchange('area_id')
    def _onchange_area_id(self):
        for rec in self:
            rec.branch_id = rec.area_id.branch_area.id if rec.area_id else False

    # @api.constrains('phone', 'mobile')
    # def _check_duplicate_phone_mobile(self):
    #     for record in self:
    #         if record.mobile:
    #             duplicate_mobile = self.search([
    #                 ('mobile', '=', record.mobile),
    #                 ('id', '!=', record.id)
    #             ], limit=1)
    #             if duplicate_mobile:
    #                 raise ValidationError("Mobile number already exists for another contact.")
    #
    #         if record.phone:
    #             duplicate_phone = self.search([
    #                 ('phone', '=', record.phone),
    #                 ('id', '!=', record.id)
    #             ], limit=1)
    #             if duplicate_phone:
    #                 raise ValidationError("Phone number already exists for another contact.")

    ###################################################################################################################

    complaint_count = fields.Integer(
        string='Complaints',
        compute='_compute_complaint_count'
    )

    def _compute_complaint_count(self):
        for partner in self:
            partner.complaint_count = self.env['res.complaint'].search_count([
                ('customer_id', '=', partner.id)
            ])

    def action_create_complaint(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Complaint',
            'res_model': 'res.complaint.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_customer_id': self.id},
        }

    def action_view_complaint(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Complaints',
            'res_model': 'res.complaint',
            'view_mode': 'list,form',
            'domain': [('customer_id', '=', self.id)],
            'target': 'current',
        }
    #######################################################################################

    customer_already_exist_id = fields.Many2one(
        'res.partner',
        string="Customer Already Exist",
        compute="_compute_customer_already_exist",
        store=False
    )
    
    # Char field for widget display to avoid Many2one template conflicts
    customer_already_exist_widget = fields.Char(
        string="Existing Customer Widget",
        compute="_compute_customer_already_exist_widget",
        store=False
    )
    
    @api.depends('customer_already_exist_id')
    def _compute_customer_already_exist_widget(self):
        """Dummy field for widget rendering"""
        for rec in self:
            rec.customer_already_exist_widget = str(rec.customer_already_exist_id.id) if rec.customer_already_exist_id else False

    @api.depends('phone')
    def _compute_customer_already_exist(self):
        for rec in self:
            rec.customer_already_exist_id = False
            if rec.phone:
                existing_customer = self.env['res.partner'].search([
                    ('phone', '=', rec.phone),
                    ('id', '!=', rec.id)
                ], limit=1)
                if existing_customer:
                    rec.customer_already_exist_id = existing_customer
    
    @api.onchange('phone')
    def _onchange_phone_check_existing(self):
        """
        Check if customer with same phone exists and show warning
        with option to redirect to existing customer
        """
        if self.phone and not self.id:  # Only for new records
            existing = self.env['res.partner'].search([
                ('phone', '=', self.phone)
            ], limit=1)
            
            if existing:
                # Store the existing customer ID for the widget button
                self.customer_already_exist_id = existing
                
                # Return warning with action
                return {
                    'warning': {
                        'title': _('Customer Already Exists!'),
                        'message': _(
                            'A customer with phone number "%s" already exists:\n'
                            'Name: %s\n'
                            'Click the "Open Existing Customer" button to view the existing record.'
                        ) % (self.phone, existing.name or 'N/A'),
                    }
                }

    def action_open_existing_customer(self):
        """
        Open existing customer form without saving current record.
        This bypasses all field validations and discards the current form.
        """
        # This method works with NewId records (unsaved forms)
        # We access the computed field directly from the recordset
        if hasattr(self, 'customer_already_exist_id') and self.customer_already_exist_id:
            customer_id = self.customer_already_exist_id.id
        else:
            # Fallback: search for existing customer by phone if field not computed
            if self.phone:
                existing = self.env['res.partner'].search([
                    ('phone', '=', self.phone),
                    ('id', '!=', self.id if self.id else 0)
                ], limit=1)
                customer_id = existing.id if existing else False
            else:
                customer_id = False
        
        if not customer_id:
            raise UserError(_("No existing customer found."))
        
        # Return action to open existing customer
        # Using 'target': 'current' will replace current form and discard unsaved changes
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'view_mode': 'form',
            'target': 'current',
            'res_id': customer_id,
            'context': self.env.context,
        }
