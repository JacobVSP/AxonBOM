import streamlit as st
import pandas as pd

# -------------------- Page & style --------------------
st.set_page_config(page_title="AXON BOM Generator (Web)", layout="wide")

# Compact, calm UI
st.markdown("""
<style>
/* Tighten page and keep it calm */
.main .block-container { max-width: 1200px; padding-top: 12px; padding-bottom: 12px; }

/* Card look for groups */
.card {
  border: 1px solid #e6e6e6; border-radius: 10px;
  padding: 12px 14px; background: #fafafa;
}

/* Labels slimmer */
.axon-label { font-weight: 600; margin: 2px 0 4px 0; }

/* Make numeric inputs small by constraining their column width */
.small-col { max-width: 140px; }
.small-col div[data-baseweb="input"] input { text-align: right; }

/* Slim instructions text */
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
    """Return zones_total_on_panel, dgps_needed, rs485_devices_added, cdc4_count"""
    panel_zones = ZONES_ONBOARD
    rs485_devices = 0
    cdc4_count = 0
    dgps = 0
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
        dgps += 1
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

    return panel_zones, dgps, rs485_devices, cdc4_count

def expand_outputs_on_panel(outputs_needed, notes):
    """
    Panel-side expansion:
    - 5 onboard → + ATS624 (+4) → + ATS1810 on ATS624 (+4) → then up to 4× ATS1811 (+8 each)
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

def row_number(label, key, minv=0, maxv=None, value=0, step=1, disabled=False, help_text=None):
    """Compact row: label on left, short number input on the right."""
    c1, c2 = st.columns([0.7, 0.3])
    with c1:
        st.markdown(f"<div class='axon-label'>{label}</div>", unsafe_allow_html=True)
    with c2:
        with st.container():
            st.write("")  # nudge down a bit
            return st.number_input(
                label="", key=key, min_value=minv,
                max_value=maxv, value=value, step=step,
                disabled=disabled, help=help_text
            )

def row_select(label, key, options, index=0, help_text=None):
    c1, c2 = st.columns([0.7, 0.3])
    with c1:
        st.markdown(f"<div class='axon-label'>{label}</div>", unsafe_allow_html=True)
    with c2:
        with st.container():
            st.write("")
            return st.selectbox(label="", key=key, options=options, index=index, help=help_text)

# -------------------- Layout --------------------
# Page = [ LeftWide (Inputs + Lift card) | RightSlim (Instructions) ]
left_wide, right_slim = st.columns([4, 1])

with left_wide:
    # LeftWide has two columns: Inputs (left) and Lift card placeholder (right)
    inputs_col, lift_col = st.columns([2, 1])

    with inputs_col:
        st.markdown("#### Inputs")
        with st.container():
            st.markdown("<div class='card'>", unsafe_allow_html=True)

            # System
            st.markdown("**System**")
            doors = row_number("Doors", "doors", value=0)
            zones = row_number("Zones", "zones", value=0, maxv=ZONE_MAX, help_text=f"Max {ZONE_MAX} (AXON panel capacity)")

            # Outputs split; Door Outputs mirrors Doors live
            row_number("Door Outputs", "door_outputs_display", value=int(doors), disabled=True)
            siren_outputs = row_number("Siren Outputs", "siren_outputs", value=0)
            other_outputs  = row_number("Other Outputs",  "other_outputs",  value=0)

            # Lift control
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

            st.markdown("</div>", unsafe_allow_html=True)  # /card

    # Lift Control card appears immediately when set to Yes (next to Inputs)
    with lift_col:
        if lift_choice == "Yes":
            st.markdown("#### Lift Control")
            with st.container():
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                lifts  = row_number("How many Lifts?",  "lifts",  value=0)
                levels = row_number("How many Levels?", "levels", value=0)
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            lifts, levels = 0, 0  # ensure defined

with right_slim:
    st.markdown("#### Instructions")
    with st.container():
        st.markdown("<div class='card axon-instr'>", unsafe_allow_html=True)
        st.markdown(
            "- Enter **Doors / Zones / Outputs**.\n"
            "- **Door Outputs** mirrors **Doors** automatically.\n"
            "- Set **Lift Control** to **Yes** to configure **Lifts/Levels**.\n"
            "- Click **Generate BOM** to build the parts list and totals.\n"
            "- Use **Download CSV** to export.",
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

# -------------------- Compute & Output --------------------
if generate:
    outputs_total = int(doors) + int(siren_outputs) + int(other_outputs)
    errors = validate_caps(int(doors), int(zones), outputs_total)
    if errors:
        for e in errors: st.error(e)
        st.stop()

    q = []
    notes = {
        "queue": q,
        "panel_1811": 0, "panel_1810": 0,
        "dgp_1811": 0,   "dgp_1810": 0, "dgp_1801": 0,
        "dgp_added_for_outputs": False,
    }

    zones_total, dgps, rs485_z, cdc4 = distribute_zones_to_panel_and_dgps(int(zones), notes)
    added_panel_out, rs485_out_panel = expand_outputs_on_panel(outputs_total, notes)
    remaining_outputs = max(0, outputs_total - OUTPUTS_ONBOARD - added_panel_out)
    added_on_dgp, rs485_out_dgp = place_remaining_outputs_on_dgp(remaining_outputs, notes)

    # Readers
    add_item(q, "AXON-AXON1180", int(axon1180))
    add_item(q, "AXON-AXON1181", int(axon1181))
    add_item(q, "HID-20-SEOS",   int(hid20_seos))
    add_item(q, "HID-20-SMART",  int(hid20_smart))
    add_item(q, "HID-20-SEOS-KP",int(hid20_seos_kp))
    add_item(q, "HID-20-SMART-KP", int(hid20_smart_kp))

    # Keypads & Options
    add_item(q, "AXON-ATS1125", 1 + int(extra1125))  # 1 included + extras
    add_item(q, "AXON-ATS1140", int(touch1140))
    if mod_4g == "Yes":
        add_item(q, "AXON-ATS7341", 1)

    # Credentials
    add_item(q, "AXON-ATS1455-10Pack", int(cred_iso_pack))
    add_item(q, "AXON-ATS1453-5Pack",  int(cred_tag_pack))

    # Manual BUS Distributor
    add_item(q, "AXON-ATS1330", int(manual_1330))

    # RS-485 estimate (hosts + expanders + readers)
    rs485 = rs485_z + rs485_out_panel + rs485_out_dgp
    rs485 += sum([int(axon1180), int(axon1181), int(hid20_seos), int(hid20_smart), int(hid20_seos_kp), int(hid20_smart_kp)])

    # ---- Stats strip ----
    st.markdown("#### Summary")
    s1, s2, s3, s4, s5 = st.columns([1.2, 1, 1, 1, 1])
    s1.metric("RS-485 Device Count", rs485)
    s2.metric("CDC4 Added", 0)
    s3.metric("Zones Total", zones_total)
    s4.metric("Outputs Total", outputs_total)
    s5.metric("Doors Total", int(doors))

    # ---- BOM table ----
    st.markdown("#### BOM (SKU / Name / Qty)")
    df = pd.DataFrame(q, columns=["SKU", "Name", "Qty"]).sort_values(by=["SKU"])
    st.dataframe(df, use_container_width=True, hide_index=True, height=320)  # scrolls beyond ~10 rows

    # CSV download
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", data=csv, file_name="AXON_BOM.csv", mime="text/csv")
else:
    st.info("Adjust inputs, then click **Generate BOM**. "
            "Door Outputs mirrors Doors live. Zones are capped at 256.")
