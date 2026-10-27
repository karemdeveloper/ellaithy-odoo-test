import re

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestFormLayout(TransactionCase):
    """What the employee and contract forms offer, and what they no longer do.

    Read from the views' own source rather than the resolved arch: the
    insurance pages are restricted to HR Personnel, so a resolved arch is
    empty of them for anyone outside that group, including the test user.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee_arch = cls.env.ref(
            'ellithy_hr_base.hr_employee_view_form_inherit').arch
        cls.contract_arch = cls.env.ref(
            'ellithy_hr_base.hr_contract_view_form_inherit').arch

    def _page(self, arch, name):
        return re.search(r'<page [^>]*name="%s"' % name, arch)

    def test_the_contract_separates_the_two_insurances(self):
        for name in ('ellithy_social_insurance', 'ellithy_medical_insurance'):
            self.assertTrue(self._page(self.contract_arch, name),
                            '%s missing from the contract form' % name)
        self.assertIsNone(self._page(self.contract_arch, 'ellithy_insurance'))

    def test_the_employee_mirrors_both_tabs(self):
        for name in ('ellithy_social_insurance', 'ellithy_medical_insurance'):
            self.assertTrue(self._page(self.employee_arch, name),
                            '%s missing from the employee form' % name)
        self.assertIsNone(self._page(self.employee_arch, 'ellithy_insurance'))

    def test_the_mirrored_medical_figures_cannot_be_edited_on_the_employee(self):
        """Entry belongs on the contract; the mirror only reports it."""
        for name in ('medical_insurance_type', 'medical_insurance_date',
                     'medical_card_number', 'medical_cost_per_year',
                     'medical_cost_per_month', 'medical_employee_share',
                     'has_medical_relative'):
            match = re.search(r'<field name="%s"[^>]*/>' % name,
                              self.employee_arch)
            self.assertIsNotNone(match, '%s missing from the form' % name)
            self.assertIn('readonly="1"', match.group(0),
                          '%s should be read-only on the employee form' % name)

    def test_relatives_are_editable_from_both_forms(self):
        for arch, where in ((self.employee_arch, 'employee'),
                            (self.contract_arch, 'contract')):
            match = re.search(r'<field name="dependant_ids"[^>]*>', arch)
            self.assertIsNotNone(match, 'relatives missing from the %s' % where)
            self.assertNotIn('readonly="1"', match.group(0),
                             'relatives should stay editable on the %s' % where)

    def test_the_employee_relatives_list_does_not_hide_behind_the_flag(self):
        """The coverage flag is the contract's to set, so it cannot gate the
        list: an employee between contracts would lose rows that exist."""
        match = re.search(r'<field name="dependant_ids"[^>]*>',
                          self.employee_arch)
        self.assertNotIn('has_medical_relative', match.group(0))

    def test_the_employee_form_carries_no_exit_tab(self):
        """CR C1: one authoritative exit route, the resignation request.

        Departure, suspension and blacklist fields stay on the model -- the
        resignation flow writes them -- but the employee form no longer
        offers a second place to type them in."""
        self.assertIsNone(self._page(self.employee_arch, 'ellithy_exit'))
        self.assertNotIn('resignation_date', self.employee_arch)
        self.assertNotIn('suspension_start', self.employee_arch)
