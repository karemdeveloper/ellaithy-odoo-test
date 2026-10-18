{
    'name': 'Ellaithy Recruitment',
    'version': '18.0.1.0.0',
    'summary': 'Ellaithy hiring flow: application fields, interviewers from employees, '
               'grade-based interview questions, manpower shortage, contact log and '
               'a public application page with QR codes',
    'description': """
Ellaithy Recruitment
====================
Recruitment requirements from the HR letter (items 1-11 of the recruitment
section):

  * Public application page per job (link + QR code) without the website app
  * Interviewers chosen from employees, not only from system users
  * Interview questions per job grade and scored interview evaluations
  * Second / third interview scheduling with an email to the interviewer
  * Manpower shortage register per department
  * Extra candidate fields (national ID, birthdate, military status, ...)
  * Applicant stages agreed with HR, with an automatic rejection email
  * Contact log for candidates reached by phone or WhatsApp
    """,
    'author': 'Ellithy',
    'category': 'Human Resources/Recruitment',
    'license': 'LGPL-3',
    'depends': [
        'hr_recruitment',
        'ellithy_hr_base',
        'calendar',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/recruitment_data.xml',
        'views/interview_views.xml',
        'views/hr_job_views.xml',
        'views/hr_candidate_views.xml',
        'views/hr_applicant_views.xml',
        'views/manpower_views.xml',
        'views/candidate_contact_views.xml',
        'views/careers_templates.xml',
        'wizard/interview_schedule_views.xml',
        'report/recruitment_reports.xml',
        'views/menus.xml',
    ],
    'icon': '/ellithy_recruitment/static/description/icon.png',
    'installable': True,
    'application': False,
}
