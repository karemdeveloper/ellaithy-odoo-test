# IBS HR Shifts

This addon provides dated shifts without using Odoo working schedules for
attendance treatment.

A shift contains only its name, From Date, To Date and weekday lines. Each
line contains Day, From, To, computed No. of Hours, Is Off, Is Flexible and
the flexible Number of Hours. The technical line relationship is not shown as
an additional business field. Employees select their applicable Shift from
their employee form.

The daily job creates one `ibs.hr.attendance.day` for every active employee
whose selected shift covers the processed date. It assigns fingerprints to
the expected shift interval. For example, a Cairo shift starting at 20:00 on
14 September and ending at 08:00 on 15 September remains the attendance day
of 14 September and records 12 worked hours.

Without a fingerprint, the daily record is classified from approved Time Off,
public holidays and the shift's Is Off line; otherwise it is Absent. The job
is safe to rerun because the existing employee/date record is updated rather
than duplicated. The scheduled job processes yesterday each day. Historical
or corrected ranges can be rebuilt with:

```python
env['ibs.hr.attendance.day'].generate_days('2026-09-01', '2026-09-30')
```

The timezone defaults to `Africa/Cairo` and can be changed through the
technical parameter `ibs_hr_shift.timezone`.

