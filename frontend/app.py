import os

import streamlit as st


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


st.set_page_config(page_title="Investment Research Assistant", layout="wide")

st.title("Investment Research Assistant")
st.caption("MVP scaffold. Research workflow implementation starts after Ticket 1 approval.")

query = st.text_input("Ticker or company name", placeholder="AAPL or Apple")

if st.button("Generate research brief", type="primary"):
    if not query.strip():
        st.warning("Enter a ticker or company name.")
    else:
        st.info(
            "The research workflow is not implemented yet. "
            f"When ready, this app will call {BACKEND_URL}/research."
        )

st.divider()
st.caption("Not financial advice. Outputs should be evidence-grounded and verifier checked.")
