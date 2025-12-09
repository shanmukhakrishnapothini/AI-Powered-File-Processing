import streamlit as st
import requests

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="AI File Processor", layout="centered")

st.markdown("""
<style>
.main-card {
    padding: 24px;
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
</style>
""", unsafe_allow_html=True)

st.title("📄 AI File Processor")

if "mode" not in st.session_state:
    st.session_state.mode = None   # upload or extract

col1, col2 = st.columns(2)

with col1:
    if st.button("⬆️ Upload File", use_container_width=True):
        st.session_state.mode = "upload"

with col2:
    if st.button("🤖 Extract From File", use_container_width=True):
        st.session_state.mode = "extract"

st.divider()

if st.session_state.mode == "upload":
    st.markdown("<div class='section-title'>⬆️ Upload File</div>", unsafe_allow_html=True)
    st.markdown("<p class='small-label'>Choose a file and upload it. You will receive a File ID.</p>", unsafe_allow_html=True)

    uploaded_file = st.file_uploader("Choose a file", type=["pdf", "txt", "docx"])

    if st.button("Submit Upload", type="primary"):
        if uploaded_file:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue())}

            with st.spinner("Uploading file..."):
                res = requests.post(f"{API_BASE}/upload", files=files)

            if res.status_code == 200:
                resp_json = res.json()
                file_id = resp_json["file_id"]
                st.success("✅ File uploaded successfully!")
                st.info(f"📌 Your File ID(save it for later): `{file_id}`")
            else:
                st.error(f"❌ Upload failed: {res.text}")
        else:
            st.warning("⚠️ Please select a file first.")

elif st.session_state.mode == "extract":
    st.markdown("<div class='section-title'>🤖 Extract & Analyze</div>", unsafe_allow_html=True)
    st.markdown("<p class='small-label'>Enter your File ID to extract and analyze.</p>", unsafe_allow_html=True)

    file_id_input = st.text_input("Enter File ID", placeholder="Paste your File ID here")

    if st.button("Run Extraction & Analysis", type="secondary"):
        if file_id_input.strip():
            with st.spinner("Processing file and calling Gemini..."):
                res = requests.post(f"{API_BASE}/process/{file_id_input.strip()}")

            if res.status_code == 200:
                data = res.json()
                st.success("✅ AI Analysis Completed!")
                st.subheader("🧠 AI Output")
                st.json(data)
            else:
                try:
                    msg = res.json().get("detail", res.text)
                except Exception:
                    msg = res.text
                st.error(f"❌ Error: {msg}")
        else:
            st.warning("⚠️ Please enter a valid File ID.")
