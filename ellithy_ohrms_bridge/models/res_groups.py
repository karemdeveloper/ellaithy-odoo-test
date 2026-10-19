from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _ellithy_apply_hcm_document_access(self):
        def update(xmlid, values):
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                record.write(values)

        loan_hr = self.env.ref('ellithy_ohrms_bridge.loan_generalist')
        advance_hr = self.env.ref('ellithy_ohrms_bridge.advance_generalist')
        advance_finance = self.env.ref('ellithy_ohrms_bridge.advance_finance')
        resignation_hr = self.env.ref('ellithy_ohrms_bridge.resignation_generalist')
        resignation_admin = self.env.ref('ellithy_ohrms_bridge.resignation_admin')
        update('ohrms_loan.hr_loan_rule_user', {'groups': [(6, 0, loan_hr.ids)]})
        update('ohrms_loan.hr_loan_rule_company', {
            'domain_force': "[('company_id', 'in', company_ids)]"})
        update('ohrms_salary_advance.hr_salary_advance_manager_rule', {
            'groups': [(6, 0, (advance_hr | advance_finance).ids)]})
        update('ohrms_salary_advance.rule_advance_salary_multi_company', {
            'domain_force': "[('company_id', 'in', company_ids)]"})
        update('hr_resignation.hr_resignation_rule_manager', {
            'groups': [(6, 0, resignation_hr.ids)],
            'domain_force': "[('employee_id.company_id', 'in', company_ids)]"})
        update('ellithy_ohrms_bridge.rule_hr_resignation_clearance_hr', {
            'groups': [(6, 0, resignation_hr.ids)],
            'domain_force': "[('employee_id.company_id', 'in', company_ids)]"})
        # Vendor ACLs are additive, so migrate those too. A menu restriction
        # alone would leave ordinary HR/accounting roles with write access.
        mappings = {
            'ohrms_loan': {'hr.group_hr_user': loan_hr, 'hr.group_hr_manager': loan_hr},
            'ohrms_salary_advance': {
                'hr.group_hr_user': advance_hr,
                'hr.group_hr_manager': self.env.ref('ellithy_ohrms_bridge.advance_admin'),
                'account.group_account_manager': self.env.ref('ellithy_ohrms_bridge.advance_admin')},
            'hr_resignation': {'hr.group_hr_user': resignation_hr,
                               'hr.group_hr_manager': resignation_admin},
        }
        for module, mapping in mappings.items():
            for xmlid in self.env['ir.model.data'].search([
                    ('module', '=', module), ('model', '=', 'ir.model.access')]):
                access = self.env['ir.model.access'].browse(xmlid.res_id)
                for source, target in mapping.items():
                    if access.group_id == self.env.ref(source):
                        access.group_id = target
        # HR letter item 21: employees raise their own advance again. The
        # vendor's employee rule keeps them to their own requests and
        # ``salary.advance.write`` keeps every approval with HR and Finance.
        update('ohrms_salary_advance.access_salary_advance_user', {
            'perm_write': True, 'perm_create': True, 'perm_unlink': False})
        return True
