from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestSocialInsurance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.office = cls.env.ref('ellithy_hr_base.insurance_office_nozha')
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Social Probe',
            'profession': 'محاسب',
        })
        # Insurance is entered on the contract; the employee mirrors it.
        cls.contract = cls.env['hr.contract'].create({
            'name': 'Social Probe Contract',
            'employee_id': cls.employee.id,
            'wage': 3800.0,
            'subscription_wage': 3800.0,
            'total_wage': 4200.0,
            'date_start': '2026-01-01',
            'state': 'open',
            'has_social_insurance': True,
            'social_insurance_office_id': cls.office.id,
            'social_insurance_number': '77897887',
            'social_insurance_start_date': '2026-09-01',
        })

    def test_offices_are_seeded(self):
        """Four offices, not the nine spellings the source holds."""
        offices = self.env['ellithy.hr.insurance.office'].search([])
        self.assertEqual(len(offices), 4)
        self.assertEqual(
            set(offices.mapped('code')), {'nozha', 'bakry', 'nasr1', 'nasr2'})

    def test_office_carries_arabic_name(self):
        self.assertTrue(self.office.name_ar)

    def test_social_fields_reach_the_employee_from_the_contract(self):
        self.assertTrue(self.employee.has_social_insurance)
        self.assertEqual(self.employee.social_insurance_number, '77897887')
        self.assertEqual(str(self.employee.social_insurance_start_date),
                         '2026-09-01')
        self.assertEqual(self.employee.social_insurance_office_id, self.office)
        self.assertEqual(self.employee.profession, 'محاسب')

    def test_the_employee_form_shows_insurance_read_only(self):
        """Entry belongs on the contract, so the employee form cannot edit it.

        Enforced in the view rather than by leaving the field readonly: a
        readonly related field drops an ORM write silently, which would lose
        an import instead of routing it. See the next test.
        """
        # The view's own source, not the resolved arch: the Insurance page
        # is restricted to HR Personnel, so the resolved arch is empty of it
        # for anyone outside that group -- including the test user.
        arch = self.env.ref(
            'ellithy_hr_base.hr_employee_view_form_inherit').arch
        import re
        for name in ('has_social_insurance', 'social_insurance_number',
                     'social_insurance_start_date', 'medical_insurance_type'):
            match = re.search(r'<field name="%s"[^>]*/>' % name, arch)
            self.assertIsNotNone(match, '%s missing from the form' % name)
            self.assertIn('readonly="1"', match.group(0),
                          '%s should be read-only on the employee form' % name)

    def test_a_write_through_the_employee_lands_on_the_contract(self):
        self.employee.social_insurance_number = '11111111'
        self.assertEqual(self.contract.social_insurance_number, '11111111')

    def test_medical_insurance_reaches_the_employee_too(self):
        self.contract.write({
            'medical_insurance_type': 'b',
            'medical_card_number': 'MC-4471',
            'medical_cost_per_month': 180.0,
        })
        self.employee.invalidate_recordset()
        self.assertEqual(self.employee.medical_insurance_type, 'b')
        self.assertEqual(self.employee.medical_card_number, 'MC-4471')
        self.assertAlmostEqual(
            self.employee.medical_cost_per_month, 180.0, places=2)

    def test_an_employee_without_a_contract_shows_no_insurance(self):
        bare = self.env['hr.employee'].create({'name': 'Uninsured'})
        self.assertFalse(bare.has_social_insurance)
        self.assertFalse(bare.social_insurance_number)
        self.assertFalse(bare.medical_insurance_type)

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
