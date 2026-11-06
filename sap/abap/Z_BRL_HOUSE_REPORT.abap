REPORT z_brl_house_report LINE-SIZE 120 NO STANDARD PAGE HEADING.
*----------------------------------------------------------------------
* Daily house report (paper v17, Section IV-D): for each house of the selected flocks
*   1 Data: assessments received in the period, expected windows and gaps
*   2 Conditions: windows per level, worst level per zone, peaks of THI, NH3 and CO2, and the
*     windows with the low-air-speed diagnostic
*   3 Possible causes of Moderate/Severe windows, Severe episode starts and notifications; a cause
*     in >= 2 notifications or >= 3 episode starts is flagged RECURRING (may be systematic)
*   4 Notification check: PM tasks completed / outstanding / overdue (> 24 h) and, for completed
*     tasks, whether the house was back to Normal within the next 3 windows
* Planned as a background job every morning (SM36, variant with P_DAYS = 1), with the spool list
* sent to the farm manager (spool list recipient; needs SAPconnect). The logic is in class
* ZCL_BRL_HOUSE_REPORT (ABAP Unit tests); this program only reads the tables and writes the list.
* WINDOW_TS and NOTIF_TS hold the farm's local time as YYYYMMDDhhmmss, so 'now' is taken from the
* local date and time of the user running the job (SY-DATLO, SY-TIMLO) in the same form.
* Written for ABAP 7.02 syntax. NOT YET RUN ON AN SAP SYSTEM.
*----------------------------------------------------------------------
TABLES zbrl_stress.

SELECT-OPTIONS: s_flock FOR zbrl_stress-flock OBLIGATORY,
                s_house FOR zbrl_stress-house.
PARAMETERS: p_days  TYPE i DEFAULT 1,      " reporting period: the last P_DAYS days
            p_ndays TYPE i DEFAULT 7,      " notifications of the last P_NDAYS days are checked
            p_intv  TYPE i DEFAULT 300.    " window length in s (0: spot data, no gap check)

TYPES: BEGIN OF ty_key,
         flock TYPE zbrl_stress-flock,
         house TYPE zbrl_stress-house,
       END OF ty_key.
TYPES ty_c16 TYPE c LENGTH 16.

DATA: gt_keys   TYPE STANDARD TABLE OF ty_key,
      gs_key    TYPE ty_key,
      gt_db     TYPE STANDARD TABLE OF zbrl_stress,
      gs_db     TYPE zbrl_stress,
      gt_dbn    TYPE STANDARD TABLE OF zbrl_notif,
      gs_dbn    TYPE zbrl_notif,
      gt_pm     TYPE STANDARD TABLE OF zbrl_notif,
      gt_qmsm   TYPE STANDARD TABLE OF qmsm,
      gs_qmsm   TYPE qmsm,
      gt_rows   TYPE zcl_brl_house_report=>ty_rows,
      gs_row    TYPE zcl_brl_house_report=>ty_row,
      gt_notifs TYPE zcl_brl_house_report=>ty_notifs,
      gs_notif  TYPE zcl_brl_house_report=>ty_notif,
      gt_tasks  TYPE zcl_brl_house_report=>ty_tasks,
      gs_task   TYPE zcl_brl_house_report=>ty_task,
      gs_res    TYPE zcl_brl_house_report=>ty_result,
      go_rep    TYPE REF TO zcl_brl_house_report,
      gv_now    TYPE zcl_brl_house_report=>ty_ts,
      gv_from   TYPE zcl_brl_house_report=>ty_ts,
      gv_nfrom  TYPE zcl_brl_house_report=>ty_ts,
      gv_rfrom  TYPE zcl_brl_house_report=>ty_ts,
      gv_secs   TYPE i,
      gv_rules  TYPE zbrl_stress-rule_ver.

START-OF-SELECTION.
  gv_now = zcl_brl_house_report=>to_ts( iv_date = sy-datlo iv_time = sy-timlo ).
  gv_secs = 0 - p_days * 86400.
  gv_from = zcl_brl_house_report=>add_secs( iv_ts = gv_now iv_secs = gv_secs ).
  gv_secs = 0 - p_ndays * 86400.
  gv_nfrom = zcl_brl_house_report=>add_secs( iv_ts = gv_now iv_secs = gv_secs ).
  gv_rfrom = gv_from.                         " rows read from the earlier of the two starts
  IF gv_nfrom < gv_rfrom.
    gv_rfrom = gv_nfrom.
  ENDIF.
  CREATE OBJECT go_rep.

  SELECT DISTINCT flock house FROM zbrl_stress INTO TABLE gt_keys
    WHERE flock IN s_flock AND house IN s_house
      AND window_ts > gv_rfrom AND window_ts <= gv_now.
  SORT gt_keys BY flock house.
  IF gt_keys IS INITIAL.
    WRITE / 'No assessments for this selection in the period.'.
  ENDIF.

  LOOP AT gt_keys INTO gs_key.
    CLEAR: gt_rows, gt_notifs, gt_tasks, gt_qmsm, gv_rules.
    SELECT * FROM zbrl_stress INTO TABLE gt_db
      WHERE flock = gs_key-flock AND house = gs_key-house
        AND window_ts > gv_rfrom AND window_ts <= gv_now.
    LOOP AT gt_db INTO gs_db.
      MOVE-CORRESPONDING gs_db TO gs_row.
      APPEND gs_row TO gt_rows.
      IF gs_db-window_ts > gv_from.
        gv_rules = gs_db-rule_ver.
      ENDIF.
    ENDLOOP.
    SELECT * FROM zbrl_notif INTO TABLE gt_dbn
      WHERE flock = gs_key-flock AND house = gs_key-house
        AND notif_ts > gv_nfrom AND notif_ts <= gv_now.
    LOOP AT gt_dbn INTO gs_dbn.
      MOVE-CORRESPONDING gs_dbn TO gs_notif.
      APPEND gs_notif TO gt_notifs.
    ENDLOOP.
    gt_pm = gt_dbn.
    DELETE gt_pm WHERE qmnum IS INITIAL.
    IF gt_pm IS NOT INITIAL.        " FOR ALL ENTRIES with an empty table would read all of QMSM
      SELECT * FROM qmsm INTO TABLE gt_qmsm
        FOR ALL ENTRIES IN gt_pm
        WHERE qmnum = gt_pm-qmnum
          AND kzloesch = space.       " tasks not marked for deletion
    ENDIF.
    LOOP AT gt_qmsm INTO gs_qmsm.     " completed = ERLDAT filled (system status TSCO)
      MOVE-CORRESPONDING gs_qmsm TO gs_task.
      APPEND gs_task TO gt_tasks.
    ENDLOOP.

    gs_res = go_rep->build( it_rows = gt_rows it_notifs = gt_notifs it_tasks = gt_tasks
                            iv_now = gv_now iv_from = gv_from iv_interval = p_intv ).
    PERFORM write_house USING gs_key gs_res.
  ENDLOOP.


*----------------------------------------------------------------------
FORM write_house USING is_key TYPE ty_key
                       is_res TYPE zcl_brl_house_report=>ty_result.
  DATA: ls_gap   TYPE zcl_brl_house_report=>ty_gap,
        ls_zone  TYPE zcl_brl_house_report=>ty_zone,
        ls_cause TYPE zcl_brl_house_report=>ty_cause,
        ls_item  TYPE zcl_brl_house_report=>ty_item,
        lv_pct   TYPE p LENGTH 6 DECIMALS 1,
        lv_txt   TYPE c LENGTH 40,
        lv_lvl   TYPE c LENGTH 8,
        lv_qmnum TYPE zcl_brl_house_report=>ty_item-qmnum,
        lv_ts    TYPE ty_c16,
        lv_wt    TYPE ty_c16.

  PERFORM fmt_ts USING gv_from CHANGING lv_ts.
  PERFORM fmt_ts USING gv_now CHANGING lv_wt.
  SKIP.
  WRITE: / 'HOUSE REPORT  flock', is_key-flock, ' house', is_key-house,
           ' period', lv_ts, 'to', lv_wt, ' rules', gv_rules.
  ULINE.
* 1 Data
  WRITE: / '1 Data:', is_res-received, 'assessments'.
  IF is_res-expected > 0.
    lv_pct = 100 * is_res-distinct / is_res-expected.
    WRITE: 'of', is_res-expected, 'expected (', lv_pct, '% )'.
    LOOP AT is_res-gaps INTO ls_gap.
      PERFORM fmt_ts USING ls_gap-from_ts CHANGING lv_ts.
      WRITE: /5 'gap from', lv_ts, ':', ls_gap-missing, 'window(s) missing'.
    ENDLOOP.
  ENDIF.
* 2 Conditions
  IF is_res-received > 0.
    WRITE: / '2 Conditions: windows Normal', is_res-n_normal, 'Moderate', is_res-n_moderate,
             'Severe', is_res-n_severe.
    WRITE: /5 'worst level per zone:'.
    LOOP AT is_res-zones INTO ls_zone.
      PERFORM level_text USING ls_zone-worst CHANGING lv_lvl.
      WRITE: ls_zone-zone, lv_lvl.
    ENDLOOP.
    WRITE: /5 'peaks: THI', is_res-thi_max, 'NH3', is_res-nh3_max, 'ppm  CO2', is_res-co2_max, 'ppm;',
              'low-air-speed diagnostic in', is_res-n_airdiag, 'window(s)'.
  ENDIF.
* 3 Possible causes
  WRITE: / '3 Possible causes (Moderate/Severe windows, episode starts, notifications):'.
  IF is_res-causes IS INITIAL.
    WRITE 'none'.
  ENDIF.
  LOOP AT is_res-causes INTO ls_cause.
    lv_txt = zcl_brl_house_report=>cause_text( ls_cause-code ).
    WRITE: /5 ls_cause-code, lv_txt, ls_cause-n_ms, ls_cause-n_ep, ls_cause-n_nt.
    IF ls_cause-recurring = 'X'.
      WRITE: /10 'RECURRING: may be systematic - check settings, equipment or the target'.
    ENDIF.
  ENDLOOP.
* 4 Notification check
  WRITE: / '4 Notification check (last', p_ndays, 'days):', is_res-notifications, 'notification(s); tasks',
           'completed', is_res-completed, 'outstanding', is_res-outstanding, 'overdue', is_res-overdue.
  IF is_res-completed > 0.
    WRITE: /5 'after completion: back to Normal', is_res-back_to_normal, 'improved', is_res-improved,
              'not yet', is_res-not_yet, 'too early to tell', is_res-too_early.
  ENDIF.
  LOOP AT is_res-items INTO ls_item.
    IF ls_item-qmnum <> lv_qmnum.     " (not AT NEW: it would blank the fields to the right)
      lv_qmnum = ls_item-qmnum.
      PERFORM fmt_ts USING ls_item-notif_ts CHANGING lv_ts.
      WRITE: /5 'notification', ls_item-qmnum, lv_ts, 'zone', ls_item-zone,
                'possible cause', ls_item-poss_cause.
    ENDIF.
    WRITE: /10 ls_item-manum, ls_item-mncod, ls_item-matxt, ls_item-status, ls_item-erlnam, ls_item-recovery.
  ENDLOOP.
ENDFORM.


FORM fmt_ts USING iv_ts TYPE zcl_brl_house_report=>ty_ts
            CHANGING cv_txt TYPE ty_c16.
  DATA lv_n TYPE n LENGTH 14.

  lv_n = iv_ts.
  CLEAR cv_txt.                         " YYYY-MM-DD hh:mm
  cv_txt(4)     = lv_n(4).
  cv_txt+4(1)   = '-'.
  cv_txt+5(2)   = lv_n+4(2).
  cv_txt+7(1)   = '-'.
  cv_txt+8(2)   = lv_n+6(2).
  cv_txt+11(2)  = lv_n+8(2).
  cv_txt+13(1)  = ':'.
  cv_txt+14(2)  = lv_n+10(2).
ENDFORM.


FORM level_text USING iv_level TYPE i
                CHANGING cv_txt TYPE c.
  CASE iv_level.
    WHEN 0. cv_txt = 'Normal'.
    WHEN 1. cv_txt = 'Moderate'.
    WHEN OTHERS. cv_txt = 'Severe'.
  ENDCASE.
ENDFORM.
