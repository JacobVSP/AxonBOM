import streamlit as st
import pandas as pd

# =========================
# Page setup & styling
# =========================
st.set_page_config(page_title="AXON BOM Generator (Web)", layout="wide")

st.markdown("""
<style>
.main .block-container { max-width: 1200px; padding-top: 10px; padding-bottom: 8px; }
.axon-label { font-weight: 600; margin: 6px 0 2px 0; }
div[data-testid="stNumberInput"] label { display: none; }
div[data-testid="stNumberInput"] > div { width: 140px !important; }
div[data-testid="stNumberInput"] input { padding: 2px 6px; height: 30px; text-align: left; }
div[data-baseweb="select"] { width: 140px !important; }
div[data-baseweb="select"] > div { min-height: 30px; }
div[data-baseweb="select"] > div > div { padding-top: 2px; padding-bottom: 2px; }
.axon-info { cursor: help; font-weight: 700; margin-left: 6px; color: #666; }
.axon-info:hover { color: #000; }
</style>
""", unsafe_allow_html=True)

# =========================
# Instructions
# =========================
with st.expander("📖 Instructions", expanded=True):
    st.markdown("""
    **How to use the AXON BOM Generator:**

    1. **Core System Tab**  
       - Enter required **Doors, Zones, and Outputs**.  
       - Select **Reader types** and their quantities.  
       - Add **Keypads, 4G module, Power Distribution Boards, and Credentials**.  
       - The tool automatically calculates required expanders (CDC4, ATS modules).

    2. **Peripherals Tab** *(Coming Soon)*  
       - This will allow adding Locks, PIRs, Reeds, Sirens, etc., with real SKUs and quantities.

    3. **Generate BOM**  
       - Click **Generate BOM** to view the System Summary and BOM table.  
       - Use **Download CSV** to export the BOM (includes the system summary at the top).

    ---
    **Tips:**
    - Leave **Siren Outputs** as `0` if none are used (they can be repurposed as door outputs).  
    - **Lift Control** is marked *Coming Soon* (not yet available).  
    - Ensure reader quantities reflect actual device count; reader totals are independent of door count.
    """)

# =========================
# System limits
# =========================
ZONES_ONBOARD_PANEL = 16
OUTPUTS_ONBOARD_PANEL = 5
DOORS_ONBOARD_PANEL = 8
DOOR_MAX   = 56
OUTPUT_MAX = 128
ZONE_MAX   = 256
PANEL_1811_LIMIT = 4

# =========================
# Catalogue (SKU -> Name)
# =========================
NAME_MAP = {
    "AXON-256AU": "AXON 256 Access Control Panel",
    "AXON-CDC4-AU": "AXON Intelligent 4 Door / Lift Controller",
    "AXON-ATS1180": "AXON Secure Mifare Reader",
    "AXON-ATS1181": "AXON Secure Mifare Reader with Keypad",
    "HID-20NKS-01": "HID Signo 20 Slim Reader, Seos Profile",
    "HID-20NKS-02": "HID Signo 20 Slim Reader, Smart Profile",
    "HID-20KNKS-01": "HID Signo 20 Keypad Reader, Seos Profile",
    "HID-20KNKS-02": "HID Signo 20 Keypad Reader, Smart Profile",
    "AXON-ATS1125": "AXON LCD Keypad with Mifare Reader",
    "AXON-ATS1140": "AXON Touchscreen Keypad with Mifare Reader",
    "AXON-ATS7341": "AXON 4G Module with UltraSync SIM",
    "AXON-ATS608": "Axon Plug-on Input Expander",
    "AXON-ATS624": "Axon Plug-on 4 Way Output Expander",
    "AXON-ATS1810": "Axon 4 Way Relay Card",
    "AXON-ATS1811": "Axon 8 Way Relay Card",
    "AXON-ATS1201E": "AXON 32 Input/Output DGP Expander",
    "AXON-ATS1202": "AXON 8 Input Expander",
    "AXON-ATS1211E": "8 Input/Output DGP Expander + Metal Housing",
    "AXON-ATS1330": "Axon Power Distribution Board",
    "AXON-ATS1455-10PACK": "AXON ISO Card, DESFire EV2/3 2K, 10 Pack",
    "AXON-ATS1453-5PACK": "AXON Tear Keytag, DESFire EV2/3 2K, 5 Pack",
    "HID-SEOS-ISO": "HID Seos ISO Cards",
    "HID-SEOS-KEYTAG": "HID Seos Keytags",
}

def get_name(sku):
    return NAME_MAP.get(sku, sku)

# =========================
# SKUs
# =========================
SKU = dict(
    PANEL="AXON-256AU",
    CDC4="AXON-CDC4-AU",
    AXON_READER="AXON-ATS1180",
    AXON_KEYPAD_READER="AXON-ATS1181",
    HID_SEOS_SLIM="HID-20NKS-01",
    HID_SMART_SLIM="HID-20NKS-02",
    HID_SEOS_KP="HID-20KNKS-01",
    HID_SMART_KP="HID-20KNKS-02",
    ATS1125="AXON-ATS1125",
    ATS1140="AXON-ATS1140",
    MOD_4G="AXON-ATS7341",
    ATS608="AXON-ATS608",
    ATS624="AXON-ATS624",
    ATS1810="AXON-ATS1810",
    ATS1811="AXON-ATS1811",
    ATS1201E="AXON-ATS1201E",
    ATS1202="AXON-ATS1202",
    ATS1211E="AXON-ATS1211E",
    ATS1330="AXON-ATS1330",
    AXON_ISO_10="AXON-ATS1455-10PACK",
    AXON_TAG_5="AXON-ATS1453-5PACK",
    HID_SEOS_ISO="HID-SEOS-ISO",
    HID_SEOS_TAG="HID-SEOS-KEYTAG",
)

# =========================
# Helpers
# =========================
def add_bom_line(queue, notes, sku, qty, reason):
    if qty <= 0:
        return
    name = get_name(sku)
    for row in queue:
        if row[0] == sku:
            row[2] += qty
            notes[sku].append(reason)
            return
    queue.append([sku, name, qty])
    notes[sku] = [reason]

def validate_caps(doors, zones, outputs_total):
    errs = []
    if doors > DOOR_MAX: errs.append(f"Doors cannot exceed {DOOR_MAX}.")
    if outputs_total > OUTPUT_MAX: errs.append(f"Outputs cannot exceed {OUTPUT_MAX}.")
    if zones > ZONE_MAX: errs.append(f"Zones cannot exceed {ZONE_MAX}.")
    return errs

# Panel expansions
def expand_zones_on_panel(zones_needed, q, notes):
    remaining = max(0, zones_needed - ZONES_ONBOARD_PANEL)
    if remaining > 0:
        add_bom_line(q, notes, SKU["ATS608"], 1, "Added ATS608 plug-on to extend panel from 16 → 24 zones")
        remaining -= 8
    return max(0, remaining)

def expand_outputs_on_panel(outputs_needed, outputs_available, q, notes):
    remaining = max(0, outputs_needed - outputs_available)
    if remaining <= 0:
        return 0
    add_bom_line(q, notes, SKU["ATS624"], 1, "Added ATS624 plug-on for +4 outputs")
    remaining -= 4
    if remaining > 0:
        add_bom_line(q, notes, SKU["ATS1810"], 1, "Added ATS1810 for +4 outputs on panel")
        remaining -= 4
    count_1811 = 0
    while remaining > 0 and count_1811 < PANEL_1811_LIMIT:
        add_bom_line(q, notes, SKU["ATS1811"], 1, "Added ATS1811 for +8 outputs on panel")
        remaining -= 8
        count_1811 += 1
    return max(0, remaining)

# DGP expansions
def place_zones_on_dgp(remaining, q, notes):
    while remaining > 0:
        if remaining <= 8:
            add_bom_line(q, notes, SKU["ATS1211E"], 1, "Added ATS1211E (+8 zones / +8 outputs) for small zone shortfall")
            remaining -= 8
        else:
            add_bom_line(q, notes, SKU["ATS1201E"], 1, "Added ATS1201E (8 zones onboard, expandable to 32)")
            remaining -= 8
            count_1202 = 0
            while remaining > 0 and count_1202 < 3:
                add_bom_line(q, notes, SKU["ATS1202"], 1, "Added ATS1202 (+8 zones) to extend ATS1201E")
                remaining -= 8
                count_1202 += 1
    return remaining

def place_outputs_on_dgp(remaining, q, notes):
    while remaining > 0:
        if remaining <= 8:
            add_bom_line(q, notes, SKU["ATS1211E"], 1, "Added ATS1211E (+8 zones / +8 outputs) for small output shortfall")
            remaining -= 8
        else:
            add_bom_line(q, notes, SKU["ATS1201E"], 1, "Added ATS1201E for large output expansion (up to 32 outputs)")
            cap = 32
            used = 0
            while remaining > 0 and used < cap:
                if remaining >= 8:
                    add_bom_line(q, notes, SKU["ATS1811"], 1, "Added ATS1811 (+8 outputs) to extend ATS1201E")
                    remaining -= 8; used += 8
                elif remaining >= 4:
                    add_bom_line(q, notes, SKU["ATS1810"], 1, "Added ATS1810 (+4 outputs) to extend ATS1201E")
                    remaining -= 4; used += 4
                else:
                    break
    return remaining

# =========================
# Build BOM
# =========================
def build_bom(doors, zones, siren_outputs, other_outputs,
              readers, extra1125, touch1140, mod_4g, manual_1330,
              cred_iso_pack, cred_tag_pack, hid_seos_iso, hid_seos_keytag):
    outputs_total = doors + siren_outputs + other_outputs
    errors = validate_caps(doors, zones, outputs_total)
    if errors:
        return None, errors

    q, notes = [], {}

    # Always include the base panel
    add_bom_line(q, notes, SKU["PANEL"], 1, "Base AXON-256AU Access Control Panel (8 doors, 16 zones, 5 outputs onboard)")

    # Add CDC4s for doors beyond 8 onboard
    cdc4_count = 0
    if doors > DOORS_ONBOARD_PANEL:
        cdc4_count = (doors - DOORS_ONBOARD_PANEL + 3) // 4
        add_bom_line(q, notes, SKU["CDC4"], cdc4_count, f"Added {cdc4_count}x CDC4 controllers to support {doors} doors (8 onboard + 4 per CDC4)")

    # Zones
    remaining_zones = expand_zones_on_panel(zones, q, notes)
    place_zones_on_dgp(remaining_zones, q, notes)

    # Outputs (include CDC4 outputs in baseline)
    outputs_available = OUTPUTS_ONBOARD_PANEL + (cdc4_count * 4)
    remaining_outputs = expand_outputs_on_panel(outputs_total, outputs_available, q, notes)
    place_outputs_on_dgp(remaining_outputs, q, notes)

    # Readers (only what the user selected)
    add_bom_line(q, notes, SKU["AXON_READER"], readers["axon1180"], "Added AXON Readers")
    add_bom_line(q, notes, SKU["AXON_KEYPAD_READER"], readers["axon1181"], "Added AXON Keypad Readers")
    add_bom_line(q, notes, SKU["HID_SEOS_SLIM"], readers["hid20_seos"], "Added HID Seos Slim Readers")
    add_bom_line(q, notes, SKU["HID_SMART_SLIM"], readers["hid20_smart"], "Added HID Smart Slim Readers")
    add_bom_line(q, notes, SKU["HID_SEOS_KP"], readers["hid20_seos_kp"], "Added HID Seos Keypad Readers")
    add_bom_line(q, notes, SKU["HID_SMART_KP"], readers["hid20_smart_kp"], "Added HID Smart Keypad Readers")

    # Keypads
    add_bom_line(q, notes, SKU["ATS1125"], 1 + extra1125, "Required ATS1125 Keypad (1 included + extras)")
    add_bom_line(q, notes, SKU["ATS1140"], touch1140, "Added ATS1140 Touchscreen Keypads")
    if mod_4g == "Yes":
        add_bom_line(q, notes, SKU["MOD_4G"], 1, "Added 4G Module")

    # Credentials
    add_bom_line(q, notes, SKU["AXON_ISO_10"], cred_iso_pack, "Added ISO card packs")
    add_bom_line(q, notes, SKU["AXON_TAG_5"], cred_tag_pack, "Added Keytag packs")
    add_bom_line(q, notes, SKU["HID_SEOS_ISO"], hid_seos_iso, "Added HID Seos ISO Cards")
    add_bom_line(q, notes, SKU["HID_SEOS_TAG"], hid_seos_keytag, "Added HID Seos Keytags")

    # PDB
    add_bom_line(q, notes, SKU["ATS1330"], manual_1330, "Added Power Distribution Boards")

    # Reader total is based on selections, not doors
    readers_total = sum(readers.values())

    result = {
        "doors_total": doors,
        "zones_total": zones,
        "outputs_total": outputs_total,
        "readers_total": readers_total,
        "rows": q,
        "notes": notes
    }
    return result, None

# =========================
# Streamlit UI helper rows
# =========================
def row_number(label, key, value=0, minv=0, maxv=None, disabled=False, info_text=None):
    c1, c2, _ = st.columns([0.48, 0.16, 0.36])
    with c1:
        if info_text:
            st.markdown(
                f"<div class='axon-label'>{label}<span class='axon-info' title='{info_text}'>ⓘ</span></div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(f"<div class='axon-label'>{label}</div>", unsafe_allow_html=True)
    with c2:
        return st.number_input("", key=key, value=value, min_value=minv, max_value=maxv,
                               disabled=disabled, label_visibility="collapsed")

def row_select(label, key, options, index=0):
    c1, c2, _ = st.columns([0.48, 0.16, 0.36])
    with c1:
        st.markdown(f"<div class='axon-label'>{label}</div>", unsafe_allow_html=True)
    with c2:
        return st.selectbox("", options, index=index, key=key, label_visibility="collapsed")

# =========================
# Layout (Tabbed)
# =========================
tab_core, tab_peripherals = st.tabs(["Core System", "Peripherals"])

with tab_core:
    st.markdown("#### System")
    doors = row_number("Doors", "doors", 0, maxv=DOOR_MAX)
    zones = row_number("Zones", "zones", 0, maxv=ZONE_MAX)
    st.session_state["door_outputs_display"] = int(doors)
    row_number("Door Outputs", "door_outputs_display", st.session_state["door_outputs_display"], disabled=True)
    siren_outputs = row_number(
        "Siren Outputs", "siren_outputs", 0,
        info_text="If there are no sirens being used, leave at 0. Siren outputs can also be repurposed as door outputs."
    )
    other_outputs = row_number("Other Outputs", "other_outputs", 0)

    # Lift Control – Coming Soon (plain text, no dropdown)
    c1, c2, _ = st.columns([0.48, 0.16, 0.36])
    with c1:
        st.markdown("<div class='axon-label'>Lift Control</div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<span style='color: grey;'>Coming Soon</span>", unsafe_allow_html=True)

    st.markdown("---"); st.markdown("#### Readers")
    axon1180 = row_number("AXON Reader", "axon1180", 0)
    axon1181 = row_number("AXON Keypad Reader", "axon1181", 0)
    hid20_seos = row_number("HID Seos Reader", "hid20_seos", 0)
    hid20_smart = row_number("HID Smart Reader", "hid_smart", 0)
    hid20_seos_kp = row_number("HID Seos Keypad Reader", "hid_seos_kp", 0)
    hid20_smart_kp = row_number("HID Smart Keypad Reader", "hid_smart_kp", 0)

    st.markdown("---"); st.markdown("#### Keypads & Options")
    extra1125 = row_number(
        "Additional ATS1125 LCD Keypad", "extra1125", 0,
        info_text="1x ATS1125 Keypad is automatically included in the BOM, leave blank if no additional keypads are required"
    )
    touch1140 = row_number("ATS1140 Touchscreen Keypad", "touch1140", 0)
    mod_4g = row_select("4G Module Required", "mod_4g", ["No", "Yes"], 0)
    manual_1330 = row_number("AXON Power Distribution Board", "manual_1330", 0)

    st.markdown("---"); st.markdown("#### Credentials")
    cred_iso_pack = row_number("AXON ISO Cards - 10 Pack", "cred_iso_pack", 0)
    cred_tag_pack = row_number("AXON Keytags - 5 Pack", "cred_tag_pack", 0)
    hid_seos_iso = row_number("HID Seos ISO Cards", "hid_seos_iso", 0)
    hid_seos_keytag = row_number("HID Seos Keytags", "hid_seos_keytag", 0)

with tab_peripherals:
    st.markdown("#### Peripherals (Locks, PIRs, Reeds, Sirens, etc.)")
    st.info("Coming Soon — this tab will let you add peripherals (with real SKUs, names, quantities, and notes) that will be included in the BOM and CSV.")

generate = st.button("Generate BOM", type="primary")

# =========================
# Generate
# =========================
if generate:
    readers = {
        "axon1180": axon1180,
        "axon1181": axon1181,
        "hid20_seos": hid20_seos,
        "hid20_smart": hid20_smart,
        "hid20_seos_kp": hid20_seos_kp,
        "hid20_smart_kp": hid20_smart_kp
    }

    result, errors = build_bom(
        int(doors), int(zones), int(siren_outputs), int(other_outputs),
        readers, int(extra1125), int(touch1140), mod_4g,
        int(manual_1330), int(cred_iso_pack), int(cred_tag_pack),
        int(hid_seos_iso), int(hid_seos_keytag)
    )

    if errors:
        [st.error(e) for e in errors]
    else:
        # ===== UI summary =====
        st.markdown("#### System Summary")
        s1, s2, s3, s4 = st.columns([1, 1, 1, 1])
        s1.metric("Doors", result["doors_total"])
        s2.metric("Zones", result["zones_total"])
        s3.metric("Outputs", result["outputs_total"])
        s4.metric("Readers", result["readers_total"])

        st.markdown("#### BOM (SKU / Name / Qty / Notes)")
        bom_with_notes = []
        for sku, _, qty in result["rows"]:
            joined = "; ".join([n for n in result["notes"].get(sku, []) if n])
            bom_with_notes.append([sku, get_name(sku), qty, joined])

        bom_df = pd.DataFrame(bom_with_notes, columns=["SKU", "Name", "Qty", "Connection Notes"])
        st.dataframe(bom_df, use_container_width=True, hide_index=True, height=360)

        # ===== CSV export with System Summary =====
        summary = [
            ["System Summary", "", "", ""],
            ["Doors Supported", result["doors_total"], "", ""],
            ["Zones Supported", result["zones_total"], "", ""],
            ["Outputs Supported", result["outputs_total"], "", ""],
            ["Readers Supported", result["readers_total"], "", ""],
            ["", "", "", ""],
        ]
        summary_df = pd.DataFrame(summary, columns=["SKU", "Name", "Qty", "Connection Notes"])
        export_df = pd.concat([summary_df, bom_df], ignore_index=True)
        csv = export_df.to_csv(index=False).encode("utf-8")

        st.download_button("Download CSV", data=csv, file_name="AXON_BOM.csv", mime="text/csv")
