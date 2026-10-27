{
    'name': """Employee End Of Service Rewards """,
    'summary': """End Of Service reward for years of services, approvals and disbursements""",
    'description': """Create and Cal    culate your employees END OF SERVICE Reward""",
    'version': '18.0.1.0.0',
    'sequence': 4,
    "author": "Elaraby",
    "email": 'elarabym31995@gmail.com',
    'depends': ['base', 'hr', 'account', 'hr_contract', 'hr_payroll_community'],
    'category': 'HR',
    'data':
        ['security/ir.model.access.csv',
         'views/end_reward_views.xml',
         'views/end_service_views.xml',
         'views/contract_view_inherit.xml',
         'report/end_rewards.xml',
         'report/end_service.xml',
         ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
    'demo': []
}
