import streamlit as st
import pandas as pd

# -------------------- Page & style --------------------
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

/* Make number inputs compact and LEFT aligned; freeze width to ~140px */
div[data-testid="stNumberInput"] label { display: none; }
div[data-testid="stNumberInput"] > div { width: 140px !important; }   /* container width */
div[data-testid="stNumberInput"] input {
  padding: 2px 6px; height: 30px; text-align: left;
}

/* Make selects compact and ~140px wide, left aligned */
div[data-baseweb="select"] { width: 140px !important; }
div[data-baseweb="select"] > div { min-height: 30px; }
div[data-baseweb="select"] > div > div { padding-top: 2px; padding-bottom: 2px; }

/* Slim instruction text */
.axon-instr { font-size: 0.9rem; line-height: 1.35; }
</style>
""", unsafe_allow_html=True)

# -------------------- System limits --------------------
ZONES_ONBOARD = 16
OUTPUTS_ONBOARD = 5
DOOR_MAX    = 56
OUTPUT_MAX  = 128     # Doors + Sirens + Other
ZONE_MAX    = 256

# -------------------- Catalogue-accurate SKU -> Name map --------------------
NAME_MAP = {
 'AXON-256AU': 'AXON 256 Access Control Panel',
 'AXON-ATS1125': 'AXON LCD Keypad with Mifare Reader',
 'AXON-ATS1140': 'AXON Touchscreen Keypad with Mifare Reader',
 'AXON-ATS1180': 'AXON Secure Mifare Reader',
 'AXON-ATS1181': 'AXON Secure Mifare Reader with Keypad',
 'AXON-ATS1201E': 'AXON 8-Zone Input Expander',
 'AXON-ATS1202': 'AXON 8 Input Expander',
 'AXON-ATS1211E': '8 Input/Output DGP Expander + Metal Housing',
 'AXON-ATS1330': 'Axon Power Distribution Board',
 'AXON-ATS1453-5PACK': 'AXON Tear Keytag, DESFire EV2/3 2K, 5 Pack',
 'AXON-ATS1455-10PACK': 'AXON ISO Card, DESFire EV2/3 2K, 10 Pack',
 'AXON-ATS1810': 'Axon 4 Way Relay Card',
 'AXON-ATS1811': 'Axon 8 Way Relay Card',
 'AXON-ATS608': 'Axon Plug-on Input Expander',
 'AXON-ATS624': 'Axon Plug-on 4 Way Output Expander',
 'AXON-ATS7341': 'AXON 4G Module with UltraSync SIM',
 'AXON-CDC4-AU': 'AXON Intelligent 4 Door / Lift Controller',
 'HID-20KNKS-01': 'HID Signo 20 Keypad Reader, Seos Profile',
 'HID-20KNKS-02': 'HID Signo 20 Keypad Reader, Smart Profile',
 'HID-20NKS-01': 'HID Signo 20 Slim Reader, Seos Profile',
 'HID-20NKS-02': 'HID Signo 20 Slim Reader, Smart Profile',
 'HID-SEOS-ISO': 'HID Seos ISO Cards',
 'HID-SEOS-KEYTAG': 'HID Seos Keytags'
}

def label_sku(sku: str) -> str:
    return f"{sku} \u2013 {NAME_MAP.get(sku, sku)}"

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
        panel_zones += 8; panel_1811 += 1; remaining -= 8
        add_item(notes["queue"], "AXON-ATS1811", 1); rs485_devices += 1; notes["panel_1811"] += 1

    while remaining > 0:
        add_item(notes["queue"], "AXON-ATS1201E", 1); rs485_devices += 1
        take = min(remaining, DGP_ZONE_CAP); remaining -= take
        extra = max(0, take - ZONES_ONBOARD)
        while extra > 0:
            add_item(notes["queue"], "AXON-ATS1801", 1); rs485_devices += 1; notes["dgp_1801"] += 1
            extra -= 8
    return panel_zones, rs485_devices, cdc4_count

def expand_outputs_on_panel(outputs_needed, notes):
    added = 0; rs485 = 0
    shortfall = max(0, outputs_needed - OUTPUTS_ONBOARD)
    if shortfall <= 0: return added, rs485
    add_item(notes["queue"], "AXON-ATS624", 1); shortfall -= 4; added += 4
    if shortfall > 0:
        add_item(notes["queue"], "AXON-ATS1810", 1); shortfall -= 4; added += 4
        rs485 += 1; notes["panel_1810"] += 1
    while shortfall > 0 and notes["panel_1811"] < 4:
        add_item(notes["queue"], "AXON-ATS1811", 1); shortfall -= 8; added += 8
        rs485 += 1; notes["panel_1811"] += 1
    return added, rs485

def place_remaining_outputs_on_dgp(shortfall, notes):
    if shortfall <= 0: return 0, 0
    rs485 = 0; added = 0; hosts = []; q = notes["queue"]
    def ensure_host():
        for h in hosts:
            if h["remaining_out"] > 0: return h
        add_item(q, "AXON-ATS1201E", 1); notes["dgp_added_for_outputs"] = True
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
    if doors > DOOR_MAX: errs.append(f"Doors cannot exceed {DOOR_MAX} (system limit).")
    if outputs_total > OUTPUT_MAX: errs.append(f"Total Outputs cannot exceed {OUTPUT_MAX} (system limit).")
    if zones > ZONE_MAX: errs.append(f"Zones cannot exceed {ZONE_MAX} (system limit).")
    if min(doors, zones, outputs_total) < 0: errs.append("Inputs must be non-negative integers.")
    return errs

# ---------- Row helpers: [Label | Value | Spacer] ----------
def row_number(label, key, minv=0, maxv=None, value=0, step=1, disabled=False, help_text=None):
    # label | value (140px) | spacer
    c1, c2, _ = st.columns([0.48, 0.16, 0.36])
    with c1:
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
        return st.selectbox(label="", key=key, options=options, index=index, help=help_text, label_visibility="collapsed")

# -------------------- Layout --------------------
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

        # Outputs; Door Outputs mirrors Doors live (read-only)
        row_number("Door Outputs", "door_outputs_display", value=int(doors), disabled=True)
        siren_outputs = row_number("Siren Outputs", "siren_outputs", value=0, help_text=f"Outputs total ≤ {OUTPUT_MAX}")
        other_outputs  = row_number("Other Outputs",  "other_outputs",  value=0, help_text=f"Outputs total ≤ {OUTPUT_MAX}")

        # Lift toggle
        lift_choice = row_select("Lift Control", "lift_choice", ["No", "Yes"], index=0)

        # Readers (SKUs & Names from catalogue)
        st.markdown("---"); st.markdown("**Readers**")
        axon1180 = row_number(label_sku("AXON-ATS1180"), "axon1180", value=0)
        axon1181 = row_number(label_sku("AXON-ATS1181"), "axon1181", value=0)
        hid20_seos = row_number(label_sku("HID-20NKS-01"), "hid_seos", value=0)
        hid20_smart = row_number(label_sku("HID-20NKS-02"), "hid_smart", value=0)
        hid20_seos_kp = row_number(label_sku("HID-20KNKS-01"), "hid_seos_kp", value=0)
        hid20_smart_kp = row_number(label_sku("HID-20KNKS-02"), "hid_smart_kp", value=0)

        # Keypads & Options
        st.markdown("---"); st.markdown("**Keypads & Options**")
        extra1125 = row_number(
            f"{label_sku('AXON-ATS1125')} (additional)",
            "extra1125", value=0
        )
        touch1140 = row_number(label_sku("AXON-ATS1140"), "touch1140", value=0)
        mod_4g = row_select(label_sku("AXON-ATS7341"), "mod_4g", ["No", "Yes"], index=0)
        manual_1330 = row_number(label_sku("AXON-ATS1330"), "manual_1330", value=0)

        # Credentials
        st.markdown("---"); st.markdown("**Credentials**")
        cred_iso_pack   = row_number(label_sku("AXON-ATS1455-10PACK"), "cred_iso_pack", value=0)
        cred_tag_pack   = row_number(label_sku("AXON-ATS1453-5PACK"), "cred_tag_pack", value=0)
        hid_seos_iso    = row_number(label_sku("HID-SEOS-ISO"), "hid_seos_iso", value=0)
        hid_seos_keytag = row_number(label_sku("HID-SEOS-KEYTAG"), "hid_seos_keytag", value=0)

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

# -------------------- Build & Validate --------------------
def build_bom(doors, zones, siren_outputs, other_outputs,
              readers, extra1125, touch1140, mod_4g, manual_1330,
              cred_iso_pack, cred_tag_pack, hid_seos_iso, hid_seos_keytag):
    outputs_total = int(doors) + int(siren_outputs) + int(other_outputs)
    errors = validate_caps(int(doors), int(zones), outputs_total)
    if errors: return None, errors

    q = []
    notes = {"queue": q, "panel_1811": 0, "panel_1810": 0,
             "dgp_1811": 0, "dgp_1810": 0, "dgp_1801": 0, "dgp_added_for_outputs": False}

    zones_total, rs485_z, cdc4 = distribute_zones_to_panel_and_dgps(int(zones), notes)
    added_panel_out, rs485_out_panel = expand_outputs_on_panel(outputs_total, notes)
    remaining_outputs = max(0, outputs_total - OUTPUTS_ONBOARD - added_panel_out)
    _, rs485_out_dgp = place_remaining_outputs_on_dgp(remaining_outputs, notes)

    # Readers (catalogue-accurate SKUs)
    add_item(q, "AXON-ATS1180", int(readers["axon1180"]))
    add_item(q, "AXON-ATS1181", int(readers["axon1181"]))
    add_item(q, "HID-20NKS-01", int(readers["hid20_seos"]))
    add_item(q, "HID-20NKS-02", int(readers["hid20_smart"]))
    add_item(q, "HID-20KNKS-01", int(readers["hid20_seos_kp"]))
    add_item(q, "HID-20KNKS-02", int(readers["hid20_smart_kp"]))

    # Keypads & Options
    add_item(q, "AXON-ATS1125", 1 + int(extra1125))  # 1 included + extras
    add_item(q, "AXON-ATS1140", int(touch1140))
    if mod_4g == "Yes": add_item(q, "AXON-ATS7341", 1)

    # Credentials
    add_item(q, "AXON-ATS1455-10PACK", int(cred_iso_pack))
    add_item(q, "AXON-ATS1453-5PACK",  int(cred_tag_pack))
    add_item(q, "HID-SEOS-ISO",        int(hid_seos_iso))
    add_item(q, "HID-SEOS-KEYTAG",     int(hid_seos_keytag))

    # Manual Power Distribution Board
    add_item(q, "AXON-ATS1330", int(manual_1330))

    rs485 = rs485_z + rs485_out_panel + rs485_out_dgp
    rs485 += sum([int(readers["axon1180"]), int(readers["axon1181"]),
                  int(readers["hid20_seos"]), int(readers["hid20_smart"]),
                  int(readers["hid20_seos_kp"]), int(readers["hid20_smart_kp"])])
    return {"zones_total": zones_total, "outputs_total": outputs_total, "doors_total": int(doors),
            "rs485": rs485, "cdc4": 0, "rows": q}, None

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

    # Summary
    st.markdown("#### Summary")
    s1, s2, s3, s4, s5 = st.columns([1.2, 1, 1, 1, 1])
    s1.metric("RS-485 Device Count", result["rs485"])
    s2.metric("CDC4 Added", result["cdc4"])
    s3.metric("Zones Total", result["zones_total"])
    s4.metric("Outputs Total", result["outputs_total"])
    s5.metric("Doors Total", result["doors_total"])

    # BOM
    st.markdown("#### BOM (SKU / Name / Qty)")
    df = pd.DataFrame(result["rows"], columns=["SKU", "Name", "Qty"]).sort_values(by=["SKU"])
    st.dataframe(df, use_container_width=True, hide_index=True, height=320)
    st.download_button("Download CSV", data=df.to_csv(index=False).encode("utf-8"),
                       file_name="AXON_BOM.csv", mime="text/csv")
else:
    st.info(f"System limits: Doors ≤ {DOOR_MAX}, Outputs ≤ {OUTPUT_MAX}, Zones ≤ {ZONE_MAX}. "
            "Door Outputs mirrors Doors. Set Lift Control to Yes to configure Lifts/Levels.")
