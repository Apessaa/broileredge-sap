CLASS zcl_brl_house_report DEFINITION PUBLIC FINAL CREATE PUBLIC.
*----------------------------------------------------------------------
* Logic of the daily house report (paper v17, Section IV-D). The class does not read the database:
* program Z_BRL_HOUSE_REPORT reads ZBRL_STRESS, ZBRL_NOTIF and QMSM and passes the rows in, so the
* logic can be tested with ABAP Unit, in SAP and off-stack (local test class, testclasses include).
* Python reference with the same limits and test cases: kit/report/house_report.py, test_report.py.
* Timestamps are YYYYMMDDhhmmss (as ZBRL_STRESS-WINDOW_TS); 0 in THI, NH3 or CO2 means "not measured". Written for ABAP 7.02 syntax (no inline declarations, no constructor expressions).
* NOT YET RUN ON AN SAP SYSTEM.
*----------------------------------------------------------------------
  PUBLIC SECTION.
    CONSTANTS gc_overdue_h TYPE i VALUE 24.
    CONSTANTS gc_recover_win TYPE i VALUE 3.
    CONSTANTS gc_recur_notif TYPE i VALUE 2.
    CONSTANTS gc_recur_epis TYPE i VALUE 3.

    TYPES ty_ts TYPE p LENGTH 8 DECIMALS 0.
    TYPES: BEGIN OF ty_row,
             assess_id  TYPE c LENGTH 36,
             window_ts  TYPE ty_ts,
             zone       TYPE n LENGTH 2,
             level_code TYPE i,
             episode    TYPE c LENGTH 1,
             poss_cause TYPE c LENGTH 4,
             rule_ver   TYPE c LENGTH 12,
             thi        TYPE p LENGTH 3 DECIMALS 2,
             nh3        TYPE p LENGTH 3 DECIMALS 1,
             co2        TYPE i,
             airdiag    TYPE c LENGTH 1,
           END OF ty_row,
           ty_rows TYPE STANDARD TABLE OF ty_row WITH DEFAULT KEY.
    TYPES: BEGIN OF ty_notif,
             qmnum     TYPE c LENGTH 12,
             notif_ts  TYPE ty_ts,
             zone      TYPE n LENGTH 2,
             assess_id TYPE c LENGTH 36,
           END OF ty_notif,
           ty_notifs TYPE STANDARD TABLE OF ty_notif WITH DEFAULT KEY.
    TYPES: BEGIN OF ty_task,
             qmnum   TYPE c LENGTH 12,
             manum   TYPE n LENGTH 4,
             mncod   TYPE c LENGTH 4,
             matxt   TYPE c LENGTH 40,
             erldat  TYPE d,
             erlzeit TYPE t,
             erlnam  TYPE c LENGTH 12,
           END OF ty_task,
           ty_tasks TYPE STANDARD TABLE OF ty_task WITH DEFAULT KEY.
    TYPES: BEGIN OF ty_gap,
             from_ts TYPE ty_ts,
             missing TYPE i,
           END OF ty_gap,
           ty_gaps TYPE STANDARD TABLE OF ty_gap WITH DEFAULT KEY.
    TYPES: BEGIN OF ty_zone,
             zone  TYPE n LENGTH 2,
             worst TYPE i,
           END OF ty_zone,
           ty_zones TYPE SORTED TABLE OF ty_zone WITH UNIQUE KEY zone.
    TYPES: BEGIN OF ty_cause,
             code      TYPE c LENGTH 4,
             n_ms      TYPE i,
             n_ep      TYPE i,
             n_nt      TYPE i,
             recurring TYPE c LENGTH 1,
           END OF ty_cause,
           ty_causes TYPE SORTED TABLE OF ty_cause WITH UNIQUE KEY code.
    TYPES: BEGIN OF ty_item,
             qmnum      TYPE c LENGTH 12,
             notif_ts   TYPE ty_ts,
             zone       TYPE n LENGTH 2,
             poss_cause TYPE c LENGTH 4,
             manum      TYPE n LENGTH 4,
             mncod      TYPE c LENGTH 4,
             matxt      TYPE c LENGTH 40,
             status     TYPE c LENGTH 12,
             erlnam     TYPE c LENGTH 12,
             recovery   TYPE c LENGTH 20,
           END OF ty_item,
           ty_items TYPE STANDARD TABLE OF ty_item WITH DEFAULT KEY.
    TYPES: BEGIN OF ty_result,
             received       TYPE i,
             distinct       TYPE i,
             expected       TYPE i,
             gaps           TYPE ty_gaps,
             n_normal       TYPE i,
             n_moderate     TYPE i,
             n_severe       TYPE i,
             zones          TYPE ty_zones,
             thi_max        TYPE p LENGTH 3 DECIMALS 2,
             nh3_max        TYPE p LENGTH 3 DECIMALS 1,
             co2_max        TYPE i,
             n_airdiag      TYPE i,
             causes         TYPE ty_causes,
             notifications  TYPE i,
             completed      TYPE i,
             outstanding    TYPE i,
             overdue        TYPE i,
             back_to_normal TYPE i,
             improved       TYPE i,
             not_yet        TYPE i,
             too_early      TYPE i,
             items          TYPE ty_items,
           END OF ty_result.

    "! Builds the report. it_rows may start before iv_from: those rows are used only for the recovery
    "! check; data, conditions and possible causes cover the rows after iv_from (all rows if initial).
    METHODS build
      IMPORTING it_rows          TYPE ty_rows
                it_notifs        TYPE ty_notifs
                it_tasks         TYPE ty_tasks
                iv_now           TYPE ty_ts
                iv_from          TYPE ty_ts OPTIONAL
                iv_interval      TYPE i DEFAULT 0
      RETURNING VALUE(rs_result) TYPE ty_result.
    CLASS-METHODS secs_between
      IMPORTING iv_from        TYPE ty_ts
                iv_to          TYPE ty_ts
      RETURNING VALUE(rv_secs) TYPE i.
    CLASS-METHODS add_secs
      IMPORTING iv_ts        TYPE ty_ts
                iv_secs      TYPE i
      RETURNING VALUE(rv_ts) TYPE ty_ts.
    CLASS-METHODS to_ts
      IMPORTING iv_date      TYPE d
                iv_time      TYPE t
      RETURNING VALUE(rv_ts) TYPE ty_ts.
    "! Text of a possible cause (as POSSIBLE_CAUSES in kit/edge/tasks.py, rule version 2026-10-v2)
    CLASS-METHODS cause_text
      IMPORTING iv_code        TYPE csequence
      RETURNING VALUE(rv_text) TYPE string.
  PRIVATE SECTION.
    METHODS count_cause
      IMPORTING iv_code   TYPE csequence
                iv_kind   TYPE c
      CHANGING  ct_causes TYPE ty_causes.
ENDCLASS.



CLASS zcl_brl_house_report IMPLEMENTATION.

  METHOD build.
    DATA: lt_rows   TYPE ty_rows,
          lt_period TYPE ty_rows,
          ls_row    TYPE ty_row,
          ls_prev   TYPE ty_row,
          ls_trig   TYPE ty_row,
          lt_notifs TYPE ty_notifs,
          ls_notif  TYPE ty_notif,
          lt_tasks  TYPE ty_tasks,
          ls_task   TYPE ty_task,
          ls_gap    TYPE ty_gap,
          ls_zone   TYPE ty_zone,
          ls_item   TYPE ty_item,
          lv_first  TYPE ty_ts,
          lv_last   TYPE ty_ts,
          lv_done   TYPE ty_ts,
          lv_secs   TYPE i,
          lv_miss   TYPE i,
          lv_seen   TYPE i,
          lv_normal TYPE c LENGTH 1,
          lv_min    TYPE i,
          lv_limit  TYPE i.
    FIELD-SYMBOLS: <ls_zone>  TYPE ty_zone,
                   <ls_cause> TYPE ty_cause.

    lv_limit = gc_overdue_h * 3600.
    lt_rows = it_rows.
    SORT lt_rows BY window_ts zone.
    LOOP AT lt_rows INTO ls_row.
      IF iv_from IS INITIAL OR ls_row-window_ts > iv_from.
        APPEND ls_row TO lt_period.
      ENDIF.
    ENDLOOP.

*   1 Data completeness
    rs_result-received = lines( lt_period ).
    LOOP AT lt_period INTO ls_row.
      IF sy-tabix = 1.
        lv_first = ls_row-window_ts.
      ELSEIF ls_row-window_ts = ls_prev-window_ts.
        ls_prev = ls_row.
        CONTINUE.
      ELSEIF iv_interval > 0.
        lv_secs = secs_between( iv_from = ls_prev-window_ts iv_to = ls_row-window_ts ).
        lv_miss = lv_secs DIV iv_interval - 1.
        IF lv_miss > 0.
          CLEAR ls_gap.
          ls_gap-from_ts = add_secs( iv_ts = ls_prev-window_ts iv_secs = iv_interval ).
          ls_gap-missing = lv_miss.
          APPEND ls_gap TO rs_result-gaps.
        ENDIF.
      ENDIF.
      rs_result-distinct = rs_result-distinct + 1.
      lv_last = ls_row-window_ts.
      ls_prev = ls_row.
    ENDLOOP.
    IF iv_interval > 0 AND rs_result-distinct > 0.
      lv_secs = secs_between( iv_from = lv_first iv_to = lv_last ).
      rs_result-expected = lv_secs DIV iv_interval + 1.
    ENDIF.

*   2 Conditions: windows per level, worst level per zone, peaks of the stored inputs, windows with
*     the low-air-speed diagnostic
    LOOP AT lt_period INTO ls_row.
      CASE ls_row-level_code.
        WHEN 0. rs_result-n_normal = rs_result-n_normal + 1.
        WHEN 1. rs_result-n_moderate = rs_result-n_moderate + 1.
        WHEN OTHERS. rs_result-n_severe = rs_result-n_severe + 1.
      ENDCASE.
      READ TABLE rs_result-zones ASSIGNING <ls_zone> WITH TABLE KEY zone = ls_row-zone.
      IF sy-subrc <> 0.
        CLEAR ls_zone.
        ls_zone-zone  = ls_row-zone.
        ls_zone-worst = ls_row-level_code.
        INSERT ls_zone INTO TABLE rs_result-zones.
      ELSEIF ls_row-level_code > <ls_zone>-worst.
        <ls_zone>-worst = ls_row-level_code.
      ENDIF.
      IF ls_row-thi > rs_result-thi_max.
        rs_result-thi_max = ls_row-thi.
      ENDIF.
      IF ls_row-nh3 > rs_result-nh3_max.
        rs_result-nh3_max = ls_row-nh3.
      ENDIF.
      IF ls_row-co2 > rs_result-co2_max.
        rs_result-co2_max = ls_row-co2.
      ENDIF.
      IF ls_row-airdiag = 'X'.
        rs_result-n_airdiag = rs_result-n_airdiag + 1.
      ENDIF.
*     3 Possible causes of Moderate/Severe windows and of Severe episode starts
      IF ls_row-poss_cause IS NOT INITIAL.
        IF ls_row-level_code >= 1.
          count_cause( EXPORTING iv_code = ls_row-poss_cause iv_kind = 'M' CHANGING ct_causes = rs_result-causes ).
        ENDIF.
        IF ls_row-episode = 'X'.
          count_cause( EXPORTING iv_code = ls_row-poss_cause iv_kind = 'E' CHANGING ct_causes = rs_result-causes ).
        ENDIF.
      ENDIF.
    ENDLOOP.

*   4 Notification check: tasks completed / outstanding / overdue, recovery after completion
    lt_notifs = it_notifs.
    SORT lt_notifs BY notif_ts zone.
    lt_tasks = it_tasks.
    SORT lt_tasks BY qmnum manum.
    rs_result-notifications = lines( lt_notifs ).
    LOOP AT lt_notifs INTO ls_notif.
      CLEAR ls_trig.
      READ TABLE lt_rows INTO ls_trig WITH KEY assess_id = ls_notif-assess_id.
      IF ls_trig-poss_cause IS NOT INITIAL.
        count_cause( EXPORTING iv_code = ls_trig-poss_cause iv_kind = 'N' CHANGING ct_causes = rs_result-causes ).
      ENDIF.
      IF ls_notif-qmnum IS INITIAL.       " LOG mode: no PM notification, tasks not tracked
        CONTINUE.
      ENDIF.
      LOOP AT lt_tasks INTO ls_task WHERE qmnum = ls_notif-qmnum.
        CLEAR ls_item.
        ls_item-qmnum      = ls_notif-qmnum.
        ls_item-notif_ts   = ls_notif-notif_ts.
        ls_item-zone       = ls_notif-zone.
        ls_item-poss_cause = ls_trig-poss_cause.
        ls_item-manum      = ls_task-manum.
        ls_item-mncod      = ls_task-mncod.
        ls_item-matxt      = ls_task-matxt.
        IF ls_task-erldat IS NOT INITIAL.
          ls_item-status = 'COMPLETED'.
          ls_item-erlnam = ls_task-erlnam.
          rs_result-completed = rs_result-completed + 1.
          lv_done = to_ts( iv_date = ls_task-erldat iv_time = ls_task-erlzeit ).
          lv_seen = 0.
          lv_min = 2.
          CLEAR lv_normal.
          LOOP AT lt_rows INTO ls_row WHERE window_ts > lv_done.
            lv_seen = lv_seen + 1.
            IF ls_row-level_code = 0.
              lv_normal = 'X'.
            ENDIF.
            IF ls_row-level_code < lv_min.
              lv_min = ls_row-level_code.
            ENDIF.
            IF lv_seen >= gc_recover_win.
              EXIT.
            ENDIF.
          ENDLOOP.
          IF lv_normal = 'X'.
            ls_item-recovery = 'BACK_TO_NORMAL'.
            rs_result-back_to_normal = rs_result-back_to_normal + 1.
          ELSEIF lv_seen < gc_recover_win.
            ls_item-recovery = 'TOO_EARLY'.
            rs_result-too_early = rs_result-too_early + 1.
          ELSEIF lv_min < 2.
            ls_item-recovery = 'IMPROVED'.
            rs_result-improved = rs_result-improved + 1.
          ELSE.
            ls_item-recovery = 'NOT_YET'.
            rs_result-not_yet = rs_result-not_yet + 1.
          ENDIF.
        ELSE.
          lv_secs = secs_between( iv_from = ls_notif-notif_ts iv_to = iv_now ).
          IF lv_secs > lv_limit.
            ls_item-status = 'OVERDUE'.
            rs_result-overdue = rs_result-overdue + 1.
          ELSE.
            ls_item-status = 'OUTSTANDING'.
            rs_result-outstanding = rs_result-outstanding + 1.
          ENDIF.
        ENDIF.
        APPEND ls_item TO rs_result-items.
      ENDLOOP.
    ENDLOOP.

*   Recurring possible cause: may be systematic (settings, equipment or the target)
    LOOP AT rs_result-causes ASSIGNING <ls_cause>.
      IF <ls_cause>-n_nt >= gc_recur_notif OR <ls_cause>-n_ep >= gc_recur_epis.
        <ls_cause>-recurring = 'X'.
      ENDIF.
    ENDLOOP.
  ENDMETHOD.


  METHOD count_cause.
    DATA ls_cause TYPE ty_cause.
    FIELD-SYMBOLS <ls_cause> TYPE ty_cause.

    READ TABLE ct_causes ASSIGNING <ls_cause> WITH TABLE KEY code = iv_code.
    IF sy-subrc <> 0.
      CLEAR ls_cause.
      ls_cause-code = iv_code.
      INSERT ls_cause INTO TABLE ct_causes.
      READ TABLE ct_causes ASSIGNING <ls_cause> WITH TABLE KEY code = iv_code.
    ENDIF.
    CASE iv_kind.
      WHEN 'M'. <ls_cause>-n_ms = <ls_cause>-n_ms + 1.
      WHEN 'E'. <ls_cause>-n_ep = <ls_cause>-n_ep + 1.
      WHEN 'N'. <ls_cause>-n_nt = <ls_cause>-n_nt + 1.
    ENDCASE.
  ENDMETHOD.


  METHOD secs_between.
    DATA: lv_n1   TYPE n LENGTH 14,
          lv_n2   TYPE n LENGTH 14,
          lv_d1   TYPE d,
          lv_d2   TYPE d,
          lv_t1   TYPE t,
          lv_t2   TYPE t,
          lv_s1   TYPE i,
          lv_s2   TYPE i,
          lv_days TYPE i.

    lv_n1 = iv_from.
    lv_n2 = iv_to.
    lv_d1 = lv_n1(8).
    lv_d2 = lv_n2(8).
    lv_t1 = lv_n1+8(6).
    lv_t2 = lv_n2+8(6).
    lv_days = lv_d2 - lv_d1.
    lv_s1 = lv_t1.
    lv_s2 = lv_t2.
    rv_secs = lv_days * 86400 + lv_s2 - lv_s1.
  ENDMETHOD.


  METHOD add_secs.
    DATA: lv_n    TYPE n LENGTH 14,
          lv_d    TYPE d,
          lv_t    TYPE t,
          lv_s    TYPE i,
          lv_days TYPE i.

    lv_n = iv_ts.
    lv_d = lv_n(8).
    lv_t = lv_n+8(6).
    lv_s = lv_t.
    lv_s = lv_s + iv_secs.
    lv_days = lv_s DIV 86400.
    lv_s = lv_s MOD 86400.
    lv_d = lv_d + lv_days.
    lv_t = lv_s.
    rv_ts = to_ts( iv_date = lv_d iv_time = lv_t ).
  ENDMETHOD.


  METHOD to_ts.
    DATA lv_n TYPE n LENGTH 14.

    lv_n(8)   = iv_date.
    lv_n+8(6) = iv_time.
    rv_ts = lv_n.
  ENDMETHOD.


  METHOD cause_text.
    CASE iv_code.
      WHEN 'AIRF'. rv_text = 'Low airflow (fans, belts or inlet)'.
      WHEN 'HUMH'. rv_text = 'Humid heat: pads would add moisture'.
      WHEN 'COOL'. rv_text = 'Cooling stage below the heat load'.
      WHEN 'HTRC'. rv_text = 'Heaters low or cold air reaching chicks'.
      WHEN 'SETP'. rv_text = 'Set point or heat above the target'.
      WHEN 'WETL'. rv_text = 'Wet litter, too little min. ventilation'.
      WHEN 'LITQ'. rv_text = 'Litter condition (caked or built-up)'.
      WHEN 'VENT'. rv_text = 'Ventilation below need for fresh air'.
      WHEN OTHERS. rv_text = '?'.
    ENDCASE.
  ENDMETHOD.

ENDCLASS.
