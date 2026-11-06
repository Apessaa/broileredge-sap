FUNCTION z_brl_test_reset.
*"----------------------------------------------------------------------
*"*"Local Interface:            (function group ZBRL_FG, Remote-Enabled Module)
*"  IMPORTING
*"     VALUE(IV_FLOCK_PREFIX) TYPE  CHAR20
*"  EXPORTING
*"     VALUE(EV_DELETED) TYPE  I
*"----------------------------------------------------------------------
* Deletes the rows of earlier TEST runs only: the prefix must start with 'TST' and be at least
* four characters long. Never call it with a production flock. Use only in a sandbox client.
*----------------------------------------------------------------------
  DATA lv_pattern TYPE c LENGTH 21.

  ev_deleted = -1.
  IF strlen( iv_flock_prefix ) < 4 OR iv_flock_prefix(3) <> 'TST'.
    RETURN.
  ENDIF.

  CONCATENATE iv_flock_prefix '%' INTO lv_pattern.
  DELETE FROM zbrl_stress WHERE flock LIKE lv_pattern.
  ev_deleted = sy-dbcnt.
  DELETE FROM zbrl_notif WHERE flock LIKE lv_pattern.
  ev_deleted = ev_deleted + sy-dbcnt.
  COMMIT WORK.
ENDFUNCTION.
