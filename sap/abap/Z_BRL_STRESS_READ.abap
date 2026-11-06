FUNCTION z_brl_stress_read.
*"----------------------------------------------------------------------
*"*"Local Interface:            (function group ZBRL_FG, Remote-Enabled Module)
*"  IMPORTING
*"     VALUE(IV_FLOCK_PREFIX) TYPE  CHAR20
*"  TABLES
*"      ET_STRESS STRUCTURE  ZBRL_STRESS
*"      ET_NOTIF STRUCTURE  ZBRL_NOTIF
*"      ET_TASK STRUCTURE  QMSM
*"----------------------------------------------------------------------
* Read-back for the test harness: all rows whose flock starts with IV_FLOCK_PREFIX and, in PM mode,
* the tasks (table QMSM) of the notifications those rows opened.
*----------------------------------------------------------------------
  DATA: lv_pattern TYPE c LENGTH 21,
        lt_pm      TYPE STANDARD TABLE OF zbrl_notif.

  CONCATENATE iv_flock_prefix '%' INTO lv_pattern.
  SELECT * FROM zbrl_stress INTO TABLE et_stress
    WHERE flock LIKE lv_pattern.
  SELECT * FROM zbrl_notif INTO TABLE et_notif
    WHERE flock LIKE lv_pattern.

  lt_pm = et_notif[].
  DELETE lt_pm WHERE qmnum IS INITIAL.
  IF lt_pm IS NOT INITIAL.          " FOR ALL ENTRIES with an empty table would read all of QMSM
    SELECT * FROM qmsm INTO TABLE et_task
      FOR ALL ENTRIES IN lt_pm
      WHERE qmnum = lt_pm-qmnum.
  ENDIF.
ENDFUNCTION.
