import streamlit as st
import pandas as pd

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
ZONES_ONBOARD_PANEL = 16
OUTPUTS_ONBOARD_PANEL = 5
DOOR_MAX   = 56
OUTPUT_MAX = 128   # Doors + Sirens + Other
ZONE_MAX   = 256
PANEL_1811_LIMIT = 4  # max number of ATS1811 on panel

# =========================
# Embedded catalogue (SKU -> Name)
# =========================
NAME_MAP = {
    # Panel / Lift
    "AXON-256AU": "AXON 256 Access Control Panel",
    "AXON-CDC4-AU": "AXON Intelligent 4 Door / Lift Controller",

    # Readers
    "AXON-ATS1180": "AXON Secure Mifare Reader",
    "AXON-ATS1181": "AXON Secure Mifare Reader with Keypad",
    "HID-20NKS-01": "HID Signo 20 Slim Reader, Seos Profile",
    "HID-20NKS-02": "HID Signo 20 Slim Reader, Smart Profile",
    "HID-20KNKS-01": "HID Signo 20 Keypad Reader, Seos Profile",
    "HID-20KNKS-02": "HID Signo 20 Keypad Reader, Smart Profile",

    # Keypads & comms
    "AXON-ATS1125": "AXON LCD Keypad with Mifare Reader",
    "AXON-ATS1140": "AXON Touchscreen Keypad with Mifare Reader",
    "AXON-ATS7341": "AXON 4G Module with UltraSync SIM",

    # Zone & output expansion (panel/DGP)
    "AXON-ATS608": "Axon Plug-on Input Expander",
    "AXON-ATS624": "Axon Plug-on 4 Way Output Expander",
    "AXON-ATS1810": "Axon 4 Way Relay Card",
    "AXON-ATS1811": "Axon 8 Way Relay Card",

    # DGP path (corrected)
    "AXON-ATS1201E": "AXON 32 Input/Output DGP Expander",   # 8 zones onboard; up to 32 I/O via 1202/1810/1811
    "AXON-ATS1202": "AXON 8 Input Expander",
    "AXON-ATS1211E": "8 Input/Output DGP Expander + Metal Housing",

    # Power / accessories
    "AXON-ATS1330": "Axon Power Distribution Board",

    # Credentials
    "AXON-ATS1455-10PACK": "AXON ISO Card, DESFire EV2/3 2K, 10 Pack",
    "AXON-ATS1453-5PACK": "AXON Tear Keytag, DESFire EV2/3 2K, 5 Pack",
    "HID-SEOS-ISO": "HID Seos ISO Cards",
    "HID-SEOS-KEYTAG": "HID Seos Keytags",
}

def get_name(sku: str) -> str:
    return NAME_MAP.get(sku, sku)

# SKUs referenced by the tool (UI shows human names; SKUs used for BOM)
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

    # Panel plug-ons
    ATS608="AXON-ATS608",   # +8 zones (panel)
    ATS624="AXON-ATS624",   # +4 outputs (panel)
    ATS1810="AXON-ATS1810", # +4 outputs (panel or DGP)
    ATS1811="AXON-ATS1811", # +8 outputs (panel or DGP)

    # DGP family
    ATS1201E="AXON-ATS1201E",   # 8 zones onboard; up to 32 I/O
    ATS1202="AXON-ATS1202",     # +8 zones per module on DGP
    ATS1211E="AXON-ATS1211E",   # (not used directly here; 1202/1810/1811 handle adds)

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
def add_bom_line(queue, sku, qty=1):
    if qty <= 0:
        return
    name = get_name(sku)
    # merge lines if SKU already present
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

# -------------------- Panel expansions --------------------
def expand_outputs_on_panel(outputs_needed, queue):
    """
    Panel has 5 outputs onboard.
    Then: ATS624 (+4), ATS1810 (+4), then up to PANEL_1811_LIMIT × ATS1811 (+8 each).
    Returns the remaining shortfall after panel expansions (>= 0).
    """
    remaining = max(0, outputs_needed - OUTPUTS_ONBOARD_PANEL)
    if remaining <= 0:
        return 0

    # ATS624 (+4)
    add_bom_line(queue, SKU["ATS624"], 1)
    remaining -= 4

    # ATS1810 (+4)
    if remaining > 0:
        add_bom_line(queue, SKU["ATS1810"], 1)
        remaining -= 4

    # ATS1811 (+8) up to limit
    count_1811 = 0
    while remaining > 0 and count_1811 < PANEL_1811_LIMIT:
        add_bom_line(queue, SKU["ATS1811"], 1)
        remaining -= 8
        count_1811 += 1

    return max(0, remaining)

def expand_zones_on_panel(zones_needed, queue):
    """
    Panel has 16 zones onboard.
    Add ATS608 (+8) once if zones exceed 16.
    Returns remaining shortfall after panel-side zones.
    """
    remaining = max(0, zones_needed - ZONES_ONBOARD_PANEL)
    if remaining <= 0:
        return 0
    add_bom_line(queue, SKU["ATS608"], 1)
    remaining -= 8
    return max(0, remaining)

# -------------------- DGP expansions (correct 1201E behavior) --------------------
def ensure_host(hosts, queue):
    """
    Ensure there is a DGP host with free I/O.
    A new ATS1201E host starts with 8 onboard zones already consuming I/O.
    """
    if hosts and hosts[-1]["io_used"] < 32:
        return hosts[-1]
    h = {"sku": SKU["ATS1201E"], "io_used": 8, "zones_added": 8, "outs_added": 0, "mods": []}
    hosts.append(h)
    add_bom_line(queue, SKU["ATS1201E"], 1)
    return h

def place_zones_on_dgp(remaining_zones, hosts, queue):
    """
    Use ATS1202 (+8 zones) modules on DGP hosts until zone requirement is covered.
    Each host has 32 total I/O slots (including its onboard 8 zones).
    """
    while remaining_zones > 0:
        h = ensure_host(hosts, queue)
        space = 32 - h["io_used"]
        if space < 8:
            # start a new host
            h = ensure_host(hosts, queue)
            space = 32 - h["io_used"]
            if space < 8:
                break
        add_bom_line(queue, SKU["ATS1202"], 1)
        h["io_used"] += 8
        h["zones_added"] += 8
        h["mods"].append(SKU["ATS1202"])
        remaining_zones -= 8

def place_outputs_on_dgp(remaining_outputs, hosts, queue):
    """
    Put residual outputs on existing/new DGP hosts (1811 preferred, then 1810),
    respecting the 32 I/O cap per host.
    """
    while remaining_outputs > 0:
        # find a host with room; otherwise create one
        target = None
        for h in hosts:
            if h["io_used"] < 32:
                target = h
                break
        if target is None:
            target = ensure_host(hosts, queue)

        space = 32 - target["io_used"]

        # try an 1811 (+8 outputs)
        if remaining_outputs >= 8 and space >= 8:
            add_bom_line(queue, SKU["ATS1811"], 1)
            target["io_used"] += 8
            target["outs_added"] += 8
            target["mods"].append(SKU["ATS1811"])
            remaining_outputs -= 8
            continue

        # else try an 1810 (+4)
        if remaining_outputs >= 4 and space >= 4:
            add_bom_line(queue, SKU["ATS1810"], 1)
            target["io_used"] += 4
            target["outs_added"] += 4
            target["mods"].append(SKU["ATS1810"])
            remaining_outputs -= 4
            continue

        # no space here; add another host
        target = ensure_host(hosts, queue)

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

        # Mirror Door Outputs live into a disabled control
        st.session_state["door_outputs_display"] = int(doors)
        row_number("Door Outputs", "door_outputs_display", value=st.session_state["door_outputs_display"], disabled=True)
        siren_outputs = row_number("Siren Outputs", "siren_outputs", value=0, help_text=f"Outputs total ≤ {OUTPUT_MAX}")
        other_outputs  = row_number("Other Outputs",  "other_outputs",  value=0, help_text=f"Outputs total ≤ {OUTPUT_MAX}")

        # Lift toggle (no CDC4 option shown at this stage)
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
        "- BOM Names and SKUs are embedded from your catalogue."
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
# Build & Validate (correct 1201E behavior)
# =========================
def build_bom(doors, zones, siren_outputs, other_outputs,
              readers, extra1125, touch1140, mod_4g, manual_1330,
              cred_iso_pack, cred_tag_pack, hid_seos_iso, hid_seos_keytag):
    outputs_total = int(doors) + int(siren_outputs) + int(other_outputs)
    errors = validate_caps(int(doors), int(zones), outputs_total)
    if errors:
        return None, errors

    q = []

    # ---- ZONES ----
    # Panel (16) + ATS608 (+8 once) if needed
    zones_remaining_after_panel = expand_zones_on_panel(int(zones), q)

    # If zones still remain, add DGP hosts and ATS1202 modules (up to 32 I/O per host)
    dgp_hosts = []
    place_zones_on_dgp(zones_remaining_after_panel, dgp_hosts, q)

    # ---- OUTPUTS ----
    # Panel outputs first (5 onboard, then 624, 1810, up to 4x 1811)
    remaining_outputs_after_panel = expand_outputs_on_panel(outputs_total, q)

    # Any residual outputs go onto DGPs (1811 preferred, then 1810), respecting 32 I/O per host
    place_outputs_on_dgp(remaining_outputs_after_panel, dgp_hosts, q)

    # ---- READERS / KEYPADS / CREDENTIALS / OTHER ----
    # Readers
    add_bom_line(q, SKU["AXON_READER"],        int(readers["axon1180"]))
    add_bom_line(q, SKU["AXON_KEYPAD_READER"], int(readers["axon1181"]))
    add_bom_line(q, SKU["HID_SEOS_SLIM"],      int(readers["hid20_seos"]))
    add_bom_line(q, SKU["HID_SMART_SLIM"],     int(readers["hid20_smart"]))
    add_bom_line(q, SKU["HID_SEOS_KP"],        int(readers["hid20_seos_kp"]))
    add_bom_line(q, SKU["HID_SMART_KP"],       int(readers["hid20_smart_kp"]))

    # Keypads & Options
    add_bom_line(q, SKU["ATS1125"], 1 + int(extra1125))  # 1 included + extras
    add_bom_line(q, SKU["ATS1140"], int(touch1140))
    if mod_4g == "Yes":
        add_bom_line(q, SKU["MOD_4G"], 1)

    # Credentials
    add_bom_line(q, SKU["AXON_ISO_10"],  int(cred_iso_pack))
    add_bom_line(q, SKU["AXON_TAG_5"],   int(cred_tag_pack))
    add_bom_line(q, SKU["HID_SEOS_ISO"], int(hid_seos_iso))
    add_bom_line(q, SKU["HID_SEOS_TAG"], int(hid_seos_keytag))

    # Manual PDB
    add_bom_line(q, SKU["ATS1330"], int(manual_1330))

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
