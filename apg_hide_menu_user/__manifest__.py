{
    'name': 'Hide Menu User Wise',
    'version': '18.0.0.0',
    'category': 'Extra Tools',
    'summary': 'User-Specific Menu Visibility in Odoo 18, Restrict Menus per User, Customize User Interface, Hide Menus Individually',
    'description': 'Control menu visibility in Odoo 18 on a per-user basis. This module lets you hide specific menu items for individual users without affecting others. Ideal for customizing the user interface, streamlining access, and enhancing security.',
    'author': 'Apagen Solutions Pvt Ltd',
    'company': 'Apagen Solutions Pvt Ltd',
    'maintainer': 'Apagen Solutions Pvt Ltd',
    'website': 'https://www.apagen.com/',
    'depends': ['base'],

    'data': [
        'security/security.xml',
        'views/res_users_views.xml',
    ],
    'license': 'LGPL-3',
    'images': ['static/description/banner.jpg'],
    'installable': True,
    'auto_install': False,
    'application': False,
}
