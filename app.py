import io
import re
import zipfile

import streamlit as st
from pypdf import PdfReader, PdfWriter


# --------- Depot ID extraction logic --------- #

def extract_depot_id_from_text(text: str) -> str:
    """
    Extracts the Depot ID from the full page text.

    In your PDF, the 4-digit depot ID (2104) appears before the 'Depot ID' label
    glued to another value like '1:34' → '1:342104'.

    Strategy:
      1) Look for a 4-digit number immediately before a newline and 'Depot ID'.
      2) Fallback: look for a 4-digit number after 'Depot ID'.
    """
    if not text:
        return "UNKNOWN"

    # Primary pattern: 4 digits followed by newline then 'Depot ID'
    match = re.search(r"(\d{4})\s*[\r\n]+\s*Depot ID", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    # Fallback: 'Depot ID' then some non-digits then a 4-digit number
    match2 = re.search(r"Depot ID[^\d]+(\d{4})", text,
                       flags=re.IGNORECASE | re.DOTALL)
    if match2:
        return match2.group(1)

    return "UNKNOWN"


def extract_depot_id(page) -> str:
    text = page.extract_text() or ""
    return extract_depot_id_from_text(text)


def depot_id_to_filename(depot_id: str) -> str:
    """
    Convert depot_id '2104' → filename '104V_CL.pdf'
    """
    if depot_id == "UNKNOWN" or not depot_id.isdigit() or len(depot_id) < 2:
        base = depot_id
    else:
        base = depot_id[1:] + "V"
    return f"{base}_CL.pdf"


# --------- Streamlit App --------- #

st.set_page_config(page_title="Depot Call List Splitter", page_icon="📄", layout="wide")

# ---- Display the logo ---- #
try:
    st.image("messer-logo (1).svg", width=180)
except:
    st.warning("⚠️ Logo file not found. Make sure 'messer-logo (1).svg' is in the same folder as app.py")

st.title("📄 Depot Call List Splitter")
st.markdown(
    """
    Upload a **Call List PDF** and this app will:

    - Detect the **Depot ID** on each page  
    - Group pages by Depot ID  
    - Rename each PDF using the rule:  
      - Depot ID `2104` → `104V_CL.pdf`  
    - Provide a **ZIP download** of all files  
    """
)

uploaded_file = st.file_uploader("Upload your Call List PDF", type=["pdf"])

if uploaded_file:
    st.success(f"File uploaded: `{uploaded_file.name}`")

    if st.button("🚀 Split PDF by Depot ID"):
        try:
            uploaded_file.seek(0)

            reader = PdfReader(uploaded_file)
            num_pages = len(reader.pages)
            st.write(f"Detected **{num_pages}** pages.")

            depot_writers = {}

            for page_index, page in enumerate(reader.pages):
                depot_id = extract_depot_id(page)

                if depot_id not in depot_writers:
                    depot_writers[depot_id] = PdfWriter()

                depot_writers[depot_id].add_page(page)
                st.write(f"Page {page_index + 1}: Depot ID `{depot_id}`")

            depot_ids = list(depot_writers.keys())
            st.write("### Depot IDs identified:")
            st.json(depot_ids)

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for depot_id, writer in depot_writers.items():
                    filename = depot_id_to_filename(depot_id)

                    pdf_bytes = io.BytesIO()
                    writer.write(pdf_bytes)
                    pdf_bytes.seek(0)

                    zip_file.writestr(filename, pdf_bytes.read())

            zip_buffer.seek(0)

            st.success("Splitting complete! Download your ZIP below:")

            st.download_button(
                label="⬇️ Download ZIP",
                data=zip_buffer,
                file_name="call_lists_by_depot.zip",
                mime="application/zip",
            )

        except Exception as e:
            st.error(f"❌ Error: {e}")

else:
    st.info("📥 Please upload a PDF to begin.")
