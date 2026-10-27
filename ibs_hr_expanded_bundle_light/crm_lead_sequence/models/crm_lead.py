from odoo import models, fields, api


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # Make name field readonly to prevent manual editing of the sequence
    name = fields.Char(
        'Opportunity',
        required=True,
        index='trigram',
        tracking=True,
        readonly=True,
    )

    def _get_sequence_code(self, branch_id, year, month):
        """Generate sequence code for branch/year/month combination"""
        return f'crm.lead.{branch_id}.{year}.{month}'

    def _get_or_create_sequence(self, branch_id, year, month):
        """Get or create sequence for specific branch/year/month"""
        sequence_code = self._get_sequence_code(branch_id, year, month)
        sequence = self.env['ir.sequence'].search([
            ('code', '=', sequence_code)
        ], limit=1)
        
        if not sequence:
            # Create new sequence for this branch/month
            sequence = self.env['ir.sequence'].sudo().create({
                'name': f'CRM Lead - Branch {branch_id} - {year}/{month}',
                'code': sequence_code,
                'padding': 4,
                'number_increment': 1,
                'number_next': 1,
                'implementation': 'standard',
            })
        
        return sequence

    def _generate_lead_name(self, branch_id):
        """Generate lead name with format: BranchCode/Year/Month/Number"""
        if not branch_id:
            return self.env['ir.sequence'].next_by_code('crm.lead') or 'New'
        
        branch = self.env['res.branch'].browse(branch_id)
        branch_code = branch.branch_code or 'XX'
        
        # Get current date
        now = fields.Datetime.now()
        year = now.strftime('%Y')
        month = now.strftime('%m')
        
        # Get or create sequence for this branch/month
        sequence = self._get_or_create_sequence(branch_id, year, month)
        number = sequence.next_by_id()
        
        # Extract just the number part from sequence (remove any prefix/suffix)
        try:
            number_str = str(int(number))
        except:
            number_str = number
        
        return f"{branch_code}/{year}/{month}/{number_str.zfill(4)}"

    # @api.model
    # def create(self, vals_list):
    #     """Override create to set custom name based on branch sequence"""
    #     if isinstance(vals_list, dict):
    #         vals_list = [vals_list]
    #
    #     for vals in vals_list:
    #         branch_id = vals.get('branch_name')
    #         if branch_id and not vals.get('name'):
    #             vals['name'] = self._generate_lead_name(branch_id)
    #
    #     records = super(CrmLead, self).create(vals_list)
    #     # Post sequence in chatter
    #     for record in records:
    #         if record.name:
    #             record.message_post(
    #                 body=f"Opportunity Reference:{record.name}"
    #             )
    #
    #     return records

    # now, we will not use this method, but it can be used in the future if we want to update existing leads with new sequence format
    # @api.model
    # def action_update_existing_leads(self):
    #     """Update all existing leads with new sequence format"""
    #     leads = self.env['crm.lead'].search([
    #         ('branch_name', '!=', False),
    #         ('create_date', '!=', False)
    #     ], order='create_date asc')
    #
    #     # Group leads by branch, year, month
    #     grouped_leads = {}
    #     for lead in leads:
    #         if not lead.branch_name or not lead.create_date:
    #             continue
    #
    #         create_date = fields.Datetime.from_string(lead.create_date)
    #         year = create_date.strftime('%Y')
    #         month = create_date.strftime('%m')
    #         key = (lead.branch_name.id, year, month)
    #
    #         if key not in grouped_leads:
    #             grouped_leads[key] = []
    #         grouped_leads[key].append(lead)
    #
    #     # Update leads with proper sequence
    #     for (branch_id, year, month), lead_list in grouped_leads.items():
    #         branch = self.env['res.branch'].browse(branch_id)
    #         branch_code = branch.branch_code or 'XX'
    #
    #         # Get or create sequence for this group
    #         sequence = self._get_or_create_sequence(branch_id, year, month)
    #
    #         # Reset sequence to 1 for this batch
    #         sequence.sudo().write({'number_next': 1})
    #
    #         # Update each lead in chronological order
    #         for lead in lead_list:
    #             number = sequence.next_by_id()
    #             try:
    #                 number_str = str(int(number))
    #             except:
    #                 number_str = number
    #
    #             new_name = f"{branch_code}/{year}/{month}/{number_str.zfill(4)}"
    #             lead.sudo().write({'name': new_name})
    #
    #     return True
