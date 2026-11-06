FUNCTION z_brl_stress_post.
*"----------------------------------------------------------------------
*"*"Update Function Module:     (function group ZBRL_FG,
*"                               processing type: Update Module, Start immediately)
*"  IMPORTING
*"     VALUE(IS_ROW) TYPE  ZBRL_STRESS
*"     VALUE(IS_NOTIF) TYPE  ZBRL_NOTIF OPTIONAL
*"----------------------------------------------------------------------
* Runs in the update task together with the PM notification posted by BAPI_ALM_NOTIF_SAVE.
* A failed insert terminates the whole update (type A message), so nothing of the call is kept.
*----------------------------------------------------------------------
  INSERT zbrl_stress FROM is_row.
  IF sy-subrc <> 0.
    MESSAGE a001(00) WITH 'ZBRL_STRESS insert failed' is_row-assess_id.
  ENDIF.

  IF is_notif-flock IS NOT INITIAL.
    INSERT zbrl_notif FROM is_notif.
    IF sy-subrc <> 0.
      MESSAGE a001(00) WITH 'ZBRL_NOTIF insert failed' is_notif-assess_id.
    ENDIF.
  ENDIF.
ENDFUNCTION.
