import io
import re
import zipfile

import streamlit as st
from pypdf import PdfReader, PdfWriter


# --------- Common extraction helpers --------- #

def extract_depot_id_from_text(text: str) -> str:
    """
    Extracts the Depot ID from the full page text for the Call List.

    In your Call List PDF, the 4-digit depot ID (e.g. 2104) appears before
    the 'Depot ID' label, stuck to another value like '1:34' → '1:342104'.

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
    Rule: drop first digit, add 'V', then '_CL.pdf'
    """
    if depot_id == "UNKNOWN" or not depot_id.isdigit() or len(depot_id) < 2:
        base = depot_id
    else:
        base = depot_id[1:] + "V"
    return f"{base}_CL.pdf"


def extract_shipping_point_from_text(text: str) -> str:
    """
    Extract Shipping Point like '123V' from the Group List PDF page text.

    We look for a line like:
        Shipping Point    :  123V  Messer St Hubert

    Rules:
    1. On each page there is "Shipping Point : 123V" (123V is variable).
    2. If there is no 3-digits+V next to Shipping Point, disregard the page.
    """
    if not text:
        return "UNKNOWN"

    # Look for "Shipping Point    :  123V"
    match = re.search(r"Shipping Point\s*:\s*([0-9]{3}V)", text)
    if match:
        return match.group(1)

    return "UNKNOWN"


def extract_shipping_point(page) -> str:
    text = page.extract_text() or ""
    return extract_shipping_point_from_text(text)


def shipping_point_to_filename(sp: str) -> str:
    """
    For the Group List:
      Shipping Point '123V' → '123V_Group.pdf'
    """
    if sp == "UNKNOWN":
        base = "UNKNOWN"
    else:
        base = sp
    return f"{base}_Group.pdf"


# --------- Streamlit App Layout --------- #

st.set_page_config(page_title="Messer PDF Tools", page_icon="📄", layout="wide")

# Logo at the top
try:
    st.image("messer-logo (1).svg", width=180)
except Exception:
    st.warning("⚠️ Logo file not found. Make sure 'messer-logo (1).svg' is in the same folder as app.py")

st.title("📄 Messer PDF Splitter Tools")

# Sidebar navigation
page = st.sidebar.radio(
    "Select tool",
    ["Call List Splitter", "Group List Splitter"]
)


# --------- PAGE 1: Call List Splitter --------- #

if page == "Call List Splitter":
    st.header("Call List Splitter")

    st.markdown(
        """
        Upload a **Call List PDF** and this tool will:

        - Detect the **Depot ID** on each page  
        - Group pages by Depot ID  
        - If a page has **no Depot ID match**, it will be added to the **previous depot's PDF**  
        - Rename each PDF using the rule:  
          - Depot ID `2104` → `104V_CL.pdf`  
        - Provide a **ZIP download** of all files  
        """
    )

    uploaded_file = st.file_uploader("Upload Call List PDF", type=["pdf"], key="call_list")

    if uploaded_file:
        st.success(f"File uploaded: `{uploaded_file.name}`")

        if st.button("🚀 Split Call List by Depot ID"):
            try:
                uploaded_file.seek(0)

                reader = PdfReader(uploaded_file)
                num_pages = len(reader.pages)
                st.write(f"Detected **{num_pages}** pages.")

                depot_writers = {}
                last_depot_id = None

                unknown_attached = []   # pages with UNKNOWN attached to previous depot
                unknown_unassigned = [] # pages truly left as UNKNOWN

                # Process each page
                for page_index, page in enumerate(reader.pages):
                    page_num = page_index + 1
                    depot_id_raw = extract_depot_id(page)

                    if depot_id_raw == "UNKNOWN":
                        if last_depot_id is not None:
                            effective_depot_id = last_depot_id
                            unknown_attached.append(
                                {"page": page_num, "assigned_to": last_depot_id}
                            )
                        else:
                            effective_depot_id = "UNKNOWN"
                            unknown_unassigned.append(page_num)
                    else:
                        effective_depot_id = depot_id_raw
                        last_depot_id = depot_id_raw

                    if effective_depot_id not in depot_writers:
                        depot_writers[effective_depot_id] = PdfWriter()

                    depot_writers[effective_depot_id].add_page(page)
                    st.write(
                        f"Page {page_num}: extracted Depot ID `{depot_id_raw}`, "
                        f"assigned to group `{effective_depot_id}`"
                    )

                depot_ids = list(depot_writers.keys())
                st.write("### Depot groups created:")
                st.json(depot_ids)

                if unknown_attached:
                    st.warning("Some pages had no Depot ID match and were attached to the previous depot:")
                    st.table(unknown_attached)

                if unknown_unassigned:
                    st.error(
                        "Some pages had no Depot ID and no previous depot to attach to. "
                        "They were grouped under 'UNKNOWN'."
                    )
                    st.write("Pages grouped as UNKNOWN:", unknown_unassigned)

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

                st.success("Splitting complete! Download your ZIP below:")

                st.download_button(
                    label="⬇️ Download Call List ZIP",
                    data=zip_buffer,
                    file_name="call_lists_by_depot.zip",
                    mime="application/zip",
                )

            except Exception as e:
                st.error(f"❌ Error: {e}")


# --------- PAGE 2: Group List Splitter --------- #

elif page == "Group List Splitter":
    st.header("Group List Splitter")

    st.markdown(
        """
        Upload a **Group List PDF** and this tool will:

        1. Look for `Shipping Point    :  123V` on each page  
        2. If there is **no** `3 digits + V` next to Shipping Point on a page, that page is **ignored**  
        3. If a `XXXV` is found, that page is grouped under that shipping point  
        4. One PDF per Shipping Point is created, named:  
           - `123V_Group.pdf`, `140V_Group.pdf`, etc.  
        5. You then download all as a **ZIP**.
        """
    )

    group_file = st.file_uploader("Upload Group List PDF", type=["pdf"], key="group_list")

    if group_file:
        st.success(f"File uploaded: `{group_file.name}`")

        if st.button("🚀 Split Group List by Shipping Point"):
            try:
                group_file.seek(0)
                reader = PdfReader(group_file)
                num_pages = len(reader.pages)
                st.write(f"Detected **{num_pages}** pages.")

                # shipping_point -> PdfWriter
                sp_writers = {}
                ignored_pages = []  # pages with no valid 3-digits+V shipping point

                for page_index, page in enumerate(reader.pages):
                    page_num = page_index + 1
                    sp = extract_shipping_point(page)

                    if sp == "UNKNOWN":
                        ignored_pages.append(page_num)
                        st.write(f"Page {page_num}: no valid Shipping Point (ignored).")
                        continue  # skip this page entirely

                    if sp not in sp_writers:
                        sp_writers[sp] = PdfWriter()

                    sp_writers[sp].add_page(page)
                    st.write(f"Page {page_num}: Shipping Point `{sp}`")

                if not sp_writers:
                    st.error("No valid Shipping Point (3 digits + 'V') found on any page. Nothing to split.")
                    if ignored_pages:
                        st.write("Pages scanned but ignored:", ignored_pages)
                else:
                    st.write("### Shipping Points created:")
                    st.json(list(sp_writers.keys()))

                    if ignored_pages:
                        st.info("Some pages had no valid Shipping Point and were ignored:")
                        st.write(ignored_pages)

                    # Create ZIP in memory
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for sp, writer in sp_writers.items():
                            filename = shipping_point_to_filename(sp)
                            pdf_bytes = io.BytesIO()
                            writer.write(pdf_bytes)
                            pdf_bytes.seek(0)
                            zip_file.writestr(filename, pdf_bytes.read())

                    zip_buffer.seek(0)

                    st.success("Group List splitting complete! Download your ZIP below:")

                    st.download_button(
                        label="⬇️ Download Group List ZIP",
                        data=zip_buffer,
                        file_name="group_lists_by_shipping_point.zip",
                        mime="application/zip",
                    )

            except Exception as e:
                st.error(f"❌ Error: {e}")
