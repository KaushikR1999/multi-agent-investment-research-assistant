import streamlit as st

from frontend.api_client import ResearchApiError, get_backend_url, request_research_brief
from frontend.components.report_view import render_response


BACKEND_URL = get_backend_url()

st.set_page_config(page_title="Investment Research Assistant", layout="wide")

st.title("Investment Research Assistant")
st.caption(
    "Evidence-grounded multi-agent research brief. "
    "This is not financial advice and does not provide buy/sell recommendations."
)

with st.form("research_form"):
    query = st.text_input("Ticker or company name", placeholder="AAPL or Apple")
    submitted = st.form_submit_button("Generate research brief", type="primary")

if submitted:
    if not query.strip():
        st.warning("Enter a ticker or company name.")
    else:
        with st.spinner("Running research workflow..."):
            try:
                response_payload = request_research_brief(query=query.strip(), backend_url=BACKEND_URL)
            except ResearchApiError as exc:
                st.error(str(exc))
            else:
                render_response(response_payload)

st.divider()
st.caption(f"Backend: {BACKEND_URL}")
