FUNCTION z_brl_stress_save.
*"----------------------------------------------------------------------
*"*"Local Interface:            (function group ZBRL_FG, Remote-Enabled Module)
*"  IMPORTING
*"     VALUE(IS_ASSESS) TYPE  ZBRL_S_ASSESS
*"  EXPORTING
*"     VALUE(EV_STATUS) TYPE  CHAR10
*"     VALUE(EV_NOTIF) TYPE  QMNUM
*"     VALUE(ES_RETURN) TYPE  BAPIRET2
*"----------------------------------------------------------------------
* Stores one StressAssessment exactly once and escalates repeated Severe episodes.
*
*  EV_STATUS = STORED     new assessment stored (EV_NOTIF filled if it opened a notification)
*              DUPLICATE  assessment ID already stored: nothing changed, acknowledge again
*              LOCKED     another call holds the house lock longer than the enqueue wait: retry
*              ERROR      notification or update failed: nothing stored, ES_RETURN has the message
*
*  Design (mirrors the mock in sil/sap_mock.py, Section IV-D of the paper):
*  1. calls for one house are serialised with lock object EZBRL_NOTIF (generic on FLOCK/HOUSE);
*  2. the assessment ID is the idempotency key: an ID already in ZBRL_STRESS is a duplicate;
*  3. a Severe episode start counts the episode starts of the same zone in
*     ( max( ts - 24 h, last notification ), ts ]; at 3 it opens one notification;
*  4. the row, the notification log and the PM notification are posted in ONE update task
*     (SAP LUW) by BAPI_TRANSACTION_COMMIT with WAIT, so they are stored together or not at all;
*  5. the PM notification carries the first tasks of the triggering assessment (TASK1-3) as
*     notification tasks, so their status (outstanding, released, completed) records in PM
*     whether the advice was carried out, by whom and when; its short text names the zone, the
*     possible cause (POSS_CAUSE) and the cause. Program Z_BRL_HOUSE_REPORT reports both daily.
*  Settings (transaction STVARV, type P): ZBRL_PM_MODE = X creates PM notifications, otherwise
*  the escalation is only logged in ZBRL_NOTIF; ZBRL_NOTIF_TYPE (e.g. M1), ZBRL_PRIORITY and
*  ZBRL_TASK_GRP (code group of the task catalog, catalog type 2; blank = tasks as text only).
*  Written for ABAP 7.0x syntax (no inline declarations). NOT YET RUN ON AN SAP SYSTEM.
*----------------------------------------------------------------------
  DATA: ls_row     TYPE zbrl_stress,
        ls_notif   TYPE zbrl_notif,
        lv_found   TYPE zbrl_stress-assess_id,
        lv_last    TYPE timestamp,
        lv_lower   TYPE timestamp,
        lv_date    TYPE d,
        lv_time    TYPE t,
        lv_count   TYPE i,
        lv_pm      TYPE tvarvc-low,
        lv_ntype   TYPE tvarvc-low,
        lv_prio    TYPE tvarvc-low,
        ls_hdr     TYPE bapi2080_nothdri,
        ls_hdre    TYPE bapi2080_nothdre,
        lt_return  TYPE STANDARD TABLE OF bapiret2,
        ls_ret     TYPE bapiret2,
        lv_failed  TYPE c LENGTH 1,
        lt_task    TYPE STANDARD TABLE OF bapi2080_nottaski,
        ls_task    TYPE bapi2080_nottaski,
        lv_tgrp    TYPE tvarvc-low,
        lv_code    TYPE c LENGTH 4,
        lv_tno     TYPE n LENGTH 4,
        lv_z       TYPE c LENGTH 3.

  CLEAR: ev_status, ev_notif, es_return.

* 1. Serialise all calls for one house; the lock passes to the update task (_SCOPE 2)
  CALL FUNCTION 'ENQUEUE_EZBRL_NOTIF'
    EXPORTING
      flock          = is_assess-flock
      house          = is_assess-house
      _scope         = '2'
      _wait          = 'X'
    EXCEPTIONS
      foreign_lock   = 1
      system_failure = 2
      OTHERS         = 3.
  IF sy-subrc <> 0.
    ev_status         = 'LOCKED'.
    es_return-type    = 'E'.
    es_return-message = 'House locked by a parallel call; retry later'.
    RETURN.
  ENDIF.

* 2. Idempotency check on the assessment ID
  SELECT SINGLE assess_id notif_no FROM zbrl_stress
    INTO (lv_found, ev_notif)
    WHERE assess_id = is_assess-assess_id.
  IF sy-subrc = 0.
    ev_status = 'DUPLICATE'.
    CALL FUNCTION 'DEQUEUE_EZBRL_NOTIF'
      EXPORTING
        flock = is_assess-flock
        house = is_assess-house.
    RETURN.
  ENDIF.

  MOVE-CORRESPONDING is_assess TO ls_row.
  GET TIME STAMP FIELD ls_row-created_at.
  ls_row-created_by = sy-uname.

* 3. Escalation rule
  IF is_assess-level_code = 2 AND is_assess-episode = 'X'.
    CONVERT TIME STAMP is_assess-window_ts TIME ZONE 'UTC'
      INTO DATE lv_date TIME lv_time.
    lv_date = lv_date - 1.                                  " 24 h earlier
    CONVERT DATE lv_date TIME lv_time
      INTO TIME STAMP lv_lower TIME ZONE 'UTC'.

    SELECT MAX( notif_ts ) FROM zbrl_notif INTO lv_last
      WHERE flock = is_assess-flock
        AND house = is_assess-house
        AND zone  = is_assess-zone.
    IF lv_last > lv_lower.
      lv_lower = lv_last.
    ENDIF.

    SELECT COUNT(*) FROM zbrl_stress INTO lv_count
      WHERE flock     = is_assess-flock
        AND house     = is_assess-house
        AND zone      = is_assess-zone
        AND episode   = 'X'
        AND window_ts > lv_lower
        AND window_ts <= is_assess-window_ts.
    lv_count = lv_count + 1.                                " the assessment being stored

    IF lv_count >= 3.
      ls_notif-flock     = is_assess-flock.
      ls_notif-house     = is_assess-house.
      ls_notif-zone      = is_assess-zone.
      ls_notif-notif_ts  = is_assess-window_ts.
      ls_notif-assess_id = is_assess-assess_id.
      GET TIME STAMP FIELD ls_notif-created_at.
      ls_notif-nmode = 'LOG'.

      SELECT SINGLE low FROM tvarvc INTO lv_pm
        WHERE name = 'ZBRL_PM_MODE' AND type = 'P' AND numb = '0000'.
      IF lv_pm = 'X'.
        SELECT SINGLE low FROM tvarvc INTO lv_ntype
          WHERE name = 'ZBRL_NOTIF_TYPE' AND type = 'P' AND numb = '0000'.
        SELECT SINGLE low FROM tvarvc INTO lv_prio
          WHERE name = 'ZBRL_PRIORITY' AND type = 'P' AND numb = '0000'.
        SELECT SINGLE low FROM tvarvc INTO lv_tgrp
          WHERE name = 'ZBRL_TASK_GRP' AND type = 'P' AND numb = '0000'.
        ls_hdr-funct_loc = is_assess-func_loc.
        ls_hdr-priority  = lv_prio.
*       Short text (40 characters), e.g. 'Severe x3/24h Z03 COOL thermal+NH3': zone, possible
*       cause and cause; the house is the functional location (longest case: 38 characters)
        CONCATENATE 'Z' is_assess-zone INTO lv_z.
        IF is_assess-poss_cause IS INITIAL.
          CONCATENATE 'Severe x3/24h' lv_z is_assess-cause
            INTO ls_hdr-short_text SEPARATED BY space.
        ELSE.
          CONCATENATE 'Severe x3/24h' lv_z is_assess-poss_cause is_assess-cause
            INTO ls_hdr-short_text SEPARATED BY space.
        ENDIF.

*       5. The first tasks become header-level notification tasks
        DO 3 TIMES.
          CASE sy-index.
            WHEN 1. lv_code = is_assess-task1.
            WHEN 2. lv_code = is_assess-task2.
            WHEN 3. lv_code = is_assess-task3.
          ENDCASE.
          CHECK lv_code IS NOT INITIAL.
          lv_tno = lv_tno + 1.
          CLEAR ls_task.
          ls_task-task_key     = lv_tno.
          ls_task-task_sort_no = lv_tno.
          IF lv_tgrp IS NOT INITIAL.
            ls_task-task_codegrp = lv_tgrp.
            ls_task-task_code    = lv_code.
            SELECT SINGLE kurztext FROM qpct INTO ls_task-task_text
              WHERE katalogart = '2' AND codegruppe = lv_tgrp
                AND code = lv_code AND sprache = sy-langu.
          ENDIF.
          IF ls_task-task_text IS INITIAL.
            CONCATENATE 'Task' lv_code 'rules' is_assess-rule_ver
              INTO ls_task-task_text SEPARATED BY space.
          ENDIF.
          APPEND ls_task TO lt_task.
        ENDDO.

        CALL FUNCTION 'BAPI_ALM_NOTIF_CREATE'
          EXPORTING
            notif_type         = lv_ntype(2)
            notifheader        = ls_hdr
          IMPORTING
            notifheader_export = ls_hdre
          TABLES
            notiftask          = lt_task
            return             = lt_return.
        LOOP AT lt_return INTO ls_ret WHERE type = 'E' OR type = 'A'.
          lv_failed = 'X'.
          EXIT.
        ENDLOOP.
        IF lv_failed IS INITIAL.
          CLEAR lt_return.
          CALL FUNCTION 'BAPI_ALM_NOTIF_SAVE'
            EXPORTING
              number      = ls_hdre-notif_no
            IMPORTING
              notifheader = ls_hdre
            TABLES
              return      = lt_return.
          LOOP AT lt_return INTO ls_ret WHERE type = 'E' OR type = 'A'.
            lv_failed = 'X'.
            EXIT.
          ENDLOOP.
        ENDIF.
        IF lv_failed = 'X'.
          CALL FUNCTION 'BAPI_TRANSACTION_ROLLBACK'.
          CALL FUNCTION 'DEQUEUE_EZBRL_NOTIF'
            EXPORTING
              flock = is_assess-flock
              house = is_assess-house.
          ev_status = 'ERROR'.
          es_return = ls_ret.
          RETURN.
        ENDIF.
        ev_notif        = ls_hdre-notif_no.
        ls_notif-qmnum  = ev_notif.
        ls_notif-nmode  = 'PM'.
      ENDIF.
      ls_row-notif_no = ev_notif.
    ENDIF.
  ENDIF.

* 4. Post the row (and the notification log) in the same update task as the BAPI
  CALL FUNCTION 'Z_BRL_STRESS_POST' IN UPDATE TASK
    EXPORTING
      is_row   = ls_row
      is_notif = ls_notif.

  CALL FUNCTION 'BAPI_TRANSACTION_COMMIT'
    EXPORTING
      wait   = 'X'
    IMPORTING
      return = ls_ret.
  IF ls_ret-type = 'E' OR ls_ret-type = 'A'.
    ev_status = 'ERROR'.
    es_return = ls_ret.
    CLEAR ev_notif.
    RETURN.
  ENDIF.

  ev_status = 'STORED'.
ENDFUNCTION.
