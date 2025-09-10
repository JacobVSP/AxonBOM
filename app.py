import streamlit as st
import pandas as pd
from pathlib import Path

# =========================
# Page setup & styling
# =========================
st.set_page_config(page_title="AXON BOM Generator (Web)", layout="wide")

# Left-aligned rows: [Label | Value | Spacer], 5px gap. Compact 140px controls.
st.markdown("""
<style>
.main .block-container { max-width: 1200px; padding-top: 10px; padding-bottom: 8px; }

/* Card */
.card { border: 1px solid #e6e6e6; border-radius: 10px; padding: 10px 12px; background: #fafafa; }

/* Keep columns very close but readable */
div[data-testid="stHorizontalBlock"] { gap: 5px !important; }
div[data-testid="column"] { padding-left: 0 !important; padding-right: 0 !important; }

/* Label style (left aligned) */
.axon-label { font-weight: 600; margin: 6px 0 2px 0; }

/* Number inputs: compact, LEFT aligned; fix width ~140px */
div[data-testid="stNumberInput"] label { display: none; }
div[data-testid="stNumberInput"] > div { width: 140px !important; }   /* input container */
div[data-testid="stNumberInput"] input {
  padding: 2px 6px; height: 30px; text-align: left;
}

/* Selects compact, ~140px wide */
div[data-baseweb="select"] { width: 140px !important; }
div[data-baseweb="select"] > div { min-height: 30px; }
div[data-baseweb="select"] > div > div { padding-top: 2px; padding-bottom: 2px; }

/* Slim instruction text */
.axon-instr { font-size: 0.9rem; line-height: 1.35; }

/* Tiny info icon right after labels */
.axon-info { cursor: help; font-weight: 700; margin-left: 6px; color: #666; }
.axon-info:hover { color: #000; }
</style>
""", unsafe_allow_html=True)

# =========================
# System limits
# =========================
ZONES_ONBOARD = 16
OUTPUTS_ONBOARD = 5
DOOR_MAX   = 56
OUTPUT_MAX = 128   # Doors + Sirens + Other
ZONE_MAX   = 256

# =========================
# Catalogue loading (Excel)
# =========================
def load_catalogue():
    """
    Loads Axon_Configurator_Catalog.xlsx and returns a dict {SKU: Name}.
    Fails closed: if a required SKU is missing from the sheet, we won't include it in the BOM.
    """
    # Try local file first (same folder as app)
    local = Path(__file__).parent / "Axon_Configurator_Catalog.xlsx"
    fallback = Path("/mnt/data/Axon_Configurator_Catalog.xlsx")  # for local testing
    xls_path = local if local.exists() else fallback

    df = pd.read_excel(xls_path, sheet_name="Catalog")
    df.columns = [str(c).strip() for c in df.columns]
    if "SKU" not in df.columns or "Name" not in df.columns:
        raise RuntimeError("Catalogue must have columns: 'SKU' and 'Name' on sheet 'Catalog'.")

    df = df[["SKU","Name"]].dropna().drop_duplicates(subset=["SKU"], keep="first")
    return dict(zip(df["SKU"].astype(str), df["Name"].astype(str)))

# Load once
try:
    NAME_MAP = load_catalogue()
except Exception as e:
    st.error(f"Failed to load catalogue Excel: {e}")
    NAME_MAP = {}  # hard fail closed

def get_name(sku: str) -> str:
    """Return official Name for SKU from the catalogue."""
    return NAME_MAP.get(sku, "")

# =========================
# SKUs used by the tool
# (UI labels will be clean names only; SKUs are for BOM & logic)
# =========================
SKU = dict(
    # Readers
    AXON_READER="AXON-ATS1180",
    AXON_KEYPAD_READER="AXON-ATS1181",
    HID_SEOS_SLIM="HID-20NKS-01",
    HID_SMART_SLIM="HID-20NKS-02",
    HID_SEOS_KP="HID-20KNKS-01",
    HID_SMART_KP="HID-20KNKS-02",

    # Keypads & comms
    ATS1125="AXON-ATS1125",
    ATS1140="AXON-ATS1140",
    MOD_4G="AXON-ATS7341",

    # Outputs
    ATS624="AXON-ATS624",
    ATS1810="AXON-ATS1810",
    ATS1811="AXON-ATS1811",

    # Zones (note: distribution logic below is conservative)
    ATS608="AXON-ATS608",
    ATS1201E="AXON-ATS1201E",
    ATS1202="AXON-ATS1202",
    ATS1211E="AXON-ATS1211E",

    # Power / accessories
    ATS1330="AXON-ATS1330",

    # Credentials
    AXON_ISO_10="AXON-ATS1455-10PACK",
    AXON_TAG_5="AXON-ATS1453-5PACK",
    HID_SEOS_ISO="HID-SEOS-ISO",
    HID_SEOS_TAG="HID-SEOS-KEYTAG",
)

# =========================
# Helpers
# =========================
def add_item(queue, sku, qty=1):
    """
    Add line to BOM only if SKU exists in the loaded catalogue.
    Ensures Names are 100% from Excel.
    """
    if qty <= 0:
        return
    name = get_name(sku)
    if not name:
        # Silently skip unknown SKUs to guarantee catalogue accuracy
        return
    for row in queue:
        if row[0] == sku:
            row[2] += qty
            return
    queue.append([sku, name, qty])

def validate_caps(doors, zones, outputs_total):
    errs = []
    if doors > DOOR_MAX: errs.append(f"Doors cannot exceed {DOOR_MAX}.")
    if outputs_total > OUTPUT_MAX: errs.append(f"Total Outputs (Doors + Sirens + Other) cannot exceed {OUTPUT_MAX}.")
    if zones > ZONE_MAX: errs.append(f"Zones cannot exceed {ZONE_MAX}.")
    if min(doors, zones, outputs_total) < 0: errs.append("Inputs must be non-negative integers.")
    return errs

# -------------------- Output expansion (conservative, matches available parts) --------------------
def expand_outputs(outputs_needed, queue):
    """
    Panel has 5 outputs onboard.
    Then: + ATS624 (+4), + ATS1810 (+4), then multiple ATS1811 (+8).
    """
    shortfall = max(0, outputs_needed - OUTPUTS_ONBOARD)
    if shortfall <= 0:
        return

    # ATS624 (+4)
    add_item(queue, SKU["ATS624"], 1)
    shortfall -= 4

    # ATS1810 (+4) if still needed
    if shortfall > 0:
        add_item(queue, SKU["ATS1810"], 1)
        shortfall -= 4

    # ATS1811 (+8) while needed
    while shortfall > 0:
        add_item(queue, SKU["ATS1811"], 1)
        shortfall -= 8

# -------------------- Zone expansion (conservative, simple) --------------------
def expand_zones(zones_needed, queue):
    """
    Panel has 16 onboard zones. Add expansions in +8 blocks using available parts.
    Order: ATS608 (plug-on +8) once, then ATS1211E (+8) / ATS1202 (+8) behind ATS1201E host as needed.
    This is intentionally conservative and does not over-prescribe topology.
    """
    remaining = max(0, zones_needed - ZONES_ONBOARD)
    if remaining <= 0:
        return

    # First, one ATS608 plug-on (+8)
    if remaining > 0:
        add_item(queue, SKU["ATS608"], 1)
        remaining -= 8

    # Then add DGP-based blocks of +8. We add a host (1201E) the first time we need DGP-based inputs.
    host_added = False
    while remaining > 0:
        if not host_added:
            add_item(queue, SKU["ATS1201E"], 1)
            host_added = True
        # Prefer 1211E (+8). If it's missing in catalogue, fall back to 1202 (+8).
        if get_name(SKU["ATS1211E"]):
            add_item(queue, SKU["ATS1211E"], 1)
        else:
            add_item(queue, SKU["ATS1202"], 1)
        remaining -= 8

# =========================
# Compact row helpers (Label | Value | Spacer)
# =========================
def row_number(label, key, minv=0, maxv=None, value=0, step=1, disabled=False, help_text=None, info_text=None):
    c1, c2, _ = st.columns([0.48, 0.16, 0.36])
    with c1:
        if info_text:
            st.markdown(f"<div class='axon-label'>{label}<span class='axon-info' title='{info_text}'>ⓘ</span></div>",
                        unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='axon-label'>{label}</div>", unsafe_allow_html=True)
    with c2:
        return st.number_input(
            label="", key=key, min_value=minv, max_value=maxv, value=value, step=step,
            disabled=disabled, help=help_text, label_visibility="collapsed"
        )

def row_select(label, key, options, index=0, help_text=None):
    c1, c2, _ = st.columns([0.48, 0.16, 0.36])
    with c1:
        st.markdown(f"<div class='axon-label'>{label}</div>", unsafe_allow_html=True)
    with c2:
        return st.selectbox(label="", key=key, options=options, index=index,
                            help=help_text, label_visibility="collapsed")

# =========================
# Layout
# =========================
left_wide, right_slim = st.columns([4, 1])

with left_wide:
    inputs_col, lift_col = st.columns([2, 1])

    with inputs_col:
        st.markdown("#### Inputs")
        st.markdown("<div class='card'>", unsafe_allow_html=True)

        # System
        st.markdown("**System**")
        doors = row_number("Doors", "doors", value=0, maxv=DOOR_MAX, help_text=f"Max {DOOR_MAX}")
        zones = row_number("Zones", "zones", value=0, maxv=ZONE_MAX, help_text=f"Max {ZONE_MAX}")

        # Outputs (Door Outputs mirrors Doors)
        row_number("Door Outputs", "door_outputs_display", value=int(doors), disabled=True)
        siren_outputs = row_number("Siren Outputs", "siren_outputs", value=0, help_text=f"Outputs total ≤ {OUTPUT_MAX}")
        other_outputs  = row_number("Other Outputs",  "other_outputs",  value=0, help_text=f"Outputs total ≤ {OUTPUT_MAX}")

        # Lift toggle (no CDC4 option shown at this stage, per instruction)
        lift_choice = row_select("Lift Control", "lift_choice", ["No", "Yes"], index=0)

        # Readers (clean labels — no SKUs in UI)
        st.markdown("---"); st.markdown("**Readers**")
        axon1180 = row_number("AXON Reader", "axon1180", value=0)
        axon1181 = row_number("AXON Keypad Reader", "axon1181", value=0)
        hid20_seos = row_number("HID Seos Reader", "hid_seos", value=0)
        hid20_smart = row_number("HID Smart Reader", "hid_smart", value=0)
        hid20_seos_kp = row_number("HID Seos Keypad Reader", "hid_seos_kp", value=0)
        hid20_smart_kp = row_number("HID Smart Keypad Reader", "hid_smart_kp", value=0)

        # Keypads & Options (ATS1125 tooltip restored)
        st.markdown("---"); st.markdown("**Keypads & Options**")
        extra1125 = row_number(
            "Additional ATS1125 LCD Keypad", "extra1125", value=0,
            info_text="1x ATS1125 Keypad is automatically included in the BOM, leave blank if no additional keypads are required"
        )
        touch1140 = row_number("ATS1140 Touchscreen Keypad", "touch1140", value=0)
        mod_4g = row_select("4G Module Required", "mod_4g", ["No", "Yes"], index=0)
        manual_1330 = row_number("AXON Power Distribution Board", "manual_1330", value=0)

        # Credentials
        st.markdown("---"); st.markdown("**Credentials**")
        cred_iso_pack   = row_number("AXON ISO Cards - 10 Pack", "cred_iso_pack", value=0)
        cred_tag_pack   = row_number("AXON Keytags - 5 Pack",  "cred_tag_pack", value=0)
        hid_seos_iso    = row_number("HID Seos ISO Cards",     "hid_seos_iso", value=0)
        hid_seos_keytag = row_number("HID Seos Keytags",       "hid_seos_keytag", value=0)

        st.markdown("</div>", unsafe_allow_html=True)

    with lift_col:
        if lift_choice == "Yes":
            st.markdown("#### Lift Control")
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            lifts  = row_number("How many Lifts?",  "lifts",  value=0)
            levels = row_number("How many Levels?", "levels", value=0)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            lifts, levels = 0, 0

with right_slim:
    st.markdown("#### Instructions")
    st.markdown("<div class='card axon-instr'>", unsafe_allow_html=True)
    st.markdown(
        f"- **Limits:** Doors ≤ {DOOR_MAX}, Outputs ≤ {OUTPUT_MAX}, Zones ≤ {ZONE_MAX}.\n"
        "- **Door Outputs** mirrors **Doors** automatically.\n"
        "- Set **Lift Control** to **Yes** to configure **Lifts/Levels**.\n"
        "- Click **Generate BOM** to build the parts list and totals.\n"
        "- Use **Download CSV** to export.\n"
        "- BOM Names and SKUs come **directly from your catalogue Excel**."
    )
    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# Actions
# =========================
act_cols = st.columns([1, 1, 6])
with act_cols[0]:
    generate = st.button("Generate BOM", type="primary")
with act_cols[1]:
    if st.button("Reset"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.experimental_rerun()

# =========================
# Build & Validate
# =========================
def build_bom(doors, zones, siren_outputs, other_outputs,
              readers, extra1125, touch1140, mod_4g, manual_1330,
              cred_iso_pack, cred_tag_pack, hid_seos_iso, hid_seos_keytag):
    outputs_total = int(doors) + int(siren_outputs) + int(other_outputs)
    errors = validate_caps(int(doors), int(zones), outputs_total)
    if errors:
        return None, errors

    q = []

    # Zones expansion
    expand_zones(int(zones), q)

    # Outputs expansion
    expand_outputs(outputs_total, q)

    # Readers
    add_item(q, SKU["AXON_READER"],       int(readers["axon1180"]))
    add_item(q, SKU["AXON_KEYPAD_READER"],int(readers["axon1181"]))
    add_item(q, SKU["HID_SEOS_SLIM"],     int(readers["hid20_seos"]))
    add_item(q, SKU["HID_SMART_SLIM"],    int(readers["hid20_smart"]))
    add_item(q, SKU["HID_SEOS_KP"],       int(readers["hid20_seos_kp"]))
    add_item(q, SKU["HID_SMART_KP"],      int(readers["hid20_smart_kp"]))

    # Keypads & Options
    # Always include 1x ATS1125 (required for setup), plus any additional entered
    include_1125 = 1 + int(extra1125)
    add_item(q, SKU["ATS1125"], include_1125)
    add_item(q, SKU["ATS1140"], int(touch1140))
    if mod_4g == "Yes":
        add_item(q, SKU["MOD_4G"], 1)

    # Credentials
    add_item(q, SKU["AXON_ISO_10"],   int(cred_iso_pack))
    add_item(q, SKU["AXON_TAG_5"],    int(cred_tag_pack))
    add_item(q, SKU["HID_SEOS_ISO"],  int(hid_seos_iso))
    add_item(q, SKU["HID_SEOS_TAG"],  int(hid_seos_keytag))

    # Manual PDB (Power Distribution Board)
    add_item(q, SKU["ATS1330"], int(manual_1330))

    # Summary (totals shown are the requested values)
    result = {
        "zones_total": int(zones),
        "outputs_total": outputs_total,
        "doors_total": int(doors),
        "rows": q
    }
    return result, None

# =========================
# Generate
# =========================
if generate:
    readers = {
        "axon1180":     st.session_state.get("axon1180", 0),
        "axon1181":     st.session_state.get("axon1181", 0),
        "hid20_seos":   st.session_state.get("hid_seos", 0),
        "hid20_smart":  st.session_state.get("hid_smart", 0),
        "hid20_seos_kp":st.session_state.get("hid_seos_kp", 0),
        "hid20_smart_kp":st.session_state.get("hid_smart_kp", 0),
    }

    result, errors = build_bom(
        doors=st.session_state.get("doors", 0),
        zones=st.session_state.get("zones", 0),
        siren_outputs=st.session_state.get("siren_outputs", 0),
        other_outputs=st.session_state.get("other_outputs", 0),
        readers=readers,
        extra1125=st.session_state.get("extra1125", 0),
        touch1140=st.session_state.get("touch1140", 0),
        mod_4g=st.session_state.get("mod_4g", "No"),
        manual_1330=st.session_state.get("manual_1330", 0),
        cred_iso_pack=st.session_state.get("cred_iso_pack", 0),
        cred_tag_pack=st.session_state.get("cred_tag_pack", 0),
        hid_seos_iso=st.session_state.get("hid_seos_iso", 0),
        hid_seos_keytag=st.session_state.get("hid_seos_keytag", 0),
    )

    if errors:
        for e in errors: st.error(e)
        st.stop()

    # ---- Summary strip ----
    st.markdown("#### Summary")
    s1, s2, s3 = st.columns([1, 1, 1])
    s1.metric("Zones Total", result["zones_total"])
    s2.metric("Outputs Total", result["outputs_total"])
    s3.metric("Doors Total", result["doors_total"])

    # ---- BOM ----
    st.markdown("#### BOM (SKU / Name / Qty)")
    df = pd.DataFrame(result["rows"], columns=["SKU", "Name", "Qty"]).sort_values(by=["SKU"])
    st.dataframe(df, use_container_width=True, hide_index=True, height=340)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", data=csv, file_name="AXON_BOM.csv", mime="text/csv")
else:
    st.info(
        f"System limits: Doors ≤ {DOOR_MAX}, Outputs ≤ {OUTPUT_MAX}, Zones ≤ {ZONE_MAX}. "
        "Door Outputs mirrors Doors."
    )
