{
    'name': 'Ellaithy HR Base',
    'version': '18.0.1.5.0',
    'summary': 'Employee directory, org structure and HR master data migrated from the legacy Laravel HR platform',
    'description': """
Ellithy HR Base
===============
Foundation module for the Ellaithy HR migration. Reproduces the legacy
employee directory in Odoo 18 Community.

Provides:
  * Branch model (Odoo Community has no branch concept)
  * Five-level org structure: company > branch > department > section > position
  * Job grade ladder
  * Employee master extended to cover the legacy ``users`` table (156 columns)
  * Child models for dependants, HR documents and payout accounts
  * Contract extension carrying the Egyptian salary and insurance figures
  * Exit workflow with the legacy's resignation/last-working-day integrity rule

Every model carries ``legacy_id`` so migration runs stay idempotent and
reconcilable against the source MariaDB database.
    """,
    'author': 'Ellithy',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'hr_contract',
        'mail',
    ],
    'data': [
        'security/ellithy_hr_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'data/ellithy_hr_grade_data.xml',
        'data/ellithy_hr_document_type_data.xml',
        'data/ellithy_hr_suspension_reason_data.xml',
        'data/ellithy_hr_insurance_office_data.xml',
        'views/ellithy_branch_views.xml',
        'views/ellithy_hr_grade_views.xml',
        'views/ellithy_hr_reference_views.xml',
        'views/ellithy_hr_line_views.xml',
        'views/hr_department_views.xml',
        'views/hr_job_views.xml',
        'views/hr_contract_views.xml',
        'views/hr_employee_views.xml',
        'wizard/hr_welcome_mail_wizard_views.xml',
        'views/menus.xml',
    ],
    'icon': '/ellithy_hr_base/static/description/icon.png',
    'installable': True,
    'application': True,
    'auto_install': False,
}
