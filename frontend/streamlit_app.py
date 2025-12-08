# frontend/streamlit_app.py

import streamlit as st
import requests

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="AI File Processor", layout="centered")

# Simple custom CSS for neat UI
st.markdown("""
<style>
.main-card {
    padding: 24px 24px 18px 24px;
    border-radius: 14px;
    background-color: #f9fafb;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    margin-bottom: 20px;
}
.section-title {
    font-size: 22px;
    font-weight: 600;
    margin-bottom: 8px;
}
.small-label {
    font-size: 14px;
    color: #666;
}
.result-card {
    padding: 20px;
    border-radius: 10px;
    background-color: #ffffff;
    border-left: 5px solid #22c55e;
    margin-top: 15px;
}
</style>
""", unsafe_allow_html=True)

st.title("📄 AI File Processor")
st.caption("Upload a file, then analyze it with Gemini for summary, insights, topics, and sentiment.")

# ------------------ UPLOAD SECTION ------------------

st.markdown("<div class='main-card'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>⬆️ Upload File</div>", unsafe_allow_html=True)
st.markdown("<p class='small-label'>Step 1: Choose a file and upload it. You'll get a File ID.</p>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Choose a file", type=["pdf", "txt", "docx"])

if st.button("Upload File", type="primary"):
    if uploaded_file:
        files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
        with st.spinner("Uploading file to server..."):
            res = requests.post(f"{API_BASE}/upload", files=files)

        if res.status_code == 200:
            resp_json = res.json()
            file_id = resp_json["file_id"]
            st.success("✅ File uploaded successfully!")
            st.info(f"📌 Your File ID (save this): `{file_id}`")
        else:
            st.error(f"❌ Upload failed: {res.text}")
    else:
        st.warning("⚠️ Please select a file first.")
st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# ------------------ PROCESS SECTION ------------------

st.markdown("<div class='main-card'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>🤖 Text Extraction & AI Analysis</div>", unsafe_allow_html=True)
st.markdown("<p class='small-label'>Step 2: Enter a File ID to extract text and run Gemini analysis.</p>", unsafe_allow_html=True)

file_id_input = st.text_input("Enter File ID", placeholder="Paste your File ID here")

if st.button("Extract Text & Analyze", type="secondary"):
    if file_id_input.strip():
        with st.spinner("Processing file and calling Gemini..."):
            res = requests.post(f"{API_BASE}/process/{file_id_input.strip()}")

        if res.status_code == 200:
            data = res.json()
            st.success("✅ AI Analysis Completed!")

            st.markdown("<div class='result-card'>", unsafe_allow_html=True)
            st.subheader("🧠 AI Output (JSON)")
            st.json(data)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            try:
                msg = res.json().get("detail", res.text)
            except Exception:
                msg = res.text
            st.error(f"❌ Error: {msg}")
    else:
        st.warning("⚠️ Please enter a valid File ID.")
st.markdown("</div>", unsafe_allow_html=True)
