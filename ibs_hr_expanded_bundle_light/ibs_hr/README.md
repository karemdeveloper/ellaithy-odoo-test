# IBS HR Flow

The attendance and discipline records that feed payroll, migrated from the
legacy Laravel HR platform.

```
attendance + leave  ->  ibs.hr.attendance.day  --+
violations          ->  ibs.hr.warning         --+--> hr.payslip
```

## 18.0.1.1.0 — the custom payroll engine was withdrawn

`ibs.hr.payslip` and `ibs.hr.loan` are gone. Payroll is
`hr_payroll_community`'s `hr.payslip`; loans and advances are OpenHRMS's
`hr.loan` and `salary.advance`, with Ellithy's policy rules living in
`ellithy_ohrms_bridge`.

What survived the move, because it has nowhere else to live:

* `ibs.hr.warning` — the labour-law discipline ladder.
* `ibs.hr.warning.deduction` — the ledger enforcing CR 2.12's five-day
  monthly ceiling, with the remainder carried into following months. A
  penalty is a balance drawn down over months, not a one-off charge, so the
  link to a payslip is a ledger rather than a foreign key.
* The `PENALTY` salary rule and its input, which is how the capped amount
  reaches a standard payslip.

`migrations/18.0.1.1.0/pre-migrate.py` clears the `payslip_id` columns that
still held `ibs_hr_payslip` primary keys. It deliberately does not drop
`ibs_hr_payslip`, `ibs_hr_loan` or `ibs_hr_loan_line` — those hold migrated
history, and dropping them is a decision for whoever runs the upgrade. Row
counts are logged.

The rules below were verified against the legacy data while that engine was
being built. They still describe what the legacy platform did, and remain the
reference for reconciling migrated payslips — but this module no longer
computes them.

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

```bash
cd .devstack
docker compose run --rm --no-deps -T odoo \
  odoo -d hrtest -u ellithy_hr_base,ibs_hr,ellithy_ohrms_bridge \
  --test-enable --test-tags ibs_payroll,ellithy_hr \
  --stop-after-init --http-port=8099
```

Coverage: escalation across occurrences, the fifth-offence case, approval
gating, the five-day monthly ceiling and its carry-over, execution-date
selection, oldest-penalty-first ordering, release on payslip reset,
cross-midnight shifts, single-punch detection and shortfall flooring, and
CR 2.6's annual leave tiers -- 8 annual days plus 7 separate casual days in the first year, 21 after it, 30 on
ten years of insured service, with the boundaries and the allocation
prefill. The loan, advance and resignation rules are tested in
`ellithy_ohrms_bridge`.

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
