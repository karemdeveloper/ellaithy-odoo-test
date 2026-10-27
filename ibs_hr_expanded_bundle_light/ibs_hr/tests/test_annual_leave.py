from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import tagged

from .common import IbsHrCommon


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestAnnualLeaveEntitlement(IbsHrCommon):
    """CR 2.6 -- 15 days in the first year, unless insured service says 30.

    The dates are all expressed as offsets from today rather than as fixed
    calendar dates, because the entitlement is answered as at today and a
    hard-coded 2026 date would start failing on its own anniversary.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env['hr.employee'])
        cls.annual_type = cls.env['hr.leave.type'].create({
            'name': 'Annual Leave',
            'is_annual_entitlement': True,
            'requires_allocation': 'yes',
        })
        cls.other_type = cls.env['hr.leave.type'].create({
            'name': 'Casual Leave',
            'is_annual_entitlement': False,
            'requires_allocation': 'yes',
        })

    def _employee(self, joined_months_ago=None, insured_years_ago=None,
                  contract=True):
        """An employee whose service and insured service are set by offset.

        The insurance date lives on the contract, so the fixture creates one
        even when the test only cares about the joining date -- writing the
        related field on an employee without a contract would be dropped.
        ``contract=False`` is for the one case that needs an employee with no
        joining date at all: ``ellithy_ohrms_bridge`` fills an empty joining
        date from the earliest contract, so a contract would supply one.
        """
        joined = insured = False
        if joined_months_ago is not None:
            joined = self.today - relativedelta(months=joined_months_ago)
        if insured_years_ago is not None:
            insured = self.today - relativedelta(years=insured_years_ago)
        employee = self.env['hr.employee'].create({
            'name': 'Entitlement Subject',
            'branch_id': self.branch.id,
            'joining_date': joined,
        })
        if contract:
            self.env['hr.contract'].create({
                'name': 'Contract',
                'employee_id': employee.id,
                'wage': 3000.0,
                'date_start': joined or self.today,
                'state': 'open',
                'has_social_insurance': bool(insured),
                'social_insurance_start_date': insured,
            })
        return employee

    # ------------------------------------------------------------------
    # The three tiers
    # ------------------------------------------------------------------
    def test_first_year_gets_fifteen_days(self):
        employee = self._employee(joined_months_ago=3)
        self.assertEqual(employee.annual_leave_entitlement, 15.0)

    def test_after_the_first_year_gets_twenty_one_days(self):
        employee = self._employee(joined_months_ago=18)
        self.assertEqual(employee.annual_leave_entitlement, 21.0)

    def test_ten_years_insured_gets_thirty_days(self):
        employee = self._employee(joined_months_ago=36, insured_years_ago=12)
        self.assertEqual(employee.annual_leave_entitlement, 30.0)

    # ------------------------------------------------------------------
    # The conflict the requirement warns about
    # ------------------------------------------------------------------
    def test_first_year_does_not_undercut_ten_years_insured(self):
        """A new joiner who arrives with insured service keeps the 30 days."""
        employee = self._employee(joined_months_ago=2, insured_years_ago=11)
        self.assertEqual(employee.annual_leave_entitlement, 30.0)

    def test_nine_years_insured_is_still_a_first_year_joiner(self):
        employee = self._employee(joined_months_ago=2, insured_years_ago=9)
        self.assertEqual(employee.annual_leave_entitlement, 15.0)

    # ------------------------------------------------------------------
    # Boundaries
    # ------------------------------------------------------------------
    def test_the_day_before_the_anniversary_is_still_the_first_year(self):
        employee = self._employee()
        employee.joining_date = self.today - relativedelta(years=1, days=-1)
        self.assertEqual(employee.annual_leave_entitlement, 15.0)

    def test_the_anniversary_itself_moves_to_twenty_one(self):
        employee = self._employee()
        employee.joining_date = self.today - relativedelta(years=1)
        self.assertEqual(employee.annual_leave_entitlement, 21.0)

    def test_the_tenth_insured_anniversary_moves_to_thirty(self):
        employee = self._employee(joined_months_ago=2)
        employee.social_insurance_start_date = (
            self.today - relativedelta(years=10))
        self.assertEqual(employee.annual_leave_entitlement, 30.0)

    def test_one_day_short_of_ten_insured_years_stays_on_the_lower_tier(self):
        employee = self._employee(joined_months_ago=2)
        employee.social_insurance_start_date = (
            self.today - relativedelta(years=10) + relativedelta(days=1))
        self.assertEqual(employee.annual_leave_entitlement, 15.0)

    # ------------------------------------------------------------------
    # Missing data
    # ------------------------------------------------------------------
    def test_without_a_joining_date_the_standard_tier_applies(self):
        """Missing data must not be read as "first year" and pay 15."""
        employee = self._employee(contract=False)
        self.assertFalse(employee.joining_date)
        self.assertEqual(employee.annual_leave_entitlement, 21.0)

    # ------------------------------------------------------------------
    # The figures are policy, not constants
    # ------------------------------------------------------------------
    def test_the_tiers_follow_the_config_parameters(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'ibs_hr.annual_leave_first_year_days', '16')
        self.env['ir.config_parameter'].sudo().set_param(
            'ibs_hr.annual_leave_long_service_years', '8')
        first_year = self._employee(joined_months_ago=4)
        long_service = self._employee(joined_months_ago=4, insured_years_ago=9)
        self.assertEqual(first_year.annual_leave_entitlement, 16.0)
        self.assertEqual(long_service.annual_leave_entitlement, 30.0)

    # ------------------------------------------------------------------
    # The tier field on the employee file
    # ------------------------------------------------------------------
    def test_a_new_employee_starts_on_the_fifteen_day_tier(self):
        """``vacation_role`` defaults to the first-year tier.

        It is a stated figure rather than a computed one -- HR raises it for
        someone who arrives with insured service behind them -- so the
        default is the tier a genuine new joiner is on.
        """
        employee = self.env['hr.employee'].create({
            'name': 'Fresh Joiner',
            'branch_id': self.branch.id,
        })
        self.assertEqual(employee.vacation_role, '15')

    # ------------------------------------------------------------------
    # What HR actually sees: the allocation form
    # ------------------------------------------------------------------
    def test_allocation_is_prefilled_from_the_entitlement(self):
        employee = self._employee(joined_months_ago=3)
        allocation = self.env['hr.leave.allocation'].new({
            'name': 'Annual 2026',
            'employee_id': employee.id,
            'holiday_status_id': self.annual_type.id,
        })
        allocation._onchange_annual_entitlement()
        self.assertEqual(allocation.number_of_days, 15.0)

    def test_a_non_annual_type_is_left_alone(self):
        employee = self._employee(joined_months_ago=3)
        allocation = self.env['hr.leave.allocation'].new({
            'name': 'Casual 2026',
            'employee_id': employee.id,
            'holiday_status_id': self.other_type.id,
            'number_of_days': 7.0,
        })
        allocation._onchange_annual_entitlement()
        self.assertEqual(allocation.number_of_days, 7.0)

    def test_changing_the_employee_refills_the_figure(self):
        """The prefill follows a correction rather than sticking."""
        allocation = self.env['hr.leave.allocation'].new({
            'name': 'Annual 2026',
            'employee_id': self._employee(joined_months_ago=3).id,
            'holiday_status_id': self.annual_type.id,
        })
        allocation._onchange_annual_entitlement()
        self.assertEqual(allocation.number_of_days, 15.0)
        allocation.employee_id = self._employee(
            joined_months_ago=3, insured_years_ago=11)
        allocation._onchange_annual_entitlement()
        self.assertEqual(allocation.number_of_days, 30.0)
