# APP_enhanced.py
# MPGB Cricket Club - Enhanced (CrickPro-like UI, corrected commentary, autosync)
# Hindi comments where helpful

import streamlit as st
import pandas as pd
import json, os, uuid, io, random
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt

# optional autorefresh
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTORE = True
except Exception:
    HAS_AUTORE = False

# ---------------- CONFIG ----------------
DATA_DIR = "data"
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
MEMBERS_CSV = os.path.join(DATA_DIR, "members.csv")
PAID_CSV = os.path.join(DATA_DIR, "Members_Paid.csv")
MATCH_INDEX = os.path.join(DATA_DIR, "matches_index.json")
ADMIN_PHONE = "8931883300"  # change to your admin mobile if needed
LOGO_PATH = os.path.join(DATA_DIR, "logo.png")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# ---------------- Commentary templates (simplified, no field areas) ----------------
RUN_TEMPLATES = [
    "Quick push and a run taken.",
    "Good placement and a quick run.",
    "Worked away for a couple.",
    "Nice timing, they'll take two.",
    "Smart running between the wickets.",
    "Pushed away to the open side for a run."
]

WICKET_TEMPLATES = [
    "Clean bowled! That's a beauty.",
    "Caught — taken safely.",
    "LBW! The umpire raises his finger.",
    "Edge and taken — batsman has to walk.",
    "Run out! Direct hit.",
    "Stumped — beaten by the bowler."
]

EXTRA_TEMPLATES = {
    "WD": ["Wide called — extra run.", "Wide — one extra."],
    "NB": ["No ball — free hit coming!", "No ball — extra run awarded."],
    "BY": ["Byes added to the total.", "Byes — runs to the batting side."],
    "LB": ["Leg-byes added.", "Leg-bye — runs added."]
}

GENERIC_COMMENTS = [
    "Good over, tight bowling.",
    "Pressure building on the batsman.",
    "Crowd enjoying the contest.",
    "That’s a useful run for the batting side."
]

# ---------------- Helpers ----------------
def normalize_mobile(s):
    if pd.isna(s) or s is None:
        return ""
    s = str(s).strip()
    for ch in [" ", "+", "-", "(", ")"]:
        s = s.replace(ch, "")
    digits = "".join([c for c in s if c.isdigit()])
    if len(digits) > 10:
        digits = digits[-10:]
    return digits

def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    try:
        os.replace(tmp, path)
    except:
        os.rename(tmp, path)

# ---------------- Members ----------------
def ensure_members_file():
    if not os.path.exists(MEMBERS_CSV):
        df = pd.DataFrame(columns=["MemberID", "Name", "Mobile", "Paid"])
        df.to_csv(MEMBERS_CSV, index=False)

def read_members():
    ensure_members_file()
    try:
        df = pd.read_csv(MEMBERS_CSV, dtype=str)
    except:
        df = pd.DataFrame(columns=["MemberID", "Name", "Mobile", "Paid"])
    if "Mobile" in df.columns:
        df["Mobile"] = df["Mobile"].apply(normalize_mobile)
    else:
        df["Mobile"] = ""
    if "Paid" not in df.columns:
        df["Paid"] = "N"
    return df.fillna("")

def write_members(df):
    try:
        df2 = df.copy()
        df2.to_csv(MEMBERS_CSV, index=False)
    except Exception as e:
        st.error(f"Error saving members file: {e}")

def next_member_id():
    df = read_members()
    if df.empty:
        return "M001"
    ids = df["MemberID"].dropna().tolist()
    nums = []
    for i in ids:
        try:
            nums.append(int(i.lstrip("M")))
        except:
            pass
    mx = max(nums) if nums else 0
    return f"M{(mx+1):03d}"

def save_member_photo(member_id, uploaded_file):
    try:
        image = Image.open(uploaded_file).convert("RGB")
        ext = uploaded_file.name.split(".")[-1].lower()
        if ext not in ["png", "jpg", "jpeg"]:
            ext = "png"
        path = os.path.join(PHOTOS_DIR, f"{member_id}.{ext}")
        image.save(path)
        return path
    except Exception as e:
        st.error(f"Photo save failed: {e}")
        return None

def get_member_photo_path(member_id):
    for ext in ["png", "jpg", "jpeg"]:
        p = os.path.join(PHOTOS_DIR, f"{member_id}.{ext}")
        if os.path.exists(p):
            return p
    return None

# ---------------- Paid list helpers ----------------
def read_paid_list():
    if os.path.exists(PAID_CSV):
        try:
            df = pd.read_csv(PAID_CSV, dtype=str)
        except:
            df = pd.DataFrame(columns=["Mobile_No"])
    else:
        df = pd.DataFrame(columns=["Mobile_No"])
    if df.shape[0] > 0:
        col = df.columns[0]
        df = df.rename(columns={col: "Mobile_No"})
        df["Mobile_No"] = df["Mobile_No"].apply(normalize_mobile)
        df = df[df["Mobile_No"] != ""].drop_duplicates().reset_index(drop=True)
    return df

def write_paid_list(df):
    try:
        df2 = df.copy()
        if "Mobile_No" not in df2.columns:
            df2.columns = ["Mobile_No"]
        df2["Mobile_No"] = df2["Mobile_No"].apply(normalize_mobile)
        df2.to_csv(PAID_CSV, index=False)
    except Exception as e:
        st.error(f"Failed to write paid list: {e}")

def is_mobile_paid(mobile):
    m = normalize_mobile(mobile)
    if not m:
        return False
    paid = read_paid_list()
    if not paid.empty and m in paid["Mobile_No"].tolist():
        return True
    mems = read_members()
    match = mems[mems["Mobile"] == m]
    if not match.empty and str(match.iloc[0].get("Paid", "N")).upper() == "Y":
        return True
    return False

def sync_paid_with_registry():
    paid_df = read_paid_list()
    mems = read_members()
    if paid_df.empty:
        return {"updated_count": 0, "unmatched": []}
    paid_set = set(paid_df["Mobile_No"].tolist())
    updated = 0
    unmatched = []
    for idx, row in mems.iterrows():
        mob = normalize_mobile(row.get("Mobile", ""))
        if mob and mob in paid_set:
            if mems.at[idx, "Paid"] != "Y":
                mems.at[idx, "Paid"] = "Y"
                updated += 1
    reg_mobs = set(mems["Mobile"].apply(normalize_mobile).tolist())
    for p in paid_set:
        if p not in reg_mobs:
            unmatched.append(p)
    write_members(mems)
    return {"updated_count": updated, "unmatched": unmatched}

# ---------------- Match state helpers ----------------
def load_matches_index():
    return load_json(MATCH_INDEX, {})

def save_matches_index(idx):
    save_json(MATCH_INDEX, idx)

def match_state_path(mid):
    return os.path.join(DATA_DIR, f"match_{mid}_state.json")

def save_match_state(mid, state):
    save_json(match_state_path(mid), state)
    # backup
    try:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        save_json(os.path.join(BACKUP_DIR, f"match_{mid}_backup_{ts}.json"), state)
    except:
        pass

def load_match_state(mid):
    return load_json(match_state_path(mid), {})

def init_match_state_full(mid, title, overs, teamA, teamB, venue=""):
    state = {
        "mid": mid,
        "title": title,
        "venue": venue,
        "overs_limit": int(overs),
        "status": "INNINGS1",
        "innings": 1,
        "bat_team": "Team A",
        "teams": {"Team A": teamA, "Team B": teamB},
        "score": {"Team A": {"runs": 0, "wkts": 0, "balls": 0}, "Team B": {"runs": 0, "wkts": 0, "balls": 0}},
        "batting": {"striker": teamA[0] if len(teamA) > 0 else "", "non_striker": teamA[1] if len(teamA) > 1 else "", "order": teamA[:], "next_index": 2},
        "bowling": {"current_bowler": "", "last_over_bowler": ""},
        "batsman_stats": {},
        "bowler_stats": {},
        "balls_log": [],
        "commentary": [],
        "overs_detail": [],
        "man_of_match_override": "",
        "scorer_lock": {}
    }
    save_match_state(mid, state)
    return state

# ---------------- Commentary pick function (fixed format) ----------------
def pick_commentary(outcome, striker, bowler, extras=None):
    """
    Return commentary in format: "Bowler to Striker — <text>"
    No field-area words. Specific texts for 6 and 4.
    """
    extras = extras or {}
    striker = striker or "Batsman"
    bowler = bowler or "Bowler"
    text = ""

    # Normalize possible outcomes
    o = str(outcome)

    if o == "6":
        text = "It's a HUGE SIX!"
    elif o == "4":
        text = "That's a FOUR!"
    elif o in ["1", "2", "3"]:
        text = random.choice(RUN_TEMPLATES)
    elif o in ["0", "dot", ""]:
        text = random.choice(["No runs. Dot ball.", "Tight bowling — dot ball."])
    elif o in ["W", "Wicket"]:
        text = random.choice(WICKET_TEMPLATES)
    elif o in ["WD", "Wide"]:
        text = random.choice(EXTRA_TEMPLATES["WD"])
    elif o in ["NB", "NoBall"]:
        text = random.choice(EXTRA_TEMPLATES["NB"])
    elif o in ["BY", "LB", "Bye", "LegBye"]:
        text = random.choice(EXTRA_TEMPLATES["BY"])
    else:
        text = random.choice(GENERIC_COMMENTS)

    return f"{bowler} to {striker} — {text}"

# ---------------- Scoring logic ----------------
def format_over_ball(total_balls):
    if total_balls <= 0:
        return "0.0"
    over_num = (total_balls) // 6
    ball_in_over = (total_balls) % 6
    return f"{over_num}.{ball_in_over}"

def record_ball_full(state, mid, outcome, extras=None, wicket_info=None):
    if extras is None: extras = {}
    bat_team = state["bat_team"]
    sc = state["score"][bat_team]
    striker = state["batting"].get("striker", "")
    non_striker = state["batting"].get("non_striker", "")
    bowler = state["bowling"].get("current_bowler", "") or "Unknown"

    # prepare entry
    entry = {
        "time": datetime.utcnow().isoformat(),
        "outcome": outcome,
        "extras": extras,
        "wicket": wicket_info,
        "striker": striker,
        "non_striker": non_striker,
        "bowler": bowler,
        "prev_score": sc.copy(),
        "prev_batsman": {striker: state["batsman_stats"].get(striker, {}).copy(), non_striker: state["batsman_stats"].get(non_striker, {}).copy()},
        "prev_bowler": {bowler: state["bowler_stats"].get(bowler, {}).copy()}
    }

    # ensure stats exist
    state["batsman_stats"].setdefault(striker, {"R": 0, "B": 0, "4": 0, "6": 0})
    state["batsman_stats"].setdefault(non_striker, {"R": 0, "B": 0, "4": 0, "6": 0})
    state["bowler_stats"].setdefault(bowler, {"B": 0, "R": 0, "W": 0})

    # outcomes
    if str(outcome) in ["0", "1", "2", "3", "4", "6"]:
        runs = int(outcome)
        state["batsman_stats"][striker]["R"] += runs
        state["batsman_stats"][striker]["B"] += 1
        if runs == 4: state["batsman_stats"][striker]["4"] += 1
        if runs == 6: state["batsman_stats"][striker]["6"] += 1
        state["bowler_stats"][bowler]["B"] += 1
        state["bowler_stats"][bowler]["R"] += runs
        sc["runs"] += runs
        sc["balls"] += 1
        # swap on odd
        if runs % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker

    elif str(outcome) in ["W", "Wicket"]:
        state["batsman_stats"][striker]["B"] += 1
        state["bowler_stats"][bowler]["B"] += 1
        state["bowler_stats"][bowler]["W"] = state["bowler_stats"][bowler].get("W", 0) + 1
        sc["wkts"] += 1
        sc["balls"] += 1
        nxt = state["batting"].get("next_index", 0)
        order = state["batting"].get("order", [])
        next_player = None
        if wicket_info and wicket_info.get("new_batsman"):
            next_player = wicket_info.get("new_batsman")
        else:
            while nxt < len(order):
                cand = order[nxt]; nxt += 1
                if cand not in [striker, non_striker]:
                    next_player = cand
                    break
        state["batting"]["next_index"] = nxt
        if next_player:
            state["batting"]["striker"] = next_player
            state["batsman_stats"].setdefault(next_player, {"R": 0, "B": 0, "4": 0, "6": 0})

    elif str(outcome) in ["WD", "Wide"]:
        add = int(extras.get("runs", 1))
        state["bowler_stats"][bowler]["R"] += add
        sc["runs"] += add
        # no ball count increment

    elif str(outcome) in ["NB", "NoBall"]:
        offbat = int(extras.get("runs_off_bat", 0))
        add = 1 + offbat
        state["bowler_stats"][bowler]["R"] += add
        sc["runs"] += add
        if offbat > 0:
            state["batsman_stats"][striker]["R"] += offbat

    elif str(outcome) in ["BY", "LB", "Bye", "LegBye"]:
        add = int(extras.get("runs", 1))
        sc["runs"] += add
        state["batsman_stats"][striker]["B"] += 1
        state["bowler_stats"][bowler]["B"] += 1
        sc["balls"] += 1
        if add % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker

    else:
        # default treat as dot
        state["batsman_stats"][striker]["B"] += 1
        state["bowler_stats"][bowler]["B"] += 1
        sc["balls"] += 1

    entry["post_score"] = sc.copy()
    state["balls_log"].append(entry)

    # commentary: use pick_commentary to generate standardized line
    comment_text = pick_commentary(str(outcome), striker, bowler, extras)
    state["commentary"].append(format_over_ball(sc["balls"]) + " — " + comment_text)

    save_match_state(mid, state)
    return entry

def undo_last_ball_full(state, mid):
    if not state.get("balls_log"):
        return False
    last = state["balls_log"].pop()
    state["score"][state["bat_team"]] = last.get("prev_score", state["score"][state["bat_team"]])
    prev_bats = last.get("prev_batsman", {})
    for p, vals in prev_bats.items():
        if vals == {}:
            state["batsman_stats"].pop(p, None)
        else:
            state["batsman_stats"][p] = vals
    prev_bowl = last.get("prev_bowler", {})
    for p, vals in prev_bowl.items():
        if vals == {}:
            state["bowler_stats"].pop(p, None)
        else:
            state["bowler_stats"][p] = vals
    if state.get("commentary"):
        state["commentary"].pop()
    save_match_state(mid, state)
    return True

# ---------------- Scorer lock ----------------
def try_acquire_scorer_lock(state, mid, phone):
    lock = state.get("scorer_lock", {})
    now = datetime.utcnow()
    if not lock or not lock.get("locked_by"):
        state["scorer_lock"] = {"locked_by": phone, "locked_at": now.isoformat(), "expires_at": (now + timedelta(minutes=15)).isoformat()}
        save_match_state(mid, state)
        return True
    try:
        expires = datetime.fromisoformat(lock.get("expires_at"))
        if expires < now:
            state["scorer_lock"] = {"locked_by": phone, "locked_at": now.isoformat(), "expires_at": (now + timedelta(minutes=15)).isoformat()}
            save_match_state(mid, state)
            return True
    except:
        pass
    return False

def release_scorer_lock(state, mid, phone):
    lock = state.get("scorer_lock", {})
    if lock.get("locked_by") == phone:
        state["scorer_lock"] = {}
        save_match_state(mid, state)
        return True
    return False

# ---------------- Export helpers ----------------
def export_match_json(state):
    return json.dumps(state, indent=2, ensure_ascii=False).encode("utf-8")

def export_match_csv(state):
    rows = []
    for b in state.get("balls_log", []):
        rows.append({
            "time": b.get("time"),
            "outcome": b.get("outcome"),
            "striker": b.get("striker"),
            "non_striker": b.get("non_striker"),
            "bowler": b.get("bowler"),
            "extras": json.dumps(b.get("extras", {}), ensure_ascii=False),
            "wicket": json.dumps(b.get("wicket", {}), ensure_ascii=False)
        })
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode("utf-8")

# ---------------- UI setup ----------------
st.set_page_config(page_title="MPGB Cricket Club - Sagar", layout="wide")

# Banner CSS and markup
BANNER_CSS = """
<style>
.app-banner {
  width:100%;
  background: linear-gradient(90deg,#0b6efd,#055ecb);
  color:#fff; padding:14px 18px; border-radius:8px;
  display:flex; align-items:center; justify-content:space-between; gap:12px;
  box-shadow:0 4px 18px rgba(5,94,203,.18);
}
.banner-title{font-size:22px;font-weight:800;margin:0;}
.banner-sub{font-size:12px;opacity:.95;margin-top:4px;}
.cricket-badge{background:rgba(255,255,255,.12);padding:8px 12px;border-radius:999px;font-weight:700;}
</style>
"""
st.markdown(BANNER_CSS, unsafe_allow_html=True)

# Logo html
logo_html = ""
if os.path.exists(LOGO_PATH):
    import base64
    try:
        logo_bytes = open(LOGO_PATH, "rb").read()
        logo_b64 = base64.b64encode(logo_bytes).decode()
        logo_html = f"<img src='data:image/png;base64,{logo_b64}' style='width:64px;height:64px;border-radius:8px;'/>"
    except:
        logo_html = "<div style='width:64px;height:64px;border-radius:8px;background:rgba(255,255,255,.14);display:flex;align-items:center;justify-content:center;'>MPGB</div>"
else:
    logo_html = "<div style='width:64px;height:64px;border-radius:8px;background:rgba(255,255,255,.14);display:flex;align-items:center;justify-content:center;'>MPGB</div>"

st.markdown(f"""
<div class="app-banner">
  <div style='display:flex;align-items:center;gap:12px;'>
    {logo_html}
    <div>
      <div class="banner-title">MPGB Cricket Club - Sagar</div>
      <div class="banner-sub">An official group of Madhya Pradesh Gramin Bank</div>
    </div>
  </div>
  <div><div class="cricket-badge">🏏 Cricket • Score • Share</div></div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br/>", unsafe_allow_html=True)

# small CSS for CrickPro-style buttons (applies globally)
BUTTON_CSS = """
<style>
div.stButton > button:first-child {
    background-color:#0b6efd !important;
    color: white !important;
    border-radius: 8px !important;
    height:48px !important;
    min-width:64px !important;
    font-size:18px !important;
    font-weight:700 !important;
    box-shadow: 0 6px 14px rgba(11,110,253,0.18);
}
</style>
"""
st.markdown(BUTTON_CSS, unsafe_allow_html=True)

# ---------------- Current member helper & sidebar ----------------
def current_member():
    mid = st.session_state.get("MemberID", "")
    if not mid:
        return None
    df = read_members()
    row = df[df["MemberID"] == mid]
    if row.empty:
        return None
    return row.iloc[0].to_dict()

def get_role_from_mobile(mobile):
    m = normalize_mobile(mobile)
    if not m:
        return "guest"
    if m == normalize_mobile(ADMIN_PHONE):
        return "admin"
    if is_mobile_paid(m):
        return "member"
    return "guest"

mem = current_member()
st.sidebar.title("Member")
if mem:
    st.sidebar.markdown("### Member Card")
    st.sidebar.markdown(f"**ID:** {mem.get('MemberID')}")
    st.sidebar.markdown(f"**Name:** {mem.get('Name')}")
    st.sidebar.markdown(f"**Mobile:** {mem.get('Mobile')}")
    st.sidebar.markdown(f"**Paid:** {mem.get('Paid')}")
    ppath = get_member_photo_path(mem.get("MemberID"))
    if ppath:
        st.sidebar.image(ppath, width=120)
    # Safe creation of ID bytes (works even if generate_id_card_image missing or returns bytes/BytesIO)
id_bytes = None
if mem:
    try:
        buf = generate_id_card_image(mem)  # try to call
        # if function returned a BytesIO-like object
        if hasattr(buf, "getvalue"):
            id_bytes = io.BytesIO(buf.getvalue())
        else:
            # if it returned raw bytes
            id_bytes = io.BytesIO(buf)
    except NameError:
        # function not defined — create a small placeholder PNG bytes
        placeholder = Image.new("RGB", (600,360), color=(255,255,255))
        ph_draw = ImageDraw.Draw(placeholder)
        ph_draw.text((20,20), f"MPGB ID\\n{mem.get('Name','-')}", fill=(0,0,0))
        tmp = io.BytesIO()
        placeholder.save(tmp, format="PNG")
        tmp.seek(0)
        id_bytes = tmp
    except Exception as e:
        # fallback placeholder on any other error
        placeholder = Image.new("RGB", (600,360), color=(255,255,255))
        ph_draw = ImageDraw.Draw(placeholder)
        ph_draw.text((20,20), "ID generation error", fill=(0,0,0))
        tmp = io.BytesIO()
        placeholder.save(tmp, format="PNG")
        tmp.seek(0)
        id_bytes = tmp
else:
    id_bytes = NoneS
    if id_bytes:
        st.sidebar.download_button(label="Download ID Card (PNG)", data=id_bytes.getvalue(), file_name=f"{mem.get('MemberID')}_ID.png", mime="image/png")
    if st.sidebar.button("Logout"):
        st.session_state.pop("MemberID", None)
        st.experimental_rerun()
else:
    st.sidebar.info("Guest — go to Menu → Login / Register")

# ---------------- Menu (sidebar) ----------------
menu = st.sidebar.selectbox("Menu", ["Home","Login / Register","Match Setup","Live Scorer","Live Score (Public)","Player Stats","Admin"])

# ---------------- Pages ----------------
if menu == "Home":
    st.subheader("Welcome to MPGB Cricket Club - Sagar")
    st.write("Use the Menu to create matches, score and view live scoreboard. Login/Register to access member features.")

# ---------------- Login / Register ----------------
if menu == "Login / Register":
    st.header("Login / Register")
    login_mobile = st.text_input("Enter mobile (10 digits)", key="ui_login_mobile")
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("Login"):
            mnorm = normalize_mobile(login_mobile)
            if not mnorm:
                st.error("Please enter valid mobile number.")
            else:
                mems = read_members()
                if mnorm in mems["Mobile"].tolist():
                    row = mems[mems["Mobile"] == mnorm].iloc[0]
                    st.session_state["MemberID"] = row["MemberID"]
                    if is_mobile_paid(mnorm):
                        st.success(f"Logged in as {row['Name']} ({row['MemberID']}) — Paid ✔️")
                    else:
                        st.success(f"Logged in as {row['Name']} ({row['MemberID']}) — Not Verified")
                    st.experimental_rerun()
                else:
                    st.info("Mobile not registered. Please register below.")
    with col2:
        if st.button("Check Verification Status"):
            if is_mobile_paid(login_mobile):
                st.success("Status: VERIFIED — membership paid ✔️")
            else:
                st.warning("Status: NOT VERIFIED — Please contact admin.")
    st.markdown("### Register (if new)")
    with st.form("ui_register_form"):
        rname = st.text_input("Full name")
        rmobile = st.text_input("Mobile (10 digits)")
        rphoto = st.file_uploader("Photo (optional)", type=["jpg","jpeg","png"])
        submitted = st.form_submit_button("Register")
        if submitted:
            if not rname.strip() or not rmobile.strip():
                st.error("Name and mobile required")
            else:
                mems = read_members()
                mnorm = normalize_mobile(rmobile)
                if mnorm in mems["Mobile"].tolist():
                    st.info("This mobile already registered.")
                else:
                    nid = next_member_id()
                    new = pd.DataFrame([{"MemberID": nid, "Name": rname.strip(), "Mobile": mnorm, "Paid": "N"}])
                    write_members(pd.concat([mems, new], ignore_index=True))
                    if rphoto is not None:
                        save_member_photo(nid, rphoto)
                    st.success(f"Registered. Member ID: {nid}")
                    st.session_state["MemberID"] = nid
                    st.experimental_rerun()

# ---------------- Match Setup ----------------
if menu == "Match Setup":
    cm = current_member()
    role = get_role_from_mobile(cm["Mobile"]) if cm else "guest"
    if role not in ["member","admin"]:
        st.warning("Match creation is for paid members only.")
        st.stop()
    st.subheader("Create / Manage Matches")
    matches = load_matches_index()
    with st.form("create_match", clear_on_submit=True):
        title = st.text_input("Match Title (Team A vs Team B)")
        venue = st.text_input("Venue (optional)")
        overs = st.number_input("Overs per innings", min_value=1, max_value=50, value=20)
        st.markdown("Select players for Team A (from paid members) or add manually (one per line)")
        paid_df = read_paid_list()
        member_choices = paid_df["Mobile_No"].tolist() if not paid_df.empty else []
        tA_sel = st.multiselect("Team A (select mobiles)", options=member_choices, default=[])
        tA_manual = st.text_area("Team A manual (one per line)")
        st.markdown("Select players for Team B")
        tB_sel = st.multiselect("Team B (select mobiles)", options=member_choices, default=[])
        tB_manual = st.text_area("Team B manual (one per line)")
        create_btn = st.form_submit_button("Create Match")
    if create_btn:
        def parse_manual(txt): return [x.strip() for x in txt.splitlines() if x.strip()]
        tA = [normalize_mobile(x) if any(ch.isdigit() for ch in x) else x for x in list(tA_sel) + parse_manual(tA_manual)]
        tB = [normalize_mobile(x) if any(ch.isdigit() for ch in x) else x for x in list(tB_sel) + parse_manual(tB_manual)]
        def dedup(seq):
            out=[]; seen=set()
            for s in seq:
                if s and s not in seen: out.append(s); seen.add(s)
            return out
        tA = dedup(tA); tB = dedup(tB)
        if set(tA).intersection(set(tB)):
            st.error("Duplicate players found in both teams.")
        elif not title or not tA or not tB:
            st.error("Provide title and players for both teams.")
        else:
            mid = datetime.now().strftime("%Y%m%d")+"-"+uuid.uuid4().hex[:6].upper()
            matches[mid] = {"title": title, "venue": venue, "overs": int(overs), "teamA": tA, "teamB": tB, "created_at": datetime.now().isoformat()}
            save_matches_index(matches)
            init_match_state_full(mid, title, overs, tA, tB, venue=venue)
            st.success(f"Match created: {title} ({mid})")

    st.markdown("### Existing Matches")
    if matches:
        for k, info in sorted(matches.items(), key=lambda x: x[0], reverse=True):
            st.write(f"- **{info.get('title')}** ({k}) — Overs: {info.get('overs')} — Created: {info.get('created_at')}")
            if role == "admin":
                if st.button(f"Delete {k}", key=f"del_{k}"):
                    matches.pop(k, None); save_matches_index(matches)
                    try: os.remove(match_state_path(k))
                    except: pass
                    st.success("Match deleted")
    else:
        st.info("No matches.")

# ---------------- Live Scorer ----------------
if menu == "Live Scorer":
    cm = current_member()
    role = get_role_from_mobile(cm["Mobile"]) if cm else "guest"
    if role not in ["member","admin"]:
        st.warning("Scoring available to paid members only.")
        st.stop()
    matches = load_matches_index()
    if not matches:
        st.info("No matches found. Create one.")
        st.stop()
    mid = st.selectbox("Select Match", options=list(matches.keys()), format_func=lambda x: f"{x} — {matches[x]['title']}")
    state = load_match_state(mid)
    if not state:
        st.error("Match state missing."); st.stop()

    st.markdown(f"## {matches[mid]['title']} — Scoring")
    bat = state.get("bat_team","Team A")
    sc = state["score"][bat]
    st.write(f"**{bat}**: {sc['runs']}/{sc['wkts']} ({sc['balls']} balls)")

    # --- START: CrickPro-style Scorecard + Summary (Live Scorer) ---
    overs_decimal = sc["balls"]//6 + (sc["balls"]%6)/10
    rr = (sc["runs"]/(sc["balls"]/6)) if sc["balls"] else 0.0

    st.markdown(f"""
    <div style='background:#0b6efd;padding:18px;border-radius:12px;text-align:center;color:white;margin-bottom:18px;'>
      <div style='font-size:38px;font-weight:900;'>{bat}: {sc['runs']}/{sc['wkts']}</div>
      <div style='font-size:16px;margin-top:6px;'>Overs: {sc['balls']//6}.{sc['balls']%6} &nbsp; • &nbsp; Run Rate: {rr:.2f}</div>
    </div>
    """, unsafe_allow_html=True)

    striker = state["batting"].get("striker","")
    non_striker = state["batting"].get("non_striker","")
    bowler = state["bowling"].get("current_bowler","")

    s_stats = state.get("batsman_stats", {}).get(striker, {"R":0,"B":0})
    ns_stats = state.get("batsman_stats", {}).get(non_striker, {"R":0,"B":0})
    bw_stats = state.get("bowler_stats", {}).get(bowler, {"B":0,"R":0,"W":0})

    st.markdown(f"""
    <div style='display:flex;gap:16px;justify-content:flex-start;margin:12px 0;flex-wrap:wrap;'>
      <div style='background:#f8fafc;padding:12px;border-radius:10px;min-width:220px;'>
        <div style='font-size:12px;color:#555;'>STRIKER</div>
        <div style='font-size:18px;font-weight:700;margin-top:6px;'>{striker or "-"}</div>
        <div style='font-size:13px;color:#333;margin-top:6px;'>{s_stats.get("R",0)} runs • {s_stats.get("B",0)} balls</div>
      </div>
      <div style='background:#f8fafc;padding:12px;border-radius:10px;min-width:220px;'>
        <div style='font-size:12px;color:#555;'>NON-STRIKER</div>
        <div style='font-size:18px;font-weight:700;margin-top:6px;'>{non_striker or "-"}</div>
        <div style='font-size:13px;color:#333;margin-top:6px;'>{ns_stats.get("R",0)} runs • {ns_stats.get("B",0)} balls</div>
      </div>
      <div style='background:#f8fafc;padding:12px;border-radius:10px;min-width:220px;'>
        <div style='font-size:12px;color:#555;'>BOWLER</div>
        <div style='font-size:18px;font-weight:700;margin-top:6px;'>{bowler or "-"}</div>
        <div style='font-size:13px;color:#333;margin-top:6px;'>{bw_stats.get("B",0)//6}.{bw_stats.get("B",0)%6} overs • {bw_stats.get("R",0)} runs • {bw_stats.get("W",0)} wkts</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    # --- END: CrickPro-style Scorecard + Summary (Live Scorer) ---

    # scorer lock
    user_mobile = normalize_mobile(cm["Mobile"])
    lock = state.get("scorer_lock", {})
    if lock and lock.get("locked_by") and lock.get("locked_by") != user_mobile:
        st.warning(f"Scoring locked by {lock.get('locked_by')} until {lock.get('expires_at')}")
        st.stop()
    else:
        if not lock or not lock.get("locked_by"):
            if st.button("Acquire Scorer Lock"):
                ok = try_acquire_scorer_lock(state, mid, user_mobile)
                if ok:
                    st.success("Lock acquired for 15 minutes"); st.rerun()
                else:
                    st.error("Could not acquire lock")
        else:
            st.info(f"You hold the lock until {lock.get('expires_at')}")
            c1, c2 = st.columns([1,1])
            if c1.button("Extend Lock"):
                state["scorer_lock"]["expires_at"] = (datetime.utcnow()+timedelta(minutes=15)).isoformat()
                save_match_state(mid, state); st.success("Lock extended"); st.rerun()
            if c2.button("Release Lock"):
                release_scorer_lock(state, mid, user_mobile); st.success("Lock released"); st.rerun()

    # set striker/non-striker/bowler
    teams = state.get("teams", {})
    bat_team = state.get("bat_team","Team A")
    team_list = teams.get(bat_team, [])
    opp_team = "Team B" if bat_team=="Team A" else "Team A"
    cols = st.columns(3)
    with cols[0]:
        try: idx0 = team_list.index(state["batting"].get("striker",""))
        except: idx0 = 0
        striker_select = st.selectbox("Striker", options=team_list, index=idx0)
    with cols[1]:
        try: idx1 = team_list.index(state["batting"].get("non_striker",""))
        except: idx1 = 0
        non_striker_select = st.selectbox("Non-Striker", options=team_list, index=idx1)
    with cols[2]:
        bowler_select = st.selectbox("Bowler", options=teams.get(opp_team, []))
    if st.button("Set Players for Over"):
        state["batting"]["striker"]=striker_select; state["batting"]["non_striker"]=non_striker_select
        state["bowling"]["current_bowler"]=bowler_select
        save_match_state(mid, state); st.success("Players set"); st.rerun()

    # scoring pad (styled buttons)
    st.markdown("### Scoring Pad")
    pad_rows = [["0","1","2"],["3","4","6"],["W","WD","NB"],["BY","LB","0NB"]]
    for r in pad_rows:
        cols = st.columns(len(r))
        for i,v in enumerate(r):
            if cols[i].button(v, key=f"pad_{v}"):
                if v == "0NB":
                    record_ball_full(state, mid, "NB", extras={"runs_off_bat":0})
                else:
                    record_ball_full(state, mid, v)
                st.success(f"Recorded {v}"); st.rerun()
    if st.button("Undo Last Ball"):
        ok = undo_last_ball_full(state, mid)
        if ok:
            st.success("Undo successful"); st.rerun()
        else:
            st.warning("No ball to undo")

    # last balls with photo & name
    st.markdown("### Last 12 balls")
    mems_df = read_members()
    for e in state.get("balls_log", [])[-12:][::-1]:
        out = e.get("outcome"); s = e.get("striker"); b = e.get("bowler")
        display = s; photo = None
        if s and any(ch.isdigit() for ch in s):
            s_norm = normalize_mobile(s)
            row = mems_df[mems_df["Mobile"]==s_norm]
            if not row.empty:
                display = row.iloc[0]["Name"]; photo = get_member_photo_path(row.iloc[0]["MemberID"])
        c1, c2 = st.columns([1,9])
        if photo:
            try: c1.image(photo, width=48)
            except: c1.write("")
        else:
            c1.write("")
        c2.write(f"**{display}** — {out} — {b}")

    st.markdown("### Commentary (recent)")
    for txt in state.get("commentary", [])[-20:][::-1]:
        st.markdown(f"<div style='background:#f1f5f9;padding:8px;border-radius:8px;margin-bottom:6px;'>{txt}</div>", unsafe_allow_html=True)

    # End innings / End match / Export
    c1, c2, c3 = st.columns([1,1,1])
    if c1.button("End Innings"):
        if state.get("status") == "INNINGS1":
            state["status"] = "INNINGS2"; state["innings"] = 2
            state["bat_team"] = "Team B" if state["bat_team"] == "Team A" else "Team A"
        else:
            state["status"] = "COMPLETED"
        save_match_state(mid, state); st.success("Innings switched/ended"); st.rerun()
    if c2.button("End Match"):
        state["status"] = "COMPLETED"; save_match_state(mid, state); st.success("Match marked completed"); st.rerun()
    if c3.button("Download Match JSON"):
        st.download_button("Download JSON", data=export_match_json(state), file_name=f"match_{mid}.json", mime="application/json")

    # CSV export
    csv_bytes = export_match_csv(state)
    st.download_button("Download Ball Log CSV", data=csv_bytes, file_name=f"match_{mid}_balls.csv", mime="text/csv")

# ---------------- Live Score (Public) ----------------
if menu == "Live Score (Public)":
    matches = load_matches_index()
    if not matches:
        st.info("No matches"); st.stop()
    mid = st.selectbox("Select Match", options=list(matches.keys()), format_func=lambda x: f"{x} — {matches[x]['title']}")
    state = load_match_state(mid)
    if not state:
        st.error("Match state missing"); st.stop()
    if HAS_AUTORE:
        st_autorefresh(interval=3000, key=f"auto_{mid}")
    st.markdown(f"### {matches[mid]['title']}")
    bat = state.get("bat_team","Team A")
    sc = state["score"][bat]
    st.write(f"{bat}: {sc['runs']}/{sc['wkts']} ({sc['balls']} balls)")

    # --- START: CrickPro-style Scorecard + Summary (Public) ---
    overs_decimal = sc["balls"]//6 + (sc["balls"]%6)/10
    rr = (sc["runs"]/(sc["balls"]/6)) if sc["balls"] else 0.0

    st.markdown(f"""
    <div style='background:#0b6efd;padding:18px;border-radius:12px;text-align:center;color:white;margin-bottom:18px;'>
      <div style='font-size:34px;font-weight:900;'>{bat}: {sc['runs']}/{sc['wkts']}</div>
      <div style='font-size:14px;margin-top:6px;'>Overs: {sc['balls']//6}.{sc['balls']%6} &nbsp; • &nbsp; Run Rate: {rr:.2f}</div>
    </div>
    """, unsafe_allow_html=True)

    striker = state["batting"].get("striker","")
    non_striker = state["batting"].get("non_striker","")
    bowler = state["bowling"].get("current_bowler","")

    s_stats = state.get("batsman_stats", {}).get(striker, {"R":0,"B":0})
    ns_stats = state.get("batsman_stats", {}).get(non_striker, {"R":0,"B":0})
    bw_stats = state.get("bowler_stats", {}).get(bowler, {"B":0,"R":0,"W":0})

    st.markdown(f"""
    <div style='display:flex;gap:12px;justify-content:flex-start;margin:12px 0;flex-wrap:wrap;'>
      <div style='background:#ffffff;padding:10px;border-radius:10px;min-width:200px;'>
        <div style='font-size:12px;color:#555;'>STRIKER</div>
        <div style='font-size:16px;font-weight:700;margin-top:6px;'>{striker or "-"}</div>
        <div style='font-size:12px;color:#333;margin-top:6px;'>{s_stats.get("R",0)} runs • {s_stats.get("B",0)} balls</div>
      </div>
      <div style='background:#ffffff;padding:10px;border-radius:10px;min-width:200px;'>
        <div style='font-size:12px;color:#555;'>NON-STRIKER</div>
        <div style='font-size:16px;font-weight:700;margin-top:6px;'>{non_striker or "-"}</div>
        <div style='font-size:12px;color:#333;margin-top:6px;'>{ns_stats.get("R",0)} runs • {ns_stats.get("B",0)} balls</div>
      </div>
      <div style='background:#ffffff;padding:10px;border-radius:10px;min-width:200px;'>
        <div style='font-size:12px;color:#555;'>BOWLER</div>
        <div style='font-size:16px;font-weight:700;margin-top:6px;'>{bowler or "-"}</div>
        <div style='font-size:12px;color:#333;margin-top:6px;'>{bw_stats.get("B",0)//6}.{bw_stats.get("B",0)%6} overs • {bw_stats.get("R",0)} runs • {bw_stats.get("W",0)} wkts</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    # --- END: CrickPro-style Scorecard + Summary (Public) ---

    st.markdown("### Last balls")
    mems_df = read_members()
    for e in state.get("balls_log", [])[-12:][::-1]:
        out = e.get("outcome"); s = e.get("striker"); b = e.get("bowler")
        display = s; photo=None
        if s and any(ch.isdigit() for ch in s):
            s_norm = normalize_mobile(s)
            row = mems_df[mems_df["Mobile"]==s_norm]
            if not row.empty:
                display = row.iloc[0]["Name"]; photo=get_member_photo_path(row.iloc[0]["MemberID"])
        cols = st.columns([1,9])
        if photo:
            cols[0].image(photo, width=48)
        cols[1].write(f"**{display}** — {out} — {b}")
    st.markdown("### Commentary")
    for txt in state.get("commentary", [])[-12:][::-1]:
        st.markdown(f"<div style='background:#f8fafc;padding:8px;border-radius:8px;margin-bottom:6px;'>{txt}</div>", unsafe_allow_html=True)

# ---------------- Player Stats ----------------
if menu == "Player Stats":
    st.subheader("Player Statistics")
    matches = load_matches_index()
    stats = {}
    for mid in matches.keys():
        s = load_match_state(mid)
        for name, vals in s.get("batsman_stats", {}).items():
            rec = stats.setdefault(name, {"R":0,"B":0,"4":0,"6":0})
            rec["R"] += vals.get("R",0); rec["B"] += vals.get("B",0); rec["4"] += vals.get("4",0); rec["6"] += vals.get("6",0)
    if not stats:
        st.info("No data")
    else:
        df = pd.DataFrame.from_dict(stats, orient="index").reset_index().rename(columns={"index":"Player"})
        df["SR"] = (df["R"]/df["B"].replace(0,1))*100
        st.dataframe(df.sort_values("R", ascending=False))
        top = df.sort_values("R", ascending=False).head(10)
        fig, ax = plt.subplots()
        ax.barh(top["Player"], top["R"])
        ax.invert_yaxis()
        ax.set_xlabel("Runs")
        st.pyplot(fig)

# ---------------- Admin Panel ----------------
if menu == "Admin":
    cmember = current_member()
    if not cmember or normalize_mobile(cmember.get("Mobile")) != normalize_mobile(ADMIN_PHONE):
        st.warning("Admin only — login with admin mobile to access.")
        st.stop()
    st.subheader("Admin Panel — Manage Paid Members & Registry")
    st.markdown("### Upload Paid Members list (CSV/XLSX)")
    up = st.file_uploader("Upload paid list", type=["csv","xlsx"])
    if up:
        try:
            if up.name.endswith(".csv"):
                df = pd.read_csv(up, dtype=str)
            else:
                df = pd.read_excel(up, engine="openpyxl", dtype=str)
            if "Mobile_No" not in df.columns:
                df.columns = ["Mobile_No"]
            df["Mobile_No"] = df["Mobile_No"].apply(normalize_mobile)
            df = df[df["Mobile_No"]!=""].drop_duplicates()
            write_paid_list(df)
            st.success("Paid list uploaded")
            result = sync_paid_with_registry()
            st.info(f"Registry updated: {result['updated_count']} members marked Paid.")
            if result["unmatched"]:
                st.warning(f"{len(result['unmatched'])} paid mobiles not found in registry. They are: {', '.join(result['unmatched'][:10])}")
        except Exception as e:
            st.error(f"Upload failed: {e}")

    st.markdown("### Manual Add / Delete Paid Members")
    add_m = st.text_input("Add Paid Mobile (10 digits)", key="admin_add_paid")
    if st.button("Add Paid Member"):
        m = normalize_mobile(add_m)
        if m:
            df = read_paid_list()
            if m in df["Mobile_No"].tolist():
                st.info("Already exists")
            else:
                df = pd.concat([df, pd.DataFrame({"Mobile_No":[m]})], ignore_index=True)
                write_paid_list(df); st.success("Added to paid list")
    dfp = read_paid_list()
    if not dfp.empty:
        del_m = st.selectbox("Select Paid to delete", dfp["Mobile_No"].tolist(), key="admin_del_select")
        if st.button("Delete Selected Paid"):
            df2 = dfp[dfp["Mobile_No"]!=del_m]; write_paid_list(df2); st.success("Deleted")
    else:
        st.info("Paid list empty")

    st.markdown("### Sync Paid list with Registry")
    if st.button("Sync paid list -> members.csv"):
        res = sync_paid_with_registry()
        st.success(f"Sync done. {res['updated_count']} registry members updated. {len(res['unmatched'])} unmatched mobiles.")
        if res["unmatched"]:
            st.warning("Unmatched examples: " + ", ".join(res["unmatched"][:10]))

    st.markdown("### Paid list preview (with registry match)")
    paid_df = read_paid_list(); mems = read_members()
    if not paid_df.empty:
        merged = paid_df.merge(mems, left_on="Mobile_No", right_on="Mobile", how="left")
        st.dataframe(merged[["Mobile_No","MemberID","Name"]].fillna("-"))
    else:
        st.info("No paid mobiles")

    st.markdown("### Member registry")
    st.dataframe(mems)

# ---------------- Footer ----------------
st.markdown("---")
st.markdown("Note: Login by mobile only. Admin mobile is restricted. Photos stored in `data/photos/`. To embed scoreboard in OBS use `?mid=<id>&embed=1`.")
