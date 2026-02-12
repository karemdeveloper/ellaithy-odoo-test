{
    'name': 'CRM Lead Sequence',
    'version': '18.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Custom sequence for CRM opportunities based on branch, year, and month',
    'description': """
        CRM Lead Sequence Module
        ========================
        This module provides:
        - Custom sequence format: BranchCode/Year/Month/Number
        - Automatic sequence generation for new opportunities
        - Update functionality for existing opportunities
        - Sequence resets monthly per branch
    """,
    'depends': ['crm', 'crm_customization'],
    'data': [
        'views/crm_lead_views.xml',
        'data/update_existing_leads.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
