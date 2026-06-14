from typing import Any

import streamlit as st


SECTION_ORDER = [
    "Company / ticker identified",
    "Market data summary",
    "Recent news sentiment",
    "Fundamentals summary",
    "Key risks",
    "Bull case",
    "Bear case",
    "Balanced view",
]


def render_response(payload: dict[str, Any]) -> None:
    status = payload.get("status", "failed")
    errors = payload.get("errors") or []
    brief = payload.get("brief")

    if status == "completed":
        st.success("Research brief completed.")
    elif status == "partial":
        st.warning("Research brief completed with partial results.")
    else:
        st.error("Research brief failed.")

    if errors:
        with st.expander("Workflow messages", expanded=status != "completed"):
            for error in errors:
                st.write(f"- {error}")

    if not brief:
        return

    render_brief(brief)


def render_brief(brief: dict[str, Any]) -> None:
    company_name = brief.get("company_name", "Unknown company")
    ticker = brief.get("ticker", "Unknown ticker")

    st.header(f"{company_name} ({ticker})")
    st.caption(brief.get("disclaimer", "Not financial advice."))

    sections = {section.get("heading"): section for section in brief.get("sections", [])}
    for heading in SECTION_ORDER:
        section = sections.get(heading)
        if section:
            render_section(section)

    render_verification(brief.get("verification"))
    render_evidence(brief.get("evidence", []))


def render_section(section: dict[str, Any]) -> None:
    st.subheader(section.get("heading", "Report section"))
    st.write(section.get("summary", ""))

    claims = section.get("claims") or []
    if claims:
        with st.expander("Claims and evidence"):
            for claim in claims:
                evidence_ids = ", ".join(claim.get("evidence_ids") or [])
                st.write(f"- {claim.get('text', '')}")
                if evidence_ids:
                    st.caption(f"Evidence: {evidence_ids}")


def render_verification(verification: dict[str, Any] | None) -> None:
    st.divider()
    st.subheader("Verification")

    if not verification:
        st.warning("Verification was not completed.")
        return

    passed = verification.get("passed")
    if passed:
        st.success("Verification passed.")
    else:
        st.error("Verification found issues.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Unsupported claims", verification.get("unsupported_claim_count", 0))
    col2.metric("Contradictions", verification.get("contradiction_count", 0))
    col3.metric("Advice wording", verification.get("advice_wording_count", 0))

    findings = verification.get("findings") or []
    if findings:
        with st.expander("Verification findings", expanded=True):
            for finding in findings:
                severity = finding.get("severity", "info")
                message = finding.get("message", "")
                st.write(f"- **{severity}**: {message}")
                if finding.get("claim_text"):
                    st.caption(f"Claim: {finding['claim_text']}")


def render_evidence(evidence_items: list[dict[str, Any]]) -> None:
    st.divider()
    st.subheader("Evidence")

    if not evidence_items:
        st.info("No evidence records were returned.")
        return

    for item in evidence_items:
        title = item.get("title", "Evidence")
        source_type = item.get("source_type", "unknown")
        with st.expander(f"{source_type}: {title}"):
            st.write(f"Evidence ID: `{item.get('id', '')}`")
            if item.get("publisher"):
                st.write(f"Publisher: {item['publisher']}")
            if item.get("published_at"):
                st.write(f"Published: {item['published_at']}")
            if item.get("url"):
                st.link_button("Open source", item["url"])
            data = item.get("data")
            if data:
                st.json(data)
