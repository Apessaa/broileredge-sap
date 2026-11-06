"""Totals over the SIL runs. Usage: python3 summarise.py sil_results.json [sil_summary.json]"""
import json, sys
R = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "sil_results.json"))
out = {"oracle": R["oracle"], "backend": R.get("backend", "mock")}
for mode in ("idem", "naive"):
    runs = [r for r in R["runs"] if r["mode"] == mode]
    if not runs:
        continue
    s = lambda k: sum(r[k] for r in runs)
    rng = lambda k: (min(r[k] for r in runs), max(r[k] for r in runs))
    out[mode] = {
        "runs": len(runs), "assessments_total": s("windows_expected"), "missing_total": s("missing_windows"),
        "duplicate_rows_total": s("duplicate_rows"), "duplicate_rows_range": rng("duplicate_rows"),
        "level_mismatch_total": s("level_mismatch"),
        "notifications_expected_total": s("notifications_expected"), "notifications_created_total": s("notifications_created"),
        "surplus_notifications_range": (min(r["notifications_created"] - r["notifications_expected"] for r in runs),
                                        max(r["notifications_created"] - r["notifications_expected"] for r in runs)),
        "local_alerts_per_run": rng("local_alerts"),
        "request_faults_total": s("injected_503") + s("injected_lost_ack") + s("injected_slow"),
        "injected_503": s("injected_503"), "injected_lost_ack": s("injected_lost_ack"), "injected_slow": s("injected_slow"),
        "edge_kills": s("edge_kills"), "mw_kills": s("mw_kills"), "outage_s_total": round(s("outage_s"), 1),
        "sap_duplicate_rejected": s("sap_duplicate_rejected"), "max_backlog_range": rng("max_backlog"),
        "sap_unavailable_total": sum(r.get("sap_unavailable", 0) for r in runs),
        "task_mismatch_total": s("task_mismatch"), "rows_with_tasks_total": s("rows_with_tasks"),
        "notification_trigger_mismatch_total": s("notification_trigger_mismatch"),
        "notification_task_mismatch_total": s("notification_task_mismatch"),
        "notification_tasks_total": s("notification_tasks"),
        "notification_tasks_expected_total": s("notification_tasks_expected"),
        "pcause_mismatch_total": s("pcause_mismatch"),
        "reports_total": s("report_count"), "report_notifications_total": s("report_notifications"),
        "report_open_tasks_total": s("report_open_tasks"),
        "report_window_mismatch_total": s("report_window_mismatch"),
        "report_pcause_mismatch_total": s("report_pcause_mismatch"),
        "report_recurring": sorted({c for r in runs for c in r["report_recurring"]}),
    }
json.dump(out, open(sys.argv[2] if len(sys.argv) > 2 else "sil_summary.json", "w"), indent=1)
print(json.dumps(out, indent=1))
