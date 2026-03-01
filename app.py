from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import streamlit as st
import re

try:
    import requests
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    requests = None
    BeautifulSoup = None

from logic.router import route_patient
from yaml_compat import safe_load


ROOT = Path(__file__).resolve().parent
PATHWAYS_DIR = ROOT / "pathways"
SOURCES_PATH = ROOT / "source" / "sources.yaml"


def age_months_from_days(age_days: int) -> float:
    return age_days / 30.4375


def load_pathway(pathway_id: str) -> Dict[str, Any]:
    path = PATHWAYS_DIR / f"{pathway_id}.yaml"
    if not path.exists():
        return {}
    return safe_load(path.read_text()) or {}


@st.cache_data
def load_source_catalog() -> Dict[str, Dict[str, Any]]:
    data = safe_load(SOURCES_PATH.read_text()) or {}
    pathways = data.get("pathways", [])
    return {p["id"]: p for p in pathways if "id" in p}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@st.cache_data(show_spinner=False, ttl=3600)
def scrape_chop_recommendations(url: str) -> Dict[str, Any]:
    if requests is None or BeautifulSoup is None:
        return {"ok": False, "recommendations": [], "error": "requests/bs4 not installed"}
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        return {"ok": False, "recommendations": [], "error": str(exc)}

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()

    recs: List[str] = []
    for li in soup.find_all("li"):
        txt = _clean_text(li.get_text(" ", strip=True))
        if len(txt) >= 40 and txt not in recs:
            recs.append(txt)
        if len(recs) >= 6:
            break

    if not recs:
        paragraphs = []
        for p in soup.find_all("p"):
            txt = _clean_text(p.get_text(" ", strip=True))
            if len(txt) >= 60:
                paragraphs.append(txt)
            if len(paragraphs) >= 4:
                break
        recs = paragraphs

    return {"ok": True, "recommendations": recs[:6], "error": None}


def init_nav_state(pathway: Dict[str, Any]) -> None:
    nodes = pathway.get("nodes", [])
    start_node = next((n for n in nodes if n.get("id") == "start"), nodes[0] if nodes else None)
    st.session_state.nav_current = start_node.get("id") if start_node else None
    st.session_state.nav_history = []


def page_router() -> None:
    st.title("Pediatric Infectious Pathway Router")

    age_mode = st.radio("Age Input", ["days", "years/months/days"], horizontal=True)
    if age_mode == "days":
        age_days = int(st.number_input("Age (days)", min_value=0, max_value=8000, value=365))
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            years = int(st.number_input("Years", min_value=0, max_value=21, value=1))
        with col2:
            months = int(st.number_input("Months", min_value=0, max_value=11, value=0))
        with col3:
            days = int(st.number_input("Days", min_value=0, max_value=30, value=0))
        age_days = years * 365 + months * 30 + days

    st.caption(f"Computed age_days: {age_days}")
    age_months = age_months_from_days(age_days)

    ga_weeks = None
    if age_days < 60:
        ga_preterm = st.checkbox("Gestational age <37 weeks", value=False)
        if ga_preterm:
            ga_weeks = int(st.number_input("Gestational age at birth (weeks)", min_value=22, max_value=36, value=35))
        ill_infant = st.checkbox("Ill-appearing infant", value=False)
    else:
        ill_infant = False

    fever_days = int(st.number_input("Fever duration (days)", min_value=0, max_value=30, value=1))
    ill_appearing = st.checkbox("Ill appearing", value=ill_infant)
    hemodynamic_instability = st.checkbox("Hemodynamic instability", value=False)
    altered_mental_status = st.checkbox("Altered mental status", value=False)
    immunocompromised_or_onc = st.checkbox("Immunocompromised or oncology patient", value=False)

    st.subheader("System Findings")
    neuro = st.multiselect(
        "Neuro",
        ["seizure", "neck_stiffness", "severe_headache"],
    )
    resp = st.multiselect("Respiratory", ["influenza_like_illness", "hypoxia", "respiratory_distress"])
    ent = st.multiselect("HEENT", ["eye_swelling", "periorbital_erythema", "pain_with_eom", "drooling", "muffled_voice", "trismus"])
    gi = st.multiselect("GI", ["vomiting", "diarrhea", "severe_focal_abdominal_pain"])
    gu = st.multiselect("GU", ["dysuria", "flank_pain", "fever_without_source"])
    msk = st.multiselect("MSK", ["joint_pain", "limp", "refusal_to_bear_weight"])
    skin = st.multiselect("Skin", ["localized_erythema", "warmth_or_tenderness", "fluctuance_or_purulence", "localized_swelling"])

    kd_features = int(st.slider("Kawasaki features count", min_value=0, max_value=5, value=0))

    uticalc_payload: Dict[str, Any] = {}
    uticalc_allowed = 2 <= age_months <= 24
    if uticalc_allowed:
        st.subheader("UTICalc (Race-Free Pretest, 2-24 months)")
        sex = st.radio("Sex", ["female", "male"], horizontal=True)
        circumcised = None
        if sex == "male":
            circumcised = st.checkbox("Circumcised", value=True)
        use_tmax_toggle = st.checkbox("Use fever >=39C toggle", value=False)
        if use_tmax_toggle:
            tmax_ge_39 = st.checkbox("Tmax >=39C", value=False)
            tmax_c = None
        else:
            tmax_c = float(st.number_input("Tmax C", min_value=35.0, max_value=43.0, value=38.5, step=0.1))
            tmax_ge_39 = None
        other_source = st.checkbox("Other source present", value=False)
        uticalc_payload = {
            "sex": sex,
            "circumcised": circumcised,
            "tmax_ge_39": tmax_ge_39,
            "tmax_c": tmax_c,
            "other_source": other_source,
        }
    else:
        st.info("UTICalc panel appears only for age 2-24 months.")

    patient = {
        "age_days": age_days,
        "age_months": age_months,
        "ga_weeks": ga_weeks,
        "fever_days": fever_days,
        "ill_appearing": ill_appearing,
        "hemodynamic_instability": hemodynamic_instability,
        "altered_mental_status": altered_mental_status,
        "immunocompromised_or_onc": immunocompromised_or_onc,
        "kd_features": kd_features,
        "uticalc": uticalc_payload,
    }

    all_flags = [
        "seizure",
        "neck_stiffness",
        "severe_headache",
        "influenza_like_illness",
        "hypoxia",
        "respiratory_distress",
        "eye_swelling",
        "periorbital_erythema",
        "pain_with_eom",
        "drooling",
        "muffled_voice",
        "trismus",
        "vomiting",
        "diarrhea",
        "severe_focal_abdominal_pain",
        "dysuria",
        "flank_pain",
        "fever_without_source",
        "joint_pain",
        "limp",
        "refusal_to_bear_weight",
        "localized_erythema",
        "warmth_or_tenderness",
        "fluctuance_or_purulence",
        "localized_swelling",
    ]
    for flag in all_flags:
        patient[flag] = False
    for flag in neuro + resp + ent + gi + gu + msk + skin:
        patient[flag] = True

    run_now = st.button("Run Full Parallel Differential", type="primary")
    if run_now or "router_result" not in st.session_state:
        st.session_state.router_result = route_patient(patient)
        st.session_state.router_input = patient

    result = st.session_state.get("router_result", {"pathways": []})

    if result.get("uticalc_pretest_percent") is not None:
        st.caption(f"UTICalc pretest: {result['uticalc_pretest_percent']:.2f}%")

    source_catalog = load_source_catalog()
    differential_items: List[Dict[str, Any]] = result.get("pathways", [])

    st.subheader("Differential To Consider")
    with st.container(border=True):
        if not differential_items:
            st.write("No differential items generated yet.")
        else:
            for item in differential_items:
                src = source_catalog.get(item["id"])
                status_line = f"{item['priority']} | {item['status']}"
                if src:
                    st.markdown(f"- **{item['name']}** ({status_line}) - [Pathway Link]({src['url']})")
                else:
                    st.markdown(f"- **{item['name']}** ({status_line})")

    st.subheader("Recommendations (Scraped From Relevant CHOP Pathways)")
    with st.container(border=True):
        chop_items = []
        for item in differential_items:
            src = source_catalog.get(item["id"])
            if src and src.get("publisher") == "chop" and "chop.edu" in src.get("url", ""):
                chop_items.append((item, src))

        if not chop_items:
            st.write("No relevant CHOP pathways in the current differential.")
        else:
            shown = set()
            for item, src in chop_items:
                if src["url"] in shown:
                    continue
                shown.add(src["url"])

                st.markdown(f"**{item['name']}**")
                st.markdown(f"[Open CHOP Pathway]({src['url']})")
                scraped = scrape_chop_recommendations(src["url"])
                if not scraped["ok"]:
                    st.caption(f"Could not scrape recommendations: {scraped['error']}")
                    continue
                recs = scraped.get("recommendations", [])
                if not recs:
                    st.caption("No recommendation snippets were detected on this page.")
                    continue
                for rec in recs:
                    st.markdown(f"- {rec}")


def page_navigator() -> None:
    st.title("Pathway Navigator")

    selected = st.session_state.get("selected_pathway")
    if not selected:
        st.info("No pathway selected. Open one from Router page.")
        return

    pathway = load_pathway(selected)
    if not pathway:
        st.error(f"Could not load pathway YAML for: {selected}")
        return

    if st.session_state.get("nav_pathway") != selected or "nav_current" not in st.session_state:
        init_nav_state(pathway)
        st.session_state.nav_pathway = selected

    nodes = {n["id"]: n for n in pathway.get("nodes", [])}
    current_id = st.session_state.get("nav_current")
    current = nodes.get(current_id)

    st.write(f"**{pathway.get('title', selected)}** (`{selected}`)")
    if not current:
        st.error("Current node not found.")
        return

    st.write(f"Node: `{current['id']}` ({current.get('type', 'unknown')})")
    st.write(current.get("text", ""))
    sources = current.get("source_urls", [])
    if sources:
        st.write("Sources:")
        for src in sources:
            st.markdown(f"- {src}")

    edges = pathway.get("edges", [])
    next_ids = [e["to"] for e in edges if e.get("from") == current_id]

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Back"):
            history = st.session_state.get("nav_history", [])
            if history:
                st.session_state.nav_current = history.pop()
                st.session_state.nav_history = history
    with col2:
        if st.button("Restart"):
            init_nav_state(pathway)
    with col3:
        if st.button("Router"):
            st.session_state.page = "Router"

    if not next_ids:
        st.success("Reached terminal node.")
        return

    st.write("Next:")
    for nid in next_ids:
        label = nodes.get(nid, {}).get("label", nid)
        if st.button(f"Go to: {label}", key=f"goto_{current_id}_{nid}"):
            history = st.session_state.get("nav_history", [])
            history.append(current_id)
            st.session_state.nav_history = history
            st.session_state.nav_current = nid


def main() -> None:
    if "page" not in st.session_state:
        st.session_state.page = "Router"

    st.sidebar.title("Navigation")
    selected_page = st.sidebar.radio("Page", ["Router", "Pathway Navigator"], index=0 if st.session_state.page == "Router" else 1)
    st.session_state.page = selected_page

    if selected_page == "Router":
        page_router()
    else:
        page_navigator()


if __name__ == "__main__":
    main()
