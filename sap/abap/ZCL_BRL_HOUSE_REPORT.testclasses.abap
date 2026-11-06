*"* ABAP Unit tests of ZCL_BRL_HOUSE_REPORT (class-relevant local types: test classes include).
*"* The SYNTHETIC test sequences mirror kit/report/test_report.py, sections 1-4; they are test
*"* inputs, not data. Run in SE24/SE80 (Ctrl+Shift+F10) or off-stack (kit/sap/offstack).
*"* cl_abap_unit_assert needs 7.02 or later (on 7.00/7.01 use cl_aunit_assert).
CLASS ltcl_report DEFINITION FINAL FOR TESTING RISK LEVEL HARMLESS DURATION SHORT.
  PRIVATE SECTION.
    DATA: mo_cut   TYPE REF TO zcl_brl_house_report,
          mt_rows  TYPE zcl_brl_house_report=>ty_rows,
          mt_notif TYPE zcl_brl_house_report=>ty_notifs,
          mt_tasks TYPE zcl_brl_house_report=>ty_tasks,
          mv_t0    TYPE zcl_brl_house_report=>ty_ts.
    METHODS setup.
    METHODS ts
      IMPORTING iv_secs      TYPE i
      RETURNING VALUE(rv_ts) TYPE zcl_brl_house_report=>ty_ts.
    METHODS add_row
      IMPORTING iv_i     TYPE i
                iv_level TYPE i
                iv_zone  TYPE csequence DEFAULT '01'
                iv_pc    TYPE csequence DEFAULT ''
                iv_ep    TYPE csequence DEFAULT ''
                iv_step  TYPE i DEFAULT 300
                iv_thi   TYPE csequence DEFAULT '0'
                iv_nh3   TYPE csequence DEFAULT '0'
                iv_co2   TYPE i DEFAULT 0
                iv_diag  TYPE csequence DEFAULT ''.
    METHODS add_notif
      IMPORTING iv_qmnum TYPE csequence
                iv_aid   TYPE csequence
                iv_zone  TYPE csequence.
    METHODS add_task
      IMPORTING iv_qmnum TYPE csequence
                iv_manum TYPE csequence
                iv_code  TYPE csequence
                iv_done  TYPE csequence DEFAULT ''.
    METHODS completeness_and_gap FOR TESTING.
    METHODS conditions_and_causes FOR TESTING.
    METHODS recurring_causes FOR TESTING.
    METHODS task_status_and_recovery FOR TESTING.
    METHODS recovery_not_yet_improved FOR TESTING.
    METHODS time_helpers FOR TESTING.
ENDCLASS.


CLASS ltcl_report IMPLEMENTATION.

  METHOD setup.
    CREATE OBJECT mo_cut.
    CLEAR: mt_rows, mt_notif, mt_tasks.
    mv_t0 = '20270104060000'.
  ENDMETHOD.


  METHOD ts.
    rv_ts = zcl_brl_house_report=>add_secs( iv_ts = mv_t0 iv_secs = iv_secs ).
  ENDMETHOD.


  METHOD add_row.
    DATA: ls_row  TYPE zcl_brl_house_report=>ty_row,
          lv_secs TYPE i,
          lv_id   TYPE c LENGTH 10.

    lv_id = iv_i.
    CONDENSE lv_id.
    CONCATENATE 'A' lv_id INTO ls_row-assess_id.
    lv_secs = iv_i * iv_step.
    ls_row-window_ts  = ts( lv_secs ).
    ls_row-zone       = iv_zone.
    ls_row-level_code = iv_level.
    ls_row-poss_cause = iv_pc.
    ls_row-episode    = iv_ep.
    ls_row-rule_ver   = '2026-10-v2'.
    ls_row-thi        = iv_thi.
    ls_row-nh3        = iv_nh3.
    ls_row-co2        = iv_co2.
    ls_row-airdiag    = iv_diag.
    APPEND ls_row TO mt_rows.
  ENDMETHOD.


  METHOD add_notif.
    DATA: ls_notif TYPE zcl_brl_house_report=>ty_notif,
          ls_row   TYPE zcl_brl_house_report=>ty_row.

    READ TABLE mt_rows INTO ls_row WITH KEY assess_id = iv_aid.
    ls_notif-qmnum     = iv_qmnum.
    ls_notif-notif_ts  = ls_row-window_ts.
    ls_notif-zone      = iv_zone.
    ls_notif-assess_id = iv_aid.
    APPEND ls_notif TO mt_notif.
  ENDMETHOD.


  METHOD add_task.
    DATA: ls_task TYPE zcl_brl_house_report=>ty_task,
          lv_n    TYPE n LENGTH 14.

    ls_task-qmnum = iv_qmnum.
    ls_task-manum = iv_manum.
    ls_task-mncod = iv_code.
    IF iv_done IS NOT INITIAL.          " completed in PM: date, time and user
      lv_n = iv_done.
      ls_task-erldat  = lv_n(8).
      ls_task-erlzeit = lv_n+8(6).
      ls_task-erlnam  = 'TESTUSER'.
    ENDIF.
    APPEND ls_task TO mt_tasks.
  ENDMETHOD.


  METHOD completeness_and_gap.
*   12 windows of 5 min, windows 4-6 lost
    DATA: ls_res  TYPE zcl_brl_house_report=>ty_result,
          ls_gap  TYPE zcl_brl_house_report=>ty_gap,
          lv_i    TYPE i,
          lv_n    TYPE i,
          lv_exp  TYPE zcl_brl_house_report=>ty_ts,
          lv_now  TYPE zcl_brl_house_report=>ty_ts.

    DO 12 TIMES.
      lv_i = sy-index - 1.
      IF lv_i < 4 OR lv_i > 6.
        add_row( iv_i = lv_i iv_level = 0 ).
      ENDIF.
    ENDDO.
    lv_now = ts( 3600 ).
    ls_res = mo_cut->build( it_rows = mt_rows it_notifs = mt_notif it_tasks = mt_tasks
                            iv_now = lv_now iv_interval = 300 ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-received exp = 9 ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-expected exp = 12 ).
    lv_n = lines( ls_res-gaps ).
    cl_abap_unit_assert=>assert_equals( act = lv_n exp = 1 ).
    READ TABLE ls_res-gaps INTO ls_gap INDEX 1.
    lv_exp = ts( 1200 ).
    cl_abap_unit_assert=>assert_equals( act = ls_gap-from_ts exp = lv_exp ).
    cl_abap_unit_assert=>assert_equals( act = ls_gap-missing exp = 3 ).
*   without an interval (spot surveys) no gap check is made
    ls_res = mo_cut->build( it_rows = mt_rows it_notifs = mt_notif it_tasks = mt_tasks iv_now = lv_now ).
    lv_n = lines( ls_res-gaps ).
    cl_abap_unit_assert=>assert_equals( act = lv_n exp = 0 ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-expected exp = 0 ).
  ENDMETHOD.


  METHOD conditions_and_causes.
    DATA: ls_res   TYPE zcl_brl_house_report=>ty_result,
          ls_zone  TYPE zcl_brl_house_report=>ty_zone,
          ls_cause TYPE zcl_brl_house_report=>ty_cause,
          lv_now   TYPE zcl_brl_house_report=>ty_ts,
          lv_thi   TYPE zcl_brl_house_report=>ty_row-thi,
          lv_nh3   TYPE zcl_brl_house_report=>ty_row-nh3.

    add_row( iv_i = 0 iv_level = 0 iv_zone = '01' iv_thi = '25.0' iv_nh3 = '8' iv_co2 = 1500 ).
    add_row( iv_i = 1 iv_level = 1 iv_zone = '02' iv_pc = 'COOL' iv_thi = '27.0' iv_nh3 = '9' iv_co2 = 1600 ).
    add_row( iv_i = 2 iv_level = 2 iv_zone = '02' iv_pc = 'COOL' iv_ep = 'X' iv_thi = '29.5' iv_nh3 = '10'
             iv_co2 = 1700 iv_diag = 'X' ).
    add_row( iv_i = 3 iv_level = 2 iv_zone = '02' iv_pc = 'COOL' iv_thi = '29.8' iv_diag = 'X' ).
    add_row( iv_i = 4 iv_level = 1 iv_zone = '03' iv_pc = 'WETL' iv_nh3 = '21' ).
    add_row( iv_i = 5 iv_level = 0 iv_zone = '01' iv_thi = '25.5' ).
    lv_now = ts( 3600 ).
    ls_res = mo_cut->build( it_rows = mt_rows it_notifs = mt_notif it_tasks = mt_tasks iv_now = lv_now ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-n_normal exp = 2 ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-n_moderate exp = 2 ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-n_severe exp = 2 ).
    READ TABLE ls_res-zones INTO ls_zone WITH TABLE KEY zone = '02'.
    cl_abap_unit_assert=>assert_equals( act = ls_zone-worst exp = 2 ).
    READ TABLE ls_res-zones INTO ls_zone WITH TABLE KEY zone = '03'.
    cl_abap_unit_assert=>assert_equals( act = ls_zone-worst exp = 1 ).
    READ TABLE ls_res-zones INTO ls_zone WITH TABLE KEY zone = '01'.
    cl_abap_unit_assert=>assert_equals( act = ls_zone-worst exp = 0 ).
    lv_thi = '29.8'.
    lv_nh3 = '21'.
    cl_abap_unit_assert=>assert_equals( act = ls_res-thi_max exp = lv_thi ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-nh3_max exp = lv_nh3 ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-co2_max exp = 1700 ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-n_airdiag exp = 2 ).
    READ TABLE ls_res-causes INTO ls_cause WITH TABLE KEY code = 'COOL'.
    cl_abap_unit_assert=>assert_equals( act = ls_cause-n_ms exp = 3 ).
    cl_abap_unit_assert=>assert_equals( act = ls_cause-n_ep exp = 1 ).
    READ TABLE ls_res-causes INTO ls_cause WITH TABLE KEY code = 'WETL'.
    cl_abap_unit_assert=>assert_equals( act = ls_cause-n_ms exp = 1 ).
    cl_abap_unit_assert=>assert_equals( act = ls_cause-n_ep exp = 0 ).
  ENDMETHOD.


  METHOD recurring_causes.
*   >= 2 notifications or >= 3 episode starts with the same possible cause
    DATA: ls_res   TYPE zcl_brl_house_report=>ty_result,
          ls_cause TYPE zcl_brl_house_report=>ty_cause,
          lv_now   TYPE zcl_brl_house_report=>ty_ts,
          lv_i     TYPE i.

    DO 3 TIMES.
      lv_i = sy-index - 1.
      add_row( iv_i = lv_i iv_level = 2 iv_zone = '01' iv_pc = 'SETP' iv_ep = 'X' iv_step = 3600 ).
    ENDDO.
    DO 3 TIMES.
      lv_i = sy-index + 2.
      add_row( iv_i = lv_i iv_level = 2 iv_zone = '02' iv_pc = 'COOL' iv_ep = 'X' iv_step = 3600 ).
    ENDDO.
    DO 2 TIMES.
      lv_i = sy-index + 5.
      add_row( iv_i = lv_i iv_level = 2 iv_zone = '03' iv_pc = 'WETL' iv_ep = 'X' iv_step = 3600 ).
    ENDDO.
    add_notif( iv_qmnum = '000010000001' iv_aid = 'A0' iv_zone = '01' ).
    add_notif( iv_qmnum = '000010000002' iv_aid = 'A1' iv_zone = '01' ).
    lv_now = ts( 36000 ).
    ls_res = mo_cut->build( it_rows = mt_rows it_notifs = mt_notif it_tasks = mt_tasks iv_now = lv_now ).
    READ TABLE ls_res-causes INTO ls_cause WITH TABLE KEY code = 'SETP'.
    cl_abap_unit_assert=>assert_equals( act = ls_cause-n_nt exp = 2 ).
    cl_abap_unit_assert=>assert_equals( act = ls_cause-recurring exp = 'X' ).
    READ TABLE ls_res-causes INTO ls_cause WITH TABLE KEY code = 'COOL'.
    cl_abap_unit_assert=>assert_equals( act = ls_cause-recurring exp = 'X' ).
    READ TABLE ls_res-causes INTO ls_cause WITH TABLE KEY code = 'WETL'.
    cl_abap_unit_assert=>assert_equals( act = ls_cause-n_ep exp = 2 ).
    cl_abap_unit_assert=>assert_equals( act = ls_cause-recurring exp = ' ' ).
  ENDMETHOD.


  METHOD task_status_and_recovery.
    DATA: ls_res  TYPE zcl_brl_house_report=>ty_result,
          ls_item TYPE zcl_brl_house_report=>ty_item,
          lv_now  TYPE zcl_brl_house_report=>ty_ts.

    add_row( iv_i = 0 iv_level = 2 iv_zone = '02' iv_pc = 'COOL' iv_ep = 'X' ).
    add_row( iv_i = 1 iv_level = 2 iv_zone = '02' iv_pc = 'COOL' ).
    add_row( iv_i = 2 iv_level = 2 iv_zone = '02' iv_pc = 'COOL' ).
    add_row( iv_i = 3 iv_level = 0 iv_zone = '01' ).
    add_row( iv_i = 4 iv_level = 0 iv_zone = '01' ).
    add_notif( iv_qmnum = '000010000001' iv_aid = 'A0' iv_zone = '02' ).
    add_task( iv_qmnum = '000010000001' iv_manum = '0001' iv_code = 'FANS' iv_done = '20270104060100' ).
    add_task( iv_qmnum = '000010000001' iv_manum = '0002' iv_code = 'PADS' iv_done = '20270104062100' ).
    add_task( iv_qmnum = '000010000001' iv_manum = '0003' iv_code = 'PADC' ).
    lv_now = ts( 7200 ).
    ls_res = mo_cut->build( it_rows = mt_rows it_notifs = mt_notif it_tasks = mt_tasks iv_now = lv_now ).
    READ TABLE ls_res-items INTO ls_item INDEX 1.
    cl_abap_unit_assert=>assert_equals( act = ls_item-status exp = 'COMPLETED' ).
    cl_abap_unit_assert=>assert_equals( act = ls_item-recovery exp = 'BACK_TO_NORMAL' ).
    cl_abap_unit_assert=>assert_equals( act = ls_item-erlnam exp = 'TESTUSER' ).
    cl_abap_unit_assert=>assert_equals( act = ls_item-poss_cause exp = 'COOL' ).
    READ TABLE ls_res-items INTO ls_item INDEX 2.
    cl_abap_unit_assert=>assert_equals( act = ls_item-recovery exp = 'TOO_EARLY' ).
    READ TABLE ls_res-items INTO ls_item INDEX 3.
    cl_abap_unit_assert=>assert_equals( act = ls_item-status exp = 'OUTSTANDING' ).
*   25 h after the notification the open task is overdue
    lv_now = ts( 90000 ).
    ls_res = mo_cut->build( it_rows = mt_rows it_notifs = mt_notif it_tasks = mt_tasks iv_now = lv_now ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-completed exp = 2 ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-overdue exp = 1 ).
    cl_abap_unit_assert=>assert_equals( act = ls_res-outstanding exp = 0 ).
  ENDMETHOD.


  METHOD recovery_not_yet_improved.
    DATA: ls_res  TYPE zcl_brl_house_report=>ty_result,
          ls_item TYPE zcl_brl_house_report=>ty_item,
          lv_now  TYPE zcl_brl_house_report=>ty_ts.

    add_row( iv_i = 0 iv_level = 2 iv_zone = '02' iv_pc = 'COOL' iv_ep = 'X' ).
    add_row( iv_i = 1 iv_level = 2 iv_zone = '02' ).
    add_row( iv_i = 2 iv_level = 2 iv_zone = '02' ).
    add_row( iv_i = 3 iv_level = 2 iv_zone = '02' ).
    add_row( iv_i = 4 iv_level = 1 iv_zone = '02' ).
    add_notif( iv_qmnum = '000010000001' iv_aid = 'A0' iv_zone = '02' ).
    add_task( iv_qmnum = '000010000001' iv_manum = '0001' iv_code = 'FANS' iv_done = '20270104060100' ).
    add_task( iv_qmnum = '000010000001' iv_manum = '0002' iv_code = 'PADS' iv_done = '20270104060600' ).
    lv_now = ts( 7200 ).
    ls_res = mo_cut->build( it_rows = mt_rows it_notifs = mt_notif it_tasks = mt_tasks iv_now = lv_now ).
    READ TABLE ls_res-items INTO ls_item INDEX 1.
    cl_abap_unit_assert=>assert_equals( act = ls_item-recovery exp = 'NOT_YET' ).
    READ TABLE ls_res-items INTO ls_item INDEX 2.
    cl_abap_unit_assert=>assert_equals( act = ls_item-recovery exp = 'IMPROVED' ).
  ENDMETHOD.


  METHOD time_helpers.
    DATA: lv_a    TYPE zcl_brl_house_report=>ty_ts,
          lv_b    TYPE zcl_brl_house_report=>ty_ts,
          lv_secs TYPE i,
          lv_ts   TYPE zcl_brl_house_report=>ty_ts,
          lv_d    TYPE d,
          lv_t    TYPE t,
          lv_txt  TYPE string.

    lv_a = '20270104235900'.
    lv_b = '20270105000100'.
    lv_secs = zcl_brl_house_report=>secs_between( iv_from = lv_a iv_to = lv_b ).
    cl_abap_unit_assert=>assert_equals( act = lv_secs exp = 120 ).
    lv_ts = zcl_brl_house_report=>add_secs( iv_ts = lv_a iv_secs = 120 ).
    cl_abap_unit_assert=>assert_equals( act = lv_ts exp = lv_b ).
    lv_d = '20270104'.
    lv_t = '060000'.
    lv_ts = zcl_brl_house_report=>to_ts( iv_date = lv_d iv_time = lv_t ).
    cl_abap_unit_assert=>assert_equals( act = lv_ts exp = mv_t0 ).
    lv_txt = zcl_brl_house_report=>cause_text( 'COOL' ).
    cl_abap_unit_assert=>assert_equals( act = lv_txt exp = 'Cooling stage below the heat load' ).
  ENDMETHOD.

ENDCLASS.
