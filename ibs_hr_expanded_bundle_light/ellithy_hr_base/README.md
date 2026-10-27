# Ellithy HR Base

Foundation module for migrating the legacy Laravel HR platform
(`u835352499_hrtest`, MariaDB) to Odoo 18 Community.

## What it covers

| Legacy table | Odoo model | Notes |
|---|---|---|
| `branches` | `ellithy.branch` | new — Odoo Community has no branch concept |
| `departments` | `hr.department` (`dept_type='directorate'`) | + `name_ar`, `branch_id` |
| `posts` | `hr.department` (`dept_type='section'`) | modelled as child departments |
| `company_jobs` | `hr.job` | + `name_ar`, `section_id` |
| `users` (156 cols) | `hr.employee` + `res.users` | ~70 new fields |
| `relative_*`, `relative_*_2` | `ellithy.hr.dependant` | O2M, no fixed limit |
| 14 document columns | `ellithy.hr.document` | O2M + completeness % |
| `bank_*`, `bank2_*`, `fawry_*` | `ellithy.hr.account` | O2M with method selector |
| salary columns | `hr.contract` | so a raise keeps history |

## Design decisions

**Sections are child `hr.department` records.** Odoo departments are already
hierarchical, so this buys the org chart, manager chain and department
reporting for free. The cost: `employee.department_id` points at the section,
and the directorate comes from its parent. Reversing this later is expensive.

**`branch_id` lives on the employee**, not derived from the department. The
source data has one department's staff spread across several branches.

**Salary and insurance amounts live on `hr.contract`**, not `hr.employee`.

**Three repeated column groups are normalised** into child models rather than
carried as flat repeated columns.

## Lookup behaviour

`hr.employee` sets `_rec_names_search = ['name', 'employee_code', 'name_ar',
'work_email']`, so **every** Many2one to an employee — department head,
manager, coach, warning, payslip — resolves an employee code without touching
each view.

`name_search` is overridden to rank an **exact code match first**. Plain
`ilike` would return EMP-50 and EMP-512 alongside EMP-5 in arbitrary order,
which is wrong when the code is the identifier the user actually typed.
Matching is case-insensitive, and partial codes still match as before.

`hr.department.manager_id` is relabelled **Department Head** — the legacy
column is `dept_head_id` and that is what the business calls the role. It is
a relabel of the stock field, not a second field, so Odoo's own department
hierarchy and manager chain keep working.

## Business rules reproduced

* `check_inactive_dates` — the legacy database trigger. An employee cannot be
  archived without both a resignation date and a last working day, and cannot
  hold either while active. Implemented as `_check_departure_dates`.
* Employee code sequence in the legacy `EMP-nnnn` format.
* Uniqueness on employee code and `legacy_id`.

## Caveats

* **Force logout** reaches into `odoo.http.root.session_store` because Odoo
  publishes no supported API for it. Verify on your deployment.
* **Files are not in the SQL dump.** Avatars and documents store relative
  paths; you need the Laravel `assets/` tree to migrate them.
* **Passwords cannot migrate** from Laravel bcrypt. Plan a reset flow.

## Install

```bash
odoo -u ellithy_hr_base -d <database> --stop-after-init
```

Offline checks:

```bash
python3 -m compileall -q .
python3 -c "import xml.dom.minidom as m,glob; [m.parse(f) for f in glob.glob('**/*.xml',recursive=True)]"
```
