from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestSocialInsurance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.office = cls.env.ref('ellithy_hr_base.insurance_office_nozha')
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Social Probe',
            'has_social_insurance': True,
            'social_insurance_office_id': cls.office.id,
            'social_insurance_number': '77897887',
            'social_insurance_start_date': '2026-09-01',
            'profession': 'محاسب',
        })
        cls.contract = cls.env['hr.contract'].create({
            'name': 'Social Probe Contract',
            'employee_id': cls.employee.id,
            'wage': 3800.0,
            'subscription_wage': 3800.0,
            'total_wage': 4200.0,
            'date_start': '2026-01-01',
            'state': 'open',
        })

    def test_offices_are_seeded(self):
        """Four offices, not the nine spellings the source holds."""
        offices = self.env['ellithy.hr.insurance.office'].search([])
        self.assertEqual(len(offices), 4)
        self.assertEqual(
            set(offices.mapped('code')), {'nozha', 'bakry', 'nasr1', 'nasr2'})

    def test_office_carries_arabic_name(self):
        self.assertTrue(self.office.name_ar)

    def test_social_fields_present(self):
        self.assertTrue(self.employee.has_social_insurance)
        self.assertEqual(self.employee.social_insurance_number, '77897887')
        self.assertEqual(str(self.employee.social_insurance_start_date),
                         '2026-09-01')
        self.assertEqual(self.employee.profession, 'محاسب')

    def test_salaries_come_from_the_contract(self):
        self.assertAlmostEqual(self.employee.basic_salary, 3800.0, places=2)
        self.assertAlmostEqual(self.employee.subscription_salary, 3800.0, places=2)
        self.assertAlmostEqual(self.employee.total_salary, 4200.0, places=2)

    def test_writing_salary_updates_the_contract(self):
        self.employee.basic_salary = 4000.0
        self.assertAlmostEqual(self.contract.wage, 4000.0, places=2)

    def test_salary_is_blank_without_a_contract(self):
        """A migrated employee may have no contract; the form must not break."""
        bare = self.env['hr.employee'].create({'name': 'No Contract'})
        self.assertFalse(bare.contract_id)
        self.assertEqual(bare.basic_salary, 0.0)

    def test_office_employee_count(self):
        self.assertGreaterEqual(self.office.employee_count, 1)
