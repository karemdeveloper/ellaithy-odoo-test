# IBS HR Permission

Hourly permission requests (lateness / early leave) and field missions, split
out of `ibs_hr`'s old combined `ibs.hr.permission` model.

```
ibs.hr.time.request.mixin (abstract: employee, date, reason, state machine)
    |-- ibs.hr.permission  (type + fixed duration, date window, monthly cap)
    |-- ibs.hr.mission     (destination, GPS check-in/out or custom hours,
                            manager approval before HR, admin remark)
```

## Why a separate addon

The old model lived in `ibs_hr` and carried a `legacy_id` because it was a
migration target for the legacy Laravel `time_leaves` table (`flag` column
told Permission and Mission apart). This addon is not a migration target: it
has no `legacy_id`, no dependency on `ibs_hr` or any payroll module, and only
depends on `ellithy_hr_base` for the employee/branch/department models and
the `group_ellithy_hr_admin` / `group_ellithy_hr_personnel` groups.

Permission and Mission share only the generic submit/cancel/reset plumbing
and a `reason` field (via `ibs.hr.time.request.mixin`) — never business
rules; each model overrides `_states_awaiting_approval()` and `action_reject`
to declare its own approval gate. Permission has a fixed 30/60/90/120-minute
duration picker and a monthly cap; Mission has a required destination, is
normally timed by GPS check-in/check-out (a manually entered time span is
available via `custom_hours` for when that is impractical), needs a branch
manager's approval before HR's, and rejecting one requires an admin remark.
Splitting the abstraction this way means a change to one request type's
rules (e.g. a fifth Permission duration) never risks touching Mission's
model.

## Business rules

* **Permission type** (`ibs.hr.permission.type`) is an open configuration
  list, not a fixed selection — HR Admins add/rename/deactivate types from
  Configuration > Permission Types. Seeded with Lateness and Early Leave.
* **Duration** is one of 30 / 60 / 90 / 120 minutes — a dropdown, not a
  computed start/end difference, because the business only ever grants one of
  these four buckets.
* **Date window**: `issue_date` must be yesterday, today or tomorrow for a
  regular user. A user in `ellithy_hr_base.group_ellithy_hr_admin` may save a
  permission dated outside that window (e.g. a backdated correction).
* **Monthly cap**: the sum of an employee's non-cancelled permission minutes
  within a calendar month may not exceed a configurable cap (default 240
  minutes = 4 hours). Change it in Settings > Employees > Permissions, or via
  the `ibs_hr_permission.monthly_cap_minutes` `ir.config_parameter` — no code
  change or upgrade needed.
* **Mission timing**: by default a mission is timed by an actual
  check-in/check-out (each captures a GPS location via the browser), driving
  `duration_hours`. Ticking `custom_hours` switches to a manually entered
  From/To span instead, for when check-in/out isn't practical. Submitting
  without `custom_hours` requires both a check-in and a check-out first.
* **Mission approval**: goes through two steps — a branch manager approves
  first (`manager_approved`), then HR gives the final approval. Rejecting a
  mission (at either step) requires an admin remark; Permission has no such
  requirement.

## Tests

```bash
cd .devstack
docker compose run --rm --no-deps -T odoo \
  odoo -d hrtest -u ellithy_hr_base,ibs_hr_permission \
  --test-enable --test-tags ibs_hr_permission \
  --stop-after-init --http-port=8099
```

See `docs/UAT.md` for the business-facing acceptance walkthrough.
