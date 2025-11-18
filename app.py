import streamlit as st
from pypdf import PdfReader, PdfWriter
import io
import zipfile
import re


# ---------- Depot ID extraction ----------

def extract_depot_id(page) -> str:
    """
    Extracts the Depot ID from a page's text.

    From your sample, the structure near the top is:

        Distance Driving Time
        1 76 1:342104
        Depot ID Shift Start TimeRte Num
        24
        ...

    The 4-digit depot ID (2104) appears on the line
    *before* the one that contains 'Depot ID',
    stuck to '1:34' as '1:342104'.

    Strategy:
      - Look for a 4-digit number immediately before a newline
        followed by a line containing 'Depot ID'.
      - As a fallback, look for a 4-digit number after 'Depot ID'.
    """
    text = page.extract_text() or ""

    # Primary pattern: 4 digits followed by newline and then 'Depot ID'
    match = re.search(r"(\d{4})\s*[\r\n]+\s*Depot ID", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    # Fallback pattern: 'Depot ID' then some non-digits then 4 digits
    match2 = re.search(r"Depot ID[^\d]+(\d{4})", text,
                       flags=re.IGNORECASE | re.DOTALL)
    if match2:
        return match2.group(1)

    return "UNKNOWN"


def depot_id_to_filename(depot_id: str) -> str:
    """
    Convert a depot_id like '2104' into the required filename:

      2104 -> 104 -> 104V -> 104V_CL.pdf
    """
    if depot_id == "UNKNOWN" or not depot_id.isdigit() or len(depot_id) < 2:
        base = depot_id
    else:
        base = depot_id[1:] + "V"

    return f"{base}_CL.pdf"


# ---------- Streamlit UI ----------

st.title("Depot Call List Splitter")

st.write(
    "Upload a **Call List PDF**, and this app will split it into one PDF per Depot ID, "
    "rename each using the **104V_CL** pattern, and give you a ZIP to download."
)

uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])

if uploaded_file is not None:
    st.success(f"File uploaded: {uploaded_file.name}")

    if st.button("Split PDF by Depot ID"):
        try:
            # Read the uploaded PDF
            reader = PdfReader(uploaded_file)
            num_pages = len(reader.pages)
            st.write(f"Detected **{num_pages}** pages.")

            # Map depot_id -> PdfWriter
            depot_writers = {}

            # Extract depot IDs and build writers
            for page_index, page in enumerate(reader.pages):
                depot_id = extract_depot_id(page)

                if depot_id not in depot_writers:
                    depot_writers[depot_id] = PdfWriter()

                depot_writers[depot_id].add_page(page)

            # Show what depot IDs were found
            st.write("Found the following Depot IDs:")
            st.json(list(depot_writers.keys()))

            # Create ZIP in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for depot_id, writer in depot_writers.items():
                    filename = depot_id_to_filename(depot_id)

                    pdf_bytes = io.BytesIO()
                    writer.write(pdf_bytes)
                    pdf_bytes.seek(0)

                    zip_file.writestr(filename, pdf_bytes.read())

            zip_buffer.seek(0)

            st.download_button(
                label="Download split PDFs as ZIP",
                data=zip_buffer,
                file_name="call_lists_by_depot.zip",
                mime="application/zip",
            )

        except Exception as e:
            st.error(f"An error occurred: {e}")
else:
    st.info("Please upload a PDF file to get started.")
