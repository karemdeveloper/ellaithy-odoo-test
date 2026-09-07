from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestEmployeeSearch(TransactionCase):
    """Employee lookup by code, which is how every assignment field is used."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Employee = cls.env['hr.employee']
        cls.branch = cls.env['ellithy.branch'].create({
            'name': 'Search Branch', 'company_id': cls.env.company.id})
        # Codes chosen so the short one is a prefix of the long ones -- that
        # is exactly the case plain ilike gets wrong.
        cls.short = Employee.create({
            'name': 'Short Code Person', 'employee_code': 'EMP-7',
            'branch_id': cls.branch.id})
        cls.longer = Employee.create({
            'name': 'Longer Code Person', 'employee_code': 'EMP-77',
            'branch_id': cls.branch.id})
        cls.longest = Employee.create({
            'name': 'Longest Code Person', 'employee_code': 'EMP-777',
            'branch_id': cls.branch.id})
        cls.arabic = Employee.create({
            'name': 'Arabic Named Person', 'name_ar': 'موظف عربي',
            'employee_code': 'EMP-901', 'branch_id': cls.branch.id})

    def _ids(self, term, limit=10):
        return [row[0] for row in self.env['hr.employee'].name_search(
            term, limit=limit)]

    def test_code_is_searchable(self):
        self.assertIn(self.longest.id, self._ids('EMP-777'))

    def test_exact_code_ranks_first(self):
        """EMP-7 must not be buried under EMP-77 and EMP-777."""
        ids = self._ids('EMP-7')
        self.assertEqual(ids[0], self.short.id)

    def test_exact_match_is_case_insensitive(self):
        self.assertEqual(self._ids('emp-77')[0], self.longer.id)

    def test_partial_code_still_matches(self):
        ids = self._ids('EMP-7')
        for employee in (self.short, self.longer, self.longest):
            self.assertIn(employee.id, ids)

    def test_name_search_still_works(self):
        self.assertIn(self.short.id, self._ids('Short Code'))

    def test_arabic_name_is_searchable(self):
        self.assertIn(self.arabic.id, self._ids('موظف عربي'))

    def test_limit_is_respected(self):
        self.assertLessEqual(len(self._ids('EMP-7', limit=2)), 2)

    def test_unknown_term_returns_nothing(self):
        self.assertEqual(self._ids('ZZZ-does-not-exist'), [])

    # ---- display name -------------------------------------------------
    def test_display_name_carries_the_code(self):
        self.assertEqual(self.short.display_name,
                         '[EMP-7] Short Code Person')

    def test_display_name_without_a_code_is_just_the_name(self):
        """Only migrated records can lack a code -- create() assigns one
        otherwise, so the migration context is how to produce this case."""
        nameless = self.env['hr.employee'].with_context(
            ellithy_migration=True).create({
                'name': 'No Code Person', 'branch_id': self.branch.id})
        self.assertFalse(nameless.employee_code)
        self.assertEqual(nameless.display_name, 'No Code Person')

    def test_new_employee_gets_a_generated_code(self):
        fresh = self.env['hr.employee'].create({
            'name': 'Generated Code Person', 'branch_id': self.branch.id})
        # CR 2.1 -- the EMP- prefix was dropped; a generated code is now
        # the bare sequence number.
        self.assertTrue(fresh.employee_code)
        self.assertFalse(fresh.employee_code.startswith('EMP-'))

    def test_display_name_is_not_double_prefixed(self):
        """Reading twice must not stack the prefix."""
        self.short.invalidate_recordset(['display_name'])
        first = self.short.display_name
        self.short.invalidate_recordset(['display_name'])
        self.assertEqual(first, self.short.display_name)
        self.assertEqual(first.count('EMP-7'), 1)

    def test_name_search_result_shows_the_code(self):
        rows = self.env['hr.employee'].name_search('EMP-777', limit=1)
        self.assertTrue(rows[0][1].startswith('[EMP-777]'))

    # ---- case insensitivity --------------------------------------------
    def test_code_search_is_case_insensitive_both_ways(self):
        """Stored codes are upper case; typing either case must work."""
        for term in ('EMP-777', 'emp-777', 'Emp-777', 'eMp-777'):
            with self.subTest(term=term):
                self.assertEqual(
                    self._ids(term)[0], self.longest.id,
                    f'{term!r} did not resolve to EMP-777')

    def test_partial_code_search_is_case_insensitive(self):
        upper = self._ids('EMP-7')
        lower = self._ids('emp-7')
        self.assertEqual(set(upper), set(lower))
        self.assertEqual(upper[0], lower[0])

    def test_name_search_is_case_insensitive(self):
        self.assertEqual(set(self._ids('short code')),
                         set(self._ids('SHORT CODE')))

    def test_code_entered_lower_case_is_stored_upper(self):
        """Otherwise 'EMP-950' and 'emp-950' are two different codes as far
        as the unique constraint is concerned."""
        odd = self.env['hr.employee'].create({
            'name': 'Lower Entered', 'employee_code': '  emp-9500  ',
            'branch_id': self.branch.id})
        self.assertEqual(odd.employee_code, 'EMP-9500')
        self.assertEqual(self._ids('EMP-9500')[0], odd.id)
        self.assertEqual(self._ids('emp-9500')[0], odd.id)

    def test_case_variant_code_is_rejected_as_duplicate(self):
        self.env['hr.employee'].create({
            'name': 'Upper Code', 'employee_code': 'EMP-9600',
            'branch_id': self.branch.id})
        with self.assertRaises(Exception):
            self.env['hr.employee'].create({
                'name': 'Lower Code', 'employee_code': 'emp-9600',
                'branch_id': self.branch.id})
            self.env.flush_all()

    def test_department_head_label(self):
        self.assertEqual(
            self.env['hr.department']._fields['manager_id'].string,
            'Department Head')

    def test_department_head_assignable_by_code(self):
        """The end goal: type a code into the head field and get the person."""
        department = self.env['hr.department'].create({
            'name': 'Search Dept', 'dept_type': 'directorate',
            'branch_id': self.branch.id})
        found = self.env['hr.employee'].name_search('EMP-901', limit=1)
        department.manager_id = found[0][0]
        self.assertEqual(department.manager_id, self.arabic)
