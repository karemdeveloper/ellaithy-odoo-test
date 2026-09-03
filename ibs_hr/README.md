# IBS HR Flow

Everything that feeds payroll, migrated from the legacy Laravel HR platform.

```
attendance + leave  ->  ibs.hr.attendance.day  --+
violations          ->  ibs.hr.warning         --+--> ibs.hr.payslip
loans / advances    ->  ibs.hr.loan.line       --+
```

## Rules verified against production data

Extracted from `u835352499_hrtest` (149,303 attendance rows, 9,976 payslips,
2,502 warnings) loaded into MariaDB and queried, not inferred from screens.

| Rule | Evidence |
|---|---|
| Daily rate = `basic_salary / 30` | Dividing stored penalty amounts by basic/30 yields clean integer day counts (1, 2, 3, 21, 25) across 3,174 rows |
| `net = total_allowance - total_deduction` | Holds on 9,959 of 9,976 rows |
| `total_allowance` excludes joining/resignation differences | 9,504 of 9,976 rows match without them; only 7,774 match with |
| Employee social insurance = 11% of subscription salary | Egyptian statutory rate; best-fitting candidate against the data |
| `violation_penalties.penalty_value` is in DAYS | Range 0.25–15.00, consistent with day-fines under the Labour Law |
| The `/30` divisor ignores calendar month length | February payslips use the same divisor |

## Legacy defects NOT reproduced

These are bugs in the source system. Reproducing them would import the bug.

**1. `absence_days` stores money, not days.** On 2,915 of 3,174 rows the
column is byte-identical to `absence_penalty`. Any migration that treats it
as a day count produces nonsense. Here `absence_days` is a real day count,
and `test_absence_days_is_a_day_count_not_money` guards it.

**2. `total_deduction` is inconsistent.** 5,112 rows include
`insurance_employee_share` in the total; 3,408 exclude it; roughly 1,456 do
not reconcile to their own line items at all. This module always includes it,
which is the only consistent reading and matches the majority.

**Consequence:** historical payslips are useful for *validating* this engine,
but they are not a specification for it. Where the two disagree, check the
rule with HR rather than assuming the legacy value is right.

## Unresolved — needs HR

**The violation occurrence reset window is not established.** The legacy
database has no reset logic and the UI exposes none. `ibs.hr.warning`
defaults to 12 months via the `ibs_hr.violation_reset_months` config
parameter, which is the common reading of the Egyptian Labour Law but is an
assumption. Getting it wrong produces wrong deductions.

**`violation_penalties.action` is free text** with 19 spellings of roughly
eight actions, several carrying embedded newlines and typos. Migration maps
them onto the canonical `PENALTY_ACTION` selection and keeps the raw string
in `legacy_action` for audit.

## Tests

44 tests, all passing against Odoo 18.0.

```bash
cd .devstack
docker compose run --rm --no-deps -T odoo \
  odoo -d hrtest -u ellithy_hr_base,ibs_hr \
  --test-enable --test-tags ibs_payroll --stop-after-init --http-port=8099
```

Coverage: daily-rate basis, month boundaries incl. leap years, the
net/allowance/deduction invariant, insurance inclusion, absence vs paid
leave, weekend and holiday handling, escalation across occurrences, the
fifth-offence case, approval gating, double-deduction prevention,
cross-midnight shifts, single-punch detection, shortfall flooring, loan
rounding, and instalment release on payslip reset.

## Attendance migration

146,442 days migrated from 149,303 legacy rows (2025-07-01 to 2026-08-29,
882 employees).

| | |
|---|---|
| Agreement with legacy `worked_hour` | 96.17% |
| Minor variance (<1h) | 3,266 |
| Major variance (>=1h) | 2,347 |
| Days over 24h | 0 |
| Overnight shifts | 17,196 |
| Collapsed duplicate groups | 2,780 |

### What the data actually says

**`night_checkin` / `night_checkout` are empty on all 149,303 rows.** Those
columns exist but were never populated. Cross-midnight shifts are detectable
only by `check_out_at < check_in_at`, which is how the loader identifies them
(17,196 days). My earlier reading of these columns was wrong.

**The biometric vendor is ZKTeco.** `check_in_type` splits `zk` 117,974 /
`wifi` 15,841 / `import` 15,488 — answering an open question from the
screen-based analysis.

**`attendance_status` is always 1** on every row. The column carries no
information and is not migrated.

**2,780 employee/date pairs are duplicated**, up to five rows deep. The
pattern is one genuine punch pair plus stray zero-duration terminal re-reads.
The loader collapses each group to earliest check-in / latest check-out and
records the count in `merged_rows`.

### A bug worth recording

The first export used `NULLIF(check_in_at, '')` to normalise blanks. MariaDB
casts `''` to TIME `00:00:00`, so **every midnight punch was silently
discarded** — 99 check-ins and 34 check-outs across 54 employees. One
employee's whole month became 30 single-punch days, which the payroll engine
correctly turned into a fabricated 1,450 EGP penalty.

`MIN()` and `MAX()` already ignore real NULLs, so the `NULLIF` was never
needed. Reconciling computed hours against the legacy's own stored total is
what surfaced it; without that check it would have reached a payslip.
