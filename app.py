import streamlit as st
import pandas as pd

# -------------------- Page & style --------------------
st.set_page_config(page_title="AXON BOM Generator (Web)", layout="wide")

# Compact, aligned UI: tighten column gaps, collapse input labels, reduce paddings
st.markdown("""
<style>
/* Page width + gentle padding */
.main .block-container { max-width: 1200px; padding-top: 10px; padding-bottom: 8px; }

/* Generic card */
.card {
  border: 1px solid #e6e6e6; border-radius: 10px;
  padding: 10px 12px; background: #fafafa;
}

/* Tighten default gap between Streamlit columns */
div[data-testid="column"] { padding-left: 6px !important; padding-right: 6px !important; }

/* Align label & input on the same visual baseline */
.axon-label { font-weight: 600; margin: 4px 0 0 0; line-height: 1.15; }

/* Make right-hand input column narrow so field sits close to label */
.axon-row { margin: 0; padding: 0; }
.axon-row .left { }
.axon-row .right { }

/* Shrink number input visual padding and collapse its inner label */
div[data-testid="stNumberInput"] label { display: none; }  /* hide built-in label */
div[data-testid="stNumberInput"] input {
  padding: 2px 6px; height: 30px;
  text-align: right;
}

/* Selectbox tidy */
div[data-baseweb="select"] > div { min-height: 30px; }
div[data-baseweb="select"] > div > div { padding-top: 2px; padding-bottom: 2px; }

/* Slim instruction text */
.axon-instr { font-size: 0.9rem; line-height: 1.35; }
</style>
""", unsafe_allow_html=True)

# -------------------- Constants --------------------
ZONES_ONBOARD = 16
OUTPUTS_ONBOARD = 5
ZONE_MAX = 256  # AXON-256AU panel capacity

NAME_MAP = {
    "AXON-ATS1201E": "AXON DGP Host (32 Zones max / 16 Outputs max)",
    "AXON-ATS1801":  "AXON Input Expander (+8 Zones on DGP)",
    "AXON-ATS1810":  "AXON Output Expander (+4 Outputs on DGP / on ATS624)",
    "AXON-ATS1811":  "AXON Output Expander (+8 Outputs on Panel or DGP)",
    "AXON-ATS624":   "AXON Panel Output Expander (+4 Outputs on Panel)",
    "AXON-ATS1125":  "AXON LCD Keypad",
    "AXON-ATS1140":  "AXON Touchscreen Keypad",
    "AXON-ATS7341":  "AXON 4G Module",
    "AXON-ATS1455-10Pack": "AXON ISO Cards - 10 Pack",
    "AXON-ATS1453-5Pack":  "AXON Keytags - 5 Pack",
    "AXON-AXON1180": "AXON AXON1180 Reader",
    "AXON-AXON1181": "AXON AXON1181 Reader",
    "HID-20-SEOS":   "HID SEOS Reader",
    "HID-20-SMART":  "HID Smart Reader",
    "HID-20-SEOS-KP":"HID SEOS Reader with Keypad",
    "HID-20-SMART-KP":"HID Smart Reader with Keypad",
    "AXON-ATS1330":  "AXON BUS Distributor",
}

DGP_ZONE_CAP = 32
DGP_OUTPUT_CAP = {"AXON-ATS1201E": 16}

# -------------------- Helpers --------------------
def add_item(q, sku, qty=1):
    if qty <= 0: return
    name = NAME_MAP.get(sku, sku)
    for row in q:
        if row[0] == sku:
            row[2] += qty
            return
    q.append([sku, name, qty])

def distribute_zones_to_panel_and_dgps(zones_needed, notes):
    panel_zones = ZONES_ONBOARD
    rs485_devices = 0
    cdc4_count = 0
    remaining = max(0, zones_needed - panel_zones)

    panel_1811 = 0
    while remaining > 0 and panel_1811 < 4:
        panel_zones += 8
        panel_1811 += 1
        remaining -= 8
        add_item(notes["queue"], "AXON-ATS1811", 1)
        rs485_devices += 1
        notes["panel_1811"] += 1

    while remaining > 0:
        add_item(notes["queue"], "AXON-ATS1201E", 1)
        rs485_devices += 1
        take = min(remaining, DGP_ZONE_CAP)
        remaining -= take
        extra = max(0, take - ZONES_ONBOARD)
        while extra > 0:
            add_item(notes["queue"], "AXON-ATS1801", 1)
            rs485_devices += 1
            notes["dgp_1801"] += 1
            extra -= 8

    return panel_zones, rs485_devices, cdc4_count

def expand_outputs_on_panel(outputs_needed, notes):
    """
    Panel-side expansion:
    5 onboard → + ATS624 (+4) → + ATS1810 on ATS624 (+4) → then up to 4× ATS1811 (+8 each)
    """
    added = 0
    rs485 = 0
    shortfall = max(0, outputs_needed - OUTPUTS_ONBOARD)
    if shortfall <= 0:
        return added, rs485

    add_item(notes["queue"], "AXON-ATS624", 1)
    shortfall -= 4
    added += 4

    if shortfall > 0:
        add_item(notes["queue"], "AXON-ATS1810", 1)
        shortfall -= 4
        added += 4
        rs485 += 1
        notes["panel_1810"] += 1

    while shortfall > 0 and notes["panel_1811"] < 4:
        add_item(notes["queue"], "AXON-ATS1811", 1)
        shortfall -= 8
        added += 8
        rs485 += 1
        notes["panel_1811"] += 1

    return added, rs485

def place_remaining_outputs_on_dgp(shortfall, notes):
    """Put remaining outputs on DGP 1201E using 1811 where possible, else 1810."""
    if shortfall <= 0: return 0, 0
    rs485 = 0; added = 0; hosts = []; q = notes["queue"]

    def ensure_host():
        for h in hosts:
            if h["remaining_out"] > 0: return h
        add_item(q, "AXON-ATS1201E", 1)
        notes["dgp_added_for_outputs"] = True
        new_h = {"sku": "AXON-ATS1201E", "remaining_out": DGP_OUTPUT_CAP["AXON-ATS1201E"]}
        hosts.append(new_h); return new_h

    while shortfall > 0:
        h = ensure_host()
        if shortfall == 4 and h["remaining_out"] >= 4:
            add_item(q, "AXON-ATS1810", 1); notes["dgp_1810"] += 1
            shortfall -= 4; added += 4; h["remaining_out"] -= 4; continue
        if h["remaining_out"] >= 8 and shortfall >= 8:
            add_item(q, "AXON-ATS1811", 1); notes["dgp_1811"] += 1
            shortfall -= 8; added += 8; h["remaining_out"] -= 8; continue
        if h["remaining_out"] >= 4:
            add_item(q, "AXON-ATS1810", 1); notes["dgp_1810"] += 1
            shortfall -= 4; added += 4; h["remaining_out"] -= 4; continue
        hosts.append({"sku": "AXON-ATS1201E", "remaining_out": DGP_OUTPUT_CAP["AXON-ATS1201E"]})
        add_item(q, "AXON-ATS1201E", 1); notes["dgp_added_for_outputs"] = True

    rs485 = sum(1 for s,_,_ in q if s in ("AXON-ATS1201E","AXON-ATS1810","AXON-ATS1811"))
    return added, rs485

def validate_caps(doors, zones, outputs_total):
    errs = []
    if zones > ZONE_MAX:
        errs.append(f"Zones cannot exceed {ZONE_MAX}.")
    if doors < 0 or zones < 0 or outputs_total < 0:
        errs.append("Inputs must be non-negative integers.")
    return errs

# ---- compact row helpers (label left, small input right, close together) ----
def row_number(label, key, minv=0, maxv=None, value=0, step=1, disabled=False, help_text=None):
    left, right = st.columns([0.70, 0.30])  # right is narrow so input sits close
    with left:
        st.markdown(f"<div class='axon-label'>{label}</div>", unsafe_allow_html=True)
    with right:
        return st.number_input(
            label="", key=key, min_value=minv,
            max_value=maxv, value=value, step=step,
            disabled=disabled, help=help_text, label_visibility="collapsed"
        )

def row_select(label, key, options, index=0, help_text=None):
    left, right = st.columns([0.70, 0.30])
    with left:
        st.markdown(f"<div class='axon-label'>{label}</div>", unsafe_allow_html=True)
    with right:
        return st.selectbox(label="", key=key, options=options, index=index, help=help_text, label_visibility="collapsed")

# -------------------- Layout --------------------
# Page = [ LeftWide (Inputs + Lift card) | RightSlim (Instructions) ]
left_wide, right_slim = st.columns([4, 1])

with left_wide:
    # Two columns: Inputs (left) and Lift card (right)
    inputs_col, lift_col = st.columns([2, 1])

    with inputs_col:
        st.markdown("#### Inputs")
        st.markdown("<div class='card'>", unsafe_allow_html=True)

        # System
        st.markdown("**System**")
        doors = row_number("Doors", "doors", value=0)
        zones = row_number("Zones", "zones", value=0, maxv=ZONE_MAX, help_text=f"Max {ZONE_MAX} (AXON panel capacity)")

        # Outputs; Door Outputs mirrors Doors live and stays close to its label
        row_number("Door Outputs", "door_outputs_display", value=int(doors), disabled=True)
        siren_outputs = row_number("Siren Outputs", "siren_outputs", value=0)
        other_outputs  = row_number("Other Outputs",  "other_outputs",  value=0)

        # Lift toggle
        lift_choice = row_select("Lift Control", "lift_choice", ["No", "Yes"], index=0)

        # Readers
        st.markdown("---")
        st.markdown("**Readers**")
        axon1180 = row_number("AXON1180 – AXON Reader", "axon1180", value=0)
        axon1181 = row_number("AXON1181 – AXON Reader", "axon1181", value=0)
        hid20_seos = row_number("HID-20-SEOS – HID SEOS Reader", "hid_seos", value=0)
        hid20_smart = row_number("HID-20-SMART – HID Smart Reader", "hid_smart", value=0)
        hid20_seos_kp = row_number("HID-20-SEOS-KP – HID SEOS Reader with Keypad", "hid_seos_kp", value=0)
        hid20_smart_kp = row_number("HID-20-SMART-KP – HID Smart Reader with Keypad", "hid_smart_kp", value=0)

        # Keypads & Options
        st.markdown("---")
        st.markdown("**Keypads & Options**")
        extra1125 = row_number(
            "Additional ATS1125 LCD Keypad", "extra1125", value=0,
            help_text="1x ATS1125 LCD Keypad already included in BOM, as it is required for initial setup"
        )
        touch1140 = row_number("ATS1140 Touchscreen Keypad", "touch1140", value=0)
        mod_4g = row_select("4G Module Required", "mod_4g", ["No", "Yes"], index=0)
        manual_1330 = row_number("AXON-ATS1330 - BUS Distributor (manual add)", "manual_1330", value=0)

        # Credentials
        st.markdown("---")
        st.markdown("**Credentials**")
        cred_iso_pack = row_number("AXON-ATS1455-10Pack – AXON ISO Cards - 10 Pack", "cred_iso_pack", value=0)
        cred_tag_pack = row_number("AXON-ATS1453-5Pack – AXON Keytags - 5 Pack", "cred_tag_pack", value=0)

        st.markdown("</div>", unsafe_allow_html=True)

    # Lift card (appears immediately when Yes) — sits RIGHT NEXT to Inputs
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
        "- Enter **Doors / Zones / Outputs**.\n"
        "- **Door Outputs** mirrors **Doors** automatically.\n"
        "- Set **Lift Control** to **Yes** to configure **Lifts/Levels**.\n"
        "- Click **Generate BOM** to build the parts list and totals.\n"
        "- Use **Download CSV** to export."
    )
    st.markdown("</div>", unsafe_allow_html=True)

# -------------------- Actions --------------------
act_cols = st.columns([1, 1, 6])
with act_cols[0]:
    generate = st.button("Generate BOM", type="primary")
with act_cols[1]:
    if st.button("Reset"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.experimental_rerun()

# -------------------- Logic --------------------
def validate_and_build(doors, zones, siren_outputs, other_outputs,
                       readers, extra1125, touch1140, mod_4g, manual_1330):
    outputs_total = int(doors) + int(siren_outputs) + int(other_outputs)
    errors = validate_caps(int(doors), int(zones), outputs_total)
    if errors:
        return None, errors

    q = []
    notes = {
        "queue": q,
        "panel_1811": 0, "panel_1810": 0,
        "dgp_1811": 0,   "dgp_1810": 0, "dgp_1801": 0,
        "dgp_added_for_outputs": False,
    }

    zones_total, rs485_z, cdc4 = distribute_zones_to_panel_and_dgps(int(zones), notes)
    added_panel_out, rs485_out_panel = expand_outputs_on_panel(outputs_total, notes)
    remaining_outputs = max(0, outputs_total - OUTPUTS_ONBOARD - added_panel_out)
    _, rs485_out_dgp = place_remaining_outputs_on_dgp(remaining_outputs, notes)

    # Readers
    add_item(q, "AXON-AXON1180", int(readers["axon1180"]))
    add_item(q, "AXON-AXON1181", int(readers["axon1181"]))
    add_item(q, "HID-20-SEOS",   int(readers["hid20_seos"]))
    add_item(q, "HID-20-SMART",  int(readers["hid20_smart"]))
    add_item(q, "HID-20-SEOS-KP",int(readers["hid20_seos_kp"]))
    add_item(q, "HID-20-SMART-KP", int(readers["hid20_smart_kp"]))

    # Keypads & Options
    add_item(q, "AXON-ATS1125", 1 + int(extra1125))  # 1 included + extras
    add_item(q, "AXON-ATS1140", int(touch1140))
    if mod_4g == "Yes":
        add_item(q, "AXON-ATS7341", 1)

    # Credentials
    add_item(q, "AXON-ATS1455-10Pack", 0 if "cred_iso_pack" not in st.session_state else int(st.session_state["cred_iso_pack"]))
    add_item(q, "AXON-ATS1453-5Pack",  0 if "cred_tag_pack" not in st.session_state else int(st.session_state["cred_tag_pack"]))

    # Manual BUS Distributor
    add_item(q, "AXON-ATS1330", int(manual_1330))

    # RS-485 estimate (hosts + expanders + readers)
    rs485 = rs485_z + rs485_out_panel + rs485_out_dgp
    rs485 += sum([
        int(readers["axon1180"]), int(readers["axon1181"]),
        int(readers["hid20_seos"]), int(readers["hid20_smart"]),
        int(readers["hid20_seos_kp"]), int(readers["hid20_smart_kp"])
    ])

    return {
        "zones_total": zones_total,
        "outputs_total": outputs_total,
        "doors_total": int(doors),
        "rs485": rs485,
        "cdc4": 0,
        "rows": q
    }, None

# -------------------- Generate --------------------
if generate:
    readers = {
        "axon1180":     st.session_state.get("axon1180", 0),
        "axon1181":     st.session_state.get("axon1181", 0),
        "hid20_seos":   st.session_state.get("hid_seos", 0),
        "hid20_smart":  st.session_state.get("hid_smart", 0),
        "hid20_seos_kp":st.session_state.get("hid_seos_kp", 0),
        "hid20_smart_kp":st.session_state.get("hid_smart_kp", 0),
    }

    result, errors = validate_and_build(
        doors=st.session_state.get("doors", 0),
        zones=st.session_state.get("zones", 0),
        siren_outputs=st.session_state.get("siren_outputs", 0),
        other_outputs=st.session_state.get("other_outputs", 0),
        readers=readers,
        extra1125=st.session_state.get("extra1125", 0),
        touch1140=st.session_state.get("touch1140", 0),
        mod_4g=st.session_state.get("lift_choice_mod", st.session_state.get("mod_4g", "No")) if False else st.session_state.get("mod_4g", "No"),
        manual_1330=st.session_state.get("manual_1330", 0),
    )

    if errors:
        for e in errors: st.error(e)
        st.stop()

    # ---- Summary strip ----
    st.markdown("#### Summary")
    s1, s2, s3, s4, s5 = st.columns([1.2, 1, 1, 1, 1])
    s1.metric("RS-485 Device Count", result["rs485"])
    s2.metric("CDC4 Added", result["cdc4"])
    s3.metric("Zones Total", result["zones_total"])
    s4.metric("Outputs Total", result["outputs_total"])
    s5.metric("Doors Total", result["doors_total"])

    # ---- BOM ----
    st.markdown("#### BOM (SKU / Name / Qty)")
    df = pd.DataFrame(result["rows"], columns=["SKU", "Name", "Qty"]).sort_values(by=["SKU"])
    st.dataframe(df, use_container_width=True, hide_index=True, height=320)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", data=csv, file_name="AXON_BOM.csv", mime="text/csv")
else:
    st.info("Adjust inputs, then click **Generate BOM**. "
            "Door Outputs mirrors Doors live. Zones are capped at 256.")
