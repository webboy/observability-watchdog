"""Streamlit dashboard for the Observability Watchdog."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import ApiClientError, WatchdogApiClient

st.set_page_config(page_title="Observability Watchdog", layout="wide")


def _init_session_state() -> None:
    defaults = {
        "api_base_url": "http://localhost:8000/api/v1",
        "selected_app_id": None,
        "latest_ingestion_run": None,
        "dashboard_ready": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _app_label(app: dict[str, Any]) -> str:
    return f"{app['name']} ({app['slug']})"


def _render_sidebar(client: WatchdogApiClient) -> None:
    st.sidebar.header("App Selector")
    st.session_state.api_base_url = st.sidebar.text_input(
        "API Base URL",
        value=st.session_state.api_base_url,
    )

    try:
        apps = client.list_apps()
    except ApiClientError as exc:
        st.sidebar.error(f"Failed to load apps: {exc}")
        apps = []

    app_options = {app["id"]: _app_label(app) for app in apps}
    if app_options:
        selected = st.sidebar.selectbox(
            "Monitored Application",
            options=list(app_options.keys()),
            format_func=lambda app_id: app_options[app_id],
            index=(
                list(app_options.keys()).index(st.session_state.selected_app_id)
                if st.session_state.selected_app_id in app_options
                else 0
            ),
        )
        st.session_state.selected_app_id = selected
    else:
        st.sidebar.info("No apps found. Create one below.")

    with st.sidebar.expander("Create New App", expanded=not app_options):
        name = st.text_input("Name", value="E-commerce Platform", key="create_app_name")
        slug = st.text_input("Slug", value="ecommerce-platform", key="create_app_slug")
        environment = st.selectbox(
            "Environment",
            options=["production", "staging", "development"],
            key="create_app_environment",
        )
        if st.button("Create App", use_container_width=True):
            try:
                created = client.create_app(name=name, slug=slug, environment=environment)
                st.session_state.selected_app_id = created["id"]
                st.session_state.dashboard_ready = False
                st.success(f"Created app '{created['name']}'")
                st.rerun()
            except ApiClientError as exc:
                st.error(f"Create app failed: {exc}")

    if st.sidebar.button("Refresh Dashboard", use_container_width=True):
        st.session_state.dashboard_ready = True
        st.rerun()


def _poll_ingestion(client: WatchdogApiClient, app_id: str, run_id: str) -> dict[str, Any] | None:
    with st.spinner("Processing ingestion run..."):
        try:
            run = client.poll_ingestion_run(app_id, run_id)
        except ApiClientError as exc:
            st.error(f"Ingestion polling failed: {exc}")
            return None

    st.session_state.latest_ingestion_run = run
    if run.get("status") == "completed":
        st.session_state.dashboard_ready = True
        st.success(
            "Ingestion completed: "
            f"{run.get('accepted_events', 0)} accepted, "
            f"{run.get('detected_anomalies', 0)} anomalies, "
            f"{run.get('alerts_triggered', 0)} alerts."
        )
    else:
        st.session_state.dashboard_ready = False
        st.error("Ingestion run failed during background processing.")
    return run


def _render_ingestion(client: WatchdogApiClient, app_id: str) -> None:
    st.subheader("Data Ingestion")
    col_upload, col_sample, col_clear = st.columns(3)

    with col_upload:
        uploaded = st.file_uploader("Upload ECS JSONL Logs", type=["jsonl", "ndjson", "txt"])
        if uploaded is not None and st.button("Upload File", key="upload_logs"):
            try:
                response = client.upload_logs(app_id, uploaded.name, uploaded.getvalue())
                st.session_state.dashboard_ready = False
                _poll_ingestion(client, app_id, response["ingestion_run_id"])
            except ApiClientError as exc:
                st.error(f"Upload failed: {exc}")

    with col_sample:
        st.write("Load bundled incident dataset")
        if st.button("Load Sample Incident Dataset", use_container_width=True):
            try:
                response = client.load_sample_dataset(app_id)
                st.session_state.dashboard_ready = False
                _poll_ingestion(client, app_id, response["ingestion_run_id"])
            except ApiClientError as exc:
                st.error(f"Sample load failed: {exc}")

    with col_clear:
        st.write("Reset app-scoped dynamic data")
        if st.button("Clear App Data", type="secondary", use_container_width=True):
            try:
                result = client.clear_app_data(app_id)
                st.session_state.latest_ingestion_run = None
                st.session_state.dashboard_ready = False
                st.success(
                    "Cleared dynamic data: "
                    f"{result['deleted_log_events']} logs, "
                    f"{result['deleted_anomalies']} anomalies, "
                    f"{result['deleted_alerts']} alerts."
                )
                st.rerun()
            except ApiClientError as exc:
                st.error(f"Clear data failed: {exc}")

    if st.session_state.latest_ingestion_run:
        run = st.session_state.latest_ingestion_run
        st.info(
            f"Latest ingestion run `{run.get('id')}` status: **{run.get('status')}** | "
            f"accepted={run.get('accepted_events', 0)}, "
            f"rejected={run.get('rejected_events', 0)}, "
            f"skipped={run.get('skipped_duplicates', 0)}"
        )


def _render_overview(client: WatchdogApiClient, app_id: str) -> None:
    st.subheader("Overview Metrics")
    try:
        overview = client.get_overview(app_id)
    except ApiClientError as exc:
        st.error(f"Failed to load overview: {exc}")
        return

    row1 = st.columns(4)
    row1[0].metric("Total Logs", overview["total_logs"])
    row1[1].metric("Accepted Events", overview["accepted_events"])
    row1[2].metric("Rejected Events", overview["rejected_events"])
    row1[3].metric("Skipped Duplicates", overview["skipped_duplicates"])

    row2 = st.columns(4)
    row2[0].metric("Active Anomalies (24h)", overview["active_anomalies"])
    row2[1].metric("Triggered Alerts", overview["triggered_alerts"])
    row2[2].metric("System Health Score", overview["system_health_score"])
    latest_ts = overview.get("latest_log_timestamp")
    row2[3].metric("Latest Log Timestamp", latest_ts or "N/A")

    st.caption(
        "Health score = max(0, 100 - 25 × critical - 10 × warning) over anomalies in the "
        "24 hours before the latest log timestamp. "
        f"Current window: {overview['critical_anomalies_24h']} critical, "
        f"{overview['warning_anomalies_24h']} warning."
    )


def _aggregate_windows_for_chart(
    windows: list[dict[str, Any]],
    value_field: str,
    *,
    agg: str = "sum",
) -> pd.DataFrame:
    if not windows:
        return pd.DataFrame(columns=["window_start", "service_name", value_field])

    frame = pd.DataFrame(windows)
    frame["window_start"] = pd.to_datetime(frame["window_start"])
    grouped = frame.groupby(["window_start", "service_name"], as_index=False)[value_field]
    if agg == "mean":
        result = grouped.mean(numeric_only=True)
    else:
        result = grouped.sum(min_count=1)
    return result.sort_values("window_start")


def _render_health_trends(client: WatchdogApiClient, app_id: str) -> None:
    st.subheader("Health Trends")
    try:
        windows = client.get_metric_windows(app_id)
    except ApiClientError as exc:
        st.error(f"Failed to load metric windows: {exc}")
        return

    if not windows:
        st.info("No metric windows yet. Upload logs to populate health trends.")
        return

    tab_errors, tab_5xx, tab_latency = st.tabs(["Errors Over Time", "HTTP 5xx Rate", "P95 Latency"])

    errors_df = _aggregate_windows_for_chart(windows, "error_count")
    with tab_errors:
        fig = px.line(
            errors_df,
            x="window_start",
            y="error_count",
            color="service_name",
            markers=True,
            title="Error Count by Service",
        )
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    rate_df = _aggregate_windows_for_chart(windows, "http_5xx_rate", agg="mean")
    with tab_5xx:
        fig = px.line(
            rate_df,
            x="window_start",
            y="http_5xx_rate",
            color="service_name",
            markers=True,
            title="HTTP 5xx Rate by Service",
        )
        fig.update_layout(hovermode="x unified", yaxis_tickformat=".1%")
        st.plotly_chart(fig, use_container_width=True)

    latency_df = pd.DataFrame(windows)
    latency_df["window_start"] = pd.to_datetime(latency_df["window_start"])
    latency_df = latency_df.dropna(subset=["latency_p95_ms"])
    with tab_latency:
        if latency_df.empty:
            st.info("No latency samples available yet.")
        else:
            fig = px.line(
                latency_df,
                x="window_start",
                y="latency_p95_ms",
                color="service_name",
                hover_data=["url_path"],
                markers=True,
                title="P95 Latency (ms) by Service",
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)


def _render_top_failing_services(client: WatchdogApiClient, app_id: str) -> None:
    st.subheader("Top Failing Services")
    try:
        services = client.get_top_failing_services(app_id)
    except ApiClientError as exc:
        st.error(f"Failed to load top failing services: {exc}")
        return

    if not services:
        st.info("No service metrics available yet.")
        return

    frame = pd.DataFrame(services)
    st.dataframe(frame, use_container_width=True, hide_index=True)

    chart_df = frame.sort_values("failure_score", ascending=True)
    fig = px.bar(
        chart_df,
        x="failure_score",
        y="service_name",
        orientation="h",
        title="Failure Score by Service",
        hover_data=["error_count", "http_5xx_count", "avg_error_rate", "max_p95_latency_ms"],
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_anomalies_and_alerts(client: WatchdogApiClient, app_id: str) -> None:
    st.subheader("Anomalies And Alerts")
    tab_anomalies, tab_alerts = st.tabs(["Detected Anomalies", "Triggered Alerts"])

    with tab_anomalies:
        try:
            anomalies = client.get_anomalies(app_id)
        except ApiClientError as exc:
            st.error(f"Failed to load anomalies: {exc}")
            anomalies = []
        if anomalies:
            st.dataframe(pd.DataFrame(anomalies), use_container_width=True, hide_index=True)
        else:
            st.info("No anomalies detected yet.")

    with tab_alerts:
        try:
            alerts = client.get_alerts(app_id)
        except ApiClientError as exc:
            st.error(f"Failed to load alerts: {exc}")
            alerts = []
        if alerts:
            summary_rows = []
            for alert in alerts:
                payload = alert.get("webhook_payload", {})
                summary_rows.append(
                    {
                        "created_at": alert.get("created_at"),
                        "severity": alert.get("severity"),
                        "delivery_status": alert.get("delivery_status"),
                        "service_name": payload.get("service_name"),
                        "metric_name": payload.get("metric_name"),
                        "message": payload.get("message"),
                    }
                )
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
            for alert in alerts:
                with st.expander(f"Webhook payload {alert.get('id')}"):
                    st.code(json.dumps(alert.get("webhook_payload", {}), indent=2), language="json")
        else:
            st.info("No alerts triggered yet.")


def _render_incident_summary(client: WatchdogApiClient, app_id: str) -> None:
    st.subheader("Incident Summary")
    try:
        summaries = client.get_incident_summaries(app_id)
    except ApiClientError as exc:
        st.error(f"Failed to load incident summaries: {exc}")
        return

    if not summaries:
        st.info("No incident summaries available yet.")
        return

    latest = summaries[0]
    st.markdown(f"**Generation Source:** `{latest.get('generation_source')}`")
    st.markdown(f"**Service:** {latest.get('service_name')} | **Severity:** {latest.get('severity')}")
    st.markdown(f"**Summary:** {latest.get('summary')}")

    cols = st.columns(2)
    cols[0].markdown(f"**What Happened**\n\n{latest.get('what_happened') or 'N/A'}")
    cols[1].markdown(f"**Likely Cause**\n\n{latest.get('likely_cause') or 'N/A'}")
    cols[0].markdown(f"**Business Impact**\n\n{latest.get('business_impact') or 'N/A'}")
    cols[1].markdown(f"**Recommended Action**\n\n{latest.get('recommended_action') or 'N/A'}")

    if len(summaries) > 1:
        with st.expander("Additional incident summaries"):
            st.dataframe(pd.DataFrame(summaries[1:]), use_container_width=True, hide_index=True)


def main() -> None:
    _init_session_state()
    client = WatchdogApiClient(st.session_state.api_base_url)

    st.title("Observability Watchdog Dashboard")
    st.caption("API-first SRE observability dashboard for ECS JSONL ingestion, anomaly detection, and alerts.")

    _render_sidebar(client)

    app_id = st.session_state.selected_app_id
    if not app_id:
        st.warning("Select or create an app to begin.")
        return

    _render_ingestion(client, app_id)

    if not st.session_state.dashboard_ready:
        st.info("Dashboard charts and tables will appear after ingestion completes.")
        return

    _render_overview(client, app_id)
    st.divider()
    _render_health_trends(client, app_id)
    st.divider()
    _render_top_failing_services(client, app_id)
    st.divider()
    _render_anomalies_and_alerts(client, app_id)
    st.divider()
    _render_incident_summary(client, app_id)


if __name__ == "__main__":
    main()
