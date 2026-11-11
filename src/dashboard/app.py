"""Supervisor dashboard: watch the agents work and approve or reject fixes (the human gate).

Run with ``make dashboard`` (``streamlit run src/dashboard/app.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from src.agents import Pipeline, default_client  # noqa: E402
from src.agents.observe import observe  # noqa: E402
from src.dashboard import views  # noqa: E402
from src.scenarios import SCENARIOS  # noqa: E402
from src.twin import LineConfig  # noqa: E402

st.set_page_config(page_title="Agentic Digital Twin", layout="wide")


@st.cache_resource
def get_client():  # type: ignore[no-untyped-def]
    """One LLM client (mock unless an API key is configured) shared across reruns."""
    return default_client()


def start_run() -> None:
    """Create a human-in-the-loop pipeline from the sidebar widgets and run it until the gate."""
    scenario, seed = st.session_state["scenario_pick"], int(st.session_state["seed_pick"])
    pipe = Pipeline(SCENARIOS[scenario], seed, get_client(), approver=None, use_simulation=st.session_state["use_sim"])
    with st.spinner("Monitor, Diagnosis and Simulation agents working..."):
        pipe.start()
    st.session_state.update(pipe=pipe, scenario=scenario, seed=seed)


def decide(approved: bool) -> None:
    """Send the supervisor's verdict into the graph and resume."""
    with st.spinner("Resuming..." if approved else "Re-diagnosing after rejection..."):
        st.session_state["pipe"].submit_human_decision(approved, st.session_state.get("reason", ""))


client = get_client()
with st.sidebar:
    st.title("Agentic Digital Twin")
    st.caption("Verify before act: nothing is applied until the twin shows a gain and you approve.")
    st.selectbox("Scenario", list(SCENARIOS), key="scenario_pick")
    st.number_input("Seed", min_value=1, max_value=9999, value=1, step=1, key="seed_pick")
    st.checkbox("Simulation agent on (verify before recommending)", value=True, key="use_sim")
    st.button("Start run", type="primary", key="start", on_click=start_run)
    st.info("Mock mode (scripted agents, offline)" if client.is_mock else f"Real LLM: {client.model}")
    st.subheader("Architecture")
    st.graphviz_chart(views.ARCHITECTURE_DOT)

pipe: Pipeline | None = st.session_state.get("pipe")
if pipe is None:
    st.header("Supervisor dashboard")
    st.write("Pick a scenario and seed in the sidebar, then press **Start run**.")
    st.stop()

state = pipe.current_state()
cfg = SCENARIOS[st.session_state["scenario"]].config
obs_result = observe(cfg, st.session_state["seed"]).result
st.header(f"{st.session_state['scenario']} (seed {st.session_state['seed']})")

left, right = st.columns(2)
with left:
    st.subheader("Line KPIs (observed shift)")
    st.line_chart(views.throughput_frame(obs_result), y_label="units per 30 min", x_label="hours")
with right:
    st.subheader("Station time split")
    st.bar_chart(views.station_frame(state["observation"]), y_label="fraction of shift")

st.subheader("Findings")
mon, diag = state["monitor"], state["diagnosis"]
st.write(f"**Monitor:** {mon['summary']}")
for a in mon["anomalies"]:
    st.write(f"- `{a['kind']}` station {a['station']}: {a['detail']}")
st.write(
    f"**Diagnosis (round {state['iteration']}):** station {diag['bottleneck_station']} / {diag['fault_type']} "
    f"(confidence {diag['confidence']}). {diag['explanation']}"
)

if state.get("candidates"):
    st.subheader("Candidate fixes tested in the twin")
    st.dataframe(views.candidates_frame(state["candidates"]), hide_index=True, width="stretch")

outcome = state.get("outcome")
if pipe.paused_at_gate:
    rec = state["recommendation"]
    st.subheader("Supervisor gate")
    st.write(f"**Recommended:** `{views.action_label(rec['action'])}`")
    ev = rec.get("evidence")
    if ev:
        st.write(f"Twin evidence: {ev['baseline_mean']:.1f} to {ev['new_mean']:.1f} units/shift ({ev['gain_pct']:+.1f}%, p={ev['p_value']:.3f}).")
    else:
        st.warning("No twin evidence: this fix was not simulated.")
    st.text_input("Reason (optional)", key="reason")
    c1, c2 = st.columns(2)
    c1.button("Approve", type="primary", key="approve", on_click=decide, args=(True,))
    c2.button("Reject (re-diagnose)", key="reject", on_click=decide, args=(False,))
elif outcome:
    st.subheader(f"Outcome: {outcome}")
    if state.get("applied_action"):
        res = views.before_after(cfg, LineConfig.model_validate(state["config"]))
        st.success(f"Applied `{views.action_label(state['applied_action'])}`: {res['before']:.1f} to {res['after']:.1f} units/shift ({res['gain_pct']:+.1f}%).")
    else:
        st.info("No fix was applied.")

st.subheader("Agent trace and token usage")
usage = pipe.meter.as_dict()
m1, m2, m3 = st.columns(3)
m1.metric("LLM steps", usage["steps"])
m2.metric("Input tokens", usage["input_tokens"])
m3.metric("Output tokens", usage["output_tokens"])
st.dataframe(views.trace_frame(state["trace"]), hide_index=True, width="stretch")
if state.get("gate_log"):
    st.caption("Gate log")
    st.dataframe(state["gate_log"], hide_index=True, width="stretch")
