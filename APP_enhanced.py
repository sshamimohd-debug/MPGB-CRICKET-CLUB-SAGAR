# APP_enhanced.py
# MPGB Cricket Club - Sagar (Enhanced)
# Features: commentary fixes, scoreboard + target, responsive selectors, auto result, MOTM

import streamlit as st
import pandas as pd
import json, os, uuid, io, random
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

# optional autorefresh
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTORE = True
except Exception:
    HAS_AUTORE = False

# ---------------- Config ----------------
DATA_DIR = "data"
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
MEMBERS_CSV = os.path.join(DATA_DIR, "members.csv")
PAID_CSV = os.path.join(DATA_DIR, "Members_Paid.csv")
MATCH_INDEX = os.path.join(DATA_DIR, "matches_index.json")
ADMIN_PHONE = "8931883300"  # edit if needed
LOGO_PATH = os.path.join(DATA_DIR, "logo.png")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# ---------------- Commentary templates ----------------
RUN_TEMPLATES = [
    "Quick push and a run taken.",
    "Good placement and a quick run.",
    "Worked away for a couple.",
    "Nice timing, they'll take two.",
    "Smart running between the wickets.",
    "Pushed away for a run."
]

WICKET_TEMPLATES = [
    "Clean bowled! That's a beauty.",
    "Caught — taken safely.",
    "LBW! The umpire raises his finger.",
    "Edge and taken — batsman walks.",
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
    if default is None: default = {}
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

def format_over_ball(total_balls):
    if not total_balls:
        return "0.0"
    over_num = total_balls // 6
    ball_in_over = total_balls % 6
    return f"{over_num}.{ball_in_over}"

# ---------------- Files: members, paid, matches ----------------
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
        st.error(f"Error saving members: {e}")

def next_member_id():
    df = read_members()
    if df.empty: return "M001"
    try:
        nums = [int(x.lstrip("M")) for x in df["MemberID"].dropna().tolist() if str(x).startswith("M")]
        mx = max(nums) if nums else 0
    except:
        mx = 0
    return f"M{(mx+1):03d}"

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

# ---------------- Matches state ----------------
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
        "batting": {"striker": teamA[0] if len(teamA)>0 else "", "non_striker": teamA[1] if len(teamA)>1 else "", "order": teamA[:], "next_index": 2},
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

# ---------------- Commentary ----------------
def pick_commentary(outcome, striker, bowler, extras=None):
    extras = extras or {}
    striker = striker or "Batsman"
    bowler = bowler or "Bowler"
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

# ---------------- Safe rerun ----------------
def safe_rerun():
    try:
        st.experimental_rerun()
    except Exception:
        return

# ---------------- ID card generation ----------------
def generate_id_card_image(member):
    """
    Return BytesIO object containing PNG ID card (simple design).
    """
    w, h = 600, 360
    img = Image.new("RGB", (w,h), color=(255,255,255))
    draw = ImageDraw.Draw(img)
    # fonts: use default PIL fonts for portability
    try:
        f_b = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        f_m = ImageFont.truetype("DejaVuSans.ttf", 16)
    except:
        f_b = ImageFont.load_default()
        f_m = ImageFont.load_default()
    # logo box
    draw.rectangle([20,20,100,100], fill=(11,110,253))
    draw.text((28,42), "MPGB", fill=(255,255,255), font=f_b)
    # name
    nm = member.get("Name","-")
    mob = member.get("Mobile","-")
    mid = member.get("MemberID","-")
    draw.text((130,30), nm, fill=(0,0,0), font=f_b)
    draw.text((130,70), f"ID: {mid}", fill=(0,0,0), font=f_m)
    draw.text((130,100), f"Mobile: {mob}", fill=(0,0,0), font=f_m)
    draw.text((20,130), "MPGB Cricket Club - Sagar", fill=(0,0,0), font=f_m)
    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out

# ---------------- Scoring function (robust, enforces overs & all-out) ----------------
def record_ball_full(state, mid, outcome, extras=None, wicket_info=None):
    if extras is None: extras = {}

    if state.get("status") == "COMPLETED":
        return {"stopped": True, "reason": "Match already completed"}

    bat_team = state["bat_team"]
    sc = state["score"][bat_team]
    striker = state["batting"].get("striker","")
    non_striker = state["batting"].get("non_striker","")
    bowler = state["bowling"].get("current_bowler","") or "Unknown"

    if state.get("status") not in ("INNINGS1","INNINGS2"):
        return {"stopped": True, "reason": "Innings not active"}

    team_players = state.get("teams", {}).get(bat_team, [])
    team_size = max(0, len(team_players))

    entry = {
        "time": datetime.utcnow().isoformat(),
        "outcome": outcome,
        "extras": extras,
        "wicket": wicket_info,
        "striker": striker,
        "non_striker": non_striker,
        "bowler": bowler,
        "prev_score": sc.copy(),
        "prev_batsman": {
            striker: state.get("batsman_stats", {}).get(striker, {}).copy(),
            non_striker: state.get("batsman_stats", {}).get(non_striker, {}).copy()
        },
        "prev_bowler": {bowler: state.get("bowler_stats", {}).get(bowler, {}).copy()}
    }

    state.setdefault("batsman_stats", {})
    state.setdefault("bowler_stats", {})
    state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})
    state["batsman_stats"].setdefault(non_striker, {"R":0,"B":0,"4":0,"6":0})
    state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})

    def legal_ball_increment():
        state["bowler_stats"][bowler]["B"] = state["bowler_stats"][bowler].get("B",0) + 1
        sc["balls"] = sc.get("balls",0) + 1

    o = str(outcome)

    if o in ["0","1","2","3","4","6"]:
        runs = int(o)
        state["batsman_stats"][striker]["R"] += runs
        state["batsman_stats"][striker]["B"] += 1
        if runs == 4: state["batsman_stats"][striker]["4"] = state["batsman_stats"][striker].get("4",0) + 1
        if runs == 6: state["batsman_stats"][striker]["6"] = state["batsman_stats"][striker].get("6",0) + 1
        legal_ball_increment()
        state["bowler_stats"][bowler]["R"] += runs
        sc["runs"] = sc.get("runs",0) + runs
        if runs % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker

    elif o in ["W","Wicket"]:
        state["batsman_stats"][striker]["B"] += 1
        legal_ball_increment()
        state["bowler_stats"][bowler]["B"] += 1
        state["bowler_stats"][bowler]["W"] = state["bowler_stats"][bowler].get("W",0) + 1
        sc["wkts"] = sc.get("wkts",0) + 1
        nxt = state["batting"].get("next_index",0)
        order = state["batting"].get("order",[])
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
            state["batsman_stats"].setdefault(next_player, {"R":0,"B":0,"4":0,"6":0})

    elif o in ["WD","Wide"]:
        add = int(extras.get("runs",1))
        state["bowler_stats"][bowler]["R"] += add
        sc["runs"] = sc.get("runs",0) + add

    elif o in ["NB","NoBall"]:
        offbat = int(extras.get("runs_off_bat",0))
        add = 1 + offbat
        state["bowler_stats"][bowler]["R"] += add
        sc["runs"] = sc.get("runs",0) + add
        if offbat > 0:
            state["batsman_stats"][striker]["R"] += offbat

    elif o in ["BY","LB","Bye","LegBye"]:
        add = int(extras.get("runs",1))
        state["batsman_stats"][striker]["B"] += 1
        legal_ball_increment()
        state["bowler_stats"][bowler]["B"] += 1
        sc["runs"] = sc.get("runs",0) + add
        if add % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker

    else:
        # default dot
        state["batsman_stats"][striker]["B"] += 1
        legal_ball_increment()
        state["bowler_stats"][bowler]["B"] += 1

    entry["post_score"] = sc.copy()
    state.setdefault("balls_log", []).append(entry)

    comment_text = pick_commentary(o, striker, bowler, extras)
    state.setdefault("commentary", []).append(format_over_ball(sc.get("balls",0)) + " — " + comment_text)

    # End of innings checks
    overs_limit = int(state.get("overs_limit",0) or 0)
    overs_reached = False
    all_out = False
    if overs_limit > 0:
        if sc.get("balls",0) >= overs_limit * 6:
            overs_reached = True
    if team_size > 0:
        if sc.get("wkts",0) >= max(0, team_size - 1):
            all_out = True

    if overs_reached or all_out:
        if state.get("status") == "INNINGS1":
            state["status"] = "INNINGS2"
            state["innings"] = 2
            state["bat_team"] = "Team B" if state.get("bat_team")=="Team A" else "Team A"
            # do not auto-set striker: scorer should set players for new innings
        else:
            state["status"] = "COMPLETED"

    save_match_state(mid, state)
    return entry

# ---------------- Undo last ball ----------------
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

# ---------------- Export ----------------
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

# banner
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
# load logo
logo_html = ""
if os.path.exists(LOGO_PATH):
    import base64
    try:
        logo_bytes = open(LOGO_PATH,"rb").read()
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

# button style
st.markdown("""
<style>
div.stButton > button:first-child {
    background-color:#0b6efd !important;
    color: white !important;
    border-radius: 8px !important;
    height:42px !important;
    min-width:64px !important;
    font-size:16px !important;
    font-weight:700 !important;
    box-shadow: 0 6px 14px rgba(11,110,253,0.18);
}
</style>
""", unsafe_allow_html=True)

# ---------------- Sidebar: member card & id ----------------
def current_member():
    mid = st.session_state.get("MemberID","")
    if not mid: return None
    df = read_members()
    row = df[df["MemberID"] == mid]
    if row.empty: return None
    return row.iloc[0].to_dict()

st.sidebar.title("Member")
mem = current_member()
if mem:
    st.sidebar.markdown("### Member Card")
    st.sidebar.markdown(f"**ID:** {mem.get('MemberID')}")
    st.sidebar.markdown(f"**Name:** {mem.get('Name')}")
    st.sidebar.markdown(f"**Mobile:** {mem.get('Mobile')}")
    st.sidebar.markdown(f"**Paid:** {mem.get('Paid')}")
    ppath = None
    # photo path if exists (MemberID)
    for ext in ["png","jpg","jpeg"]:
        p = os.path.join(PHOTOS_DIR, f"{mem.get('MemberID')}.{ext}")
        if os.path.exists(p):
            ppath = p; break
    if ppath:
        try: st.sidebar.image(ppath, width=120)
        except: pass

    # Safe ID bytes creation (robust)
    id_bytes = None
    try:
        buf = generate_id_card_image(mem)
        if hasattr(buf, "getvalue"):
            id_bytes = io.BytesIO(buf.getvalue())
        else:
            id_bytes = io.BytesIO(buf)
    except Exception:
        # fallback placeholder
        placeholder = Image.new("RGB", (600,360), color=(255,255,255))
        d = ImageDraw.Draw(placeholder)
        try:
            f = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        except:
            f = ImageFont.load_default()
        d.text((20,20), f"MPGB ID\n{mem.get('Name','-')}", fill=(0,0,0), font=f)
        tmp = io.BytesIO(); placeholder.save(tmp, format="PNG"); tmp.seek(0)
        id_bytes = tmp

    if id_bytes:
        st.sidebar.download_button("Download ID Card (PNG)", data=id_bytes.getvalue(), file_name=f"{mem.get('MemberID')}_ID.png", mime="image/png")

    if st.sidebar.button("Logout"):
        st.session_state.pop("MemberID", None); safe_rerun()
else:
    st.sidebar.info("Guest — go to Menu -> Login / Register")

# ---------------- Sidebar menu ----------------
menu = st.sidebar.selectbox("Menu", ["Home","Login / Register","Match Setup","Live Scorer","Live Score (Public)","Player Stats","Admin"])

# ---------------- Pages ----------------
if menu == "Home":
    st.header("Welcome to MPGB Cricket Club - Sagar")
    st.write("Use Menu to create matches and score. Login/Register to access member features.")

# ---------------- Login / Register ----------------
if menu == "Login / Register":
    st.header("Login / Register")
    login_mobile = st.text_input("Enter mobile (10 digits)", key="ui_login_mobile")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            mnorm = normalize_mobile(login_mobile)
            if not mnorm:
                st.error("Please enter valid mobile.")
            else:
                mems = read_members()
                if mnorm in mems["Mobile"].tolist():
                    row = mems[mems["Mobile"]==mnorm].iloc[0]
                    st.session_state["MemberID"] = row["MemberID"]
                    if is_mobile_paid(mnorm := normalize_mobile(mnorm)):
                        st.success(f"Logged in as {row['Name']} — Paid")
                    else:
                        st.success(f"Logged in as {row['Name']} — Not Verified")
                    safe_rerun()
                else:
                    st.info("Mobile not registered. Please register below.")
    with col2:
        if st.button("Check Verification Status"):
            if is_mobile_paid(login_mobile):
                st.success("Status: VERIFIED — membership paid")
            else:
                st.warning("Status: NOT VERIFIED — contact admin.")
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
                    st.info("Mobile already registered.")
                else:
                    nid = next_member_id()
                    new = pd.DataFrame([{"MemberID": nid, "Name": rname.strip(), "Mobile": mnorm, "Paid":"N"}])
                    write_members(pd.concat([mems, new], ignore_index=True))
                    if rphoto: 
                        try:
                            image = Image.open(rphoto).convert("RGB")
                            ext = rphoto.name.split(".")[-1].lower()
                            if ext not in ["png","jpg","jpeg"]: ext = "png"
                            path = os.path.join(PHOTOS_DIR, f"{nid}.{ext}")
                            image.save(path)
                        except:
                            pass
                    st.success(f"Registered. Member ID: {nid}")
                    st.session_state["MemberID"] = nid
                    safe_rerun()

# ---------------- Match Setup ----------------
if menu == "Match Setup":
    cm = current_member()
    role = "guest"
    if cm:
        role = "admin" if normalize_mobile(cm.get("Mobile","")) == normalize_mobile(ADMIN_PHONE) else ("member" if is_mobile_paid(cm.get("Mobile","")) else "guest")
    if role not in ["member","admin"]:
        st.warning("Match creation is for paid members only."); st.stop()
    st.subheader("Create / Manage Matches")
    matches = load_matches_index()
    with st.form("create_match", clear_on_submit=True):
        title = st.text_input("Match Title (e.g. Team A vs Team B)")
        venue = st.text_input("Venue (optional)")
        overs = st.number_input("Overs per innings", min_value=1, max_value=50, value=2)
        st.markdown("Select players for Team A (mobile numbers or names)")
        paid_df = read_paid_list()
        member_choices = paid_df["Mobile_No"].tolist() if not paid_df.empty else []
        tA_sel = st.multiselect("Team A (mobiles)", options=member_choices, default=[])
        tA_manual = st.text_area("Team A manual (one per line)")
        st.markdown("Select players for Team B")
        tB_sel = st.multiselect("Team B (mobiles)", options=member_choices, default=[])
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

    st.markdown("### Existing matches")
    if matches:
        for k, info in sorted(matches.items(), key=lambda x:x[0], reverse=True):
            st.write(f"- **{info.get('title')}** ({k}) — Overs: {info.get('overs')} — Created: {info.get('created_at')}")
            if role == "admin":
                if st.button(f"Delete {k}", key=f"del_{k}"):
                    matches.pop(k, None); save_matches_index(matches)
                    try: os.remove(match_state_path(k))
                    except: pass
                    st.success("Deleted")

# ---------------- Live Scorer ----------------
if menu == "Live Scorer":
    cm = current_member()
    role = "guest"
    if cm:
        role = "admin" if normalize_mobile(cm.get("Mobile","")) == normalize_mobile(ADMIN_PHONE) else ("member" if is_mobile_paid(cm.get("Mobile","")) else "guest")
    if role not in ["member","admin"]:
        st.warning("Scoring available to paid members only."); st.stop()
    matches = load_matches_index()
    if not matches:
        st.info("No matches found."); st.stop()
    mid = st.selectbox("Select Match", options=list(matches.keys()), format_func=lambda x: f"{x} — {matches[x]['title']}")
    state = load_match_state(mid)
    if not state:
        st.error("Match state missing."); st.stop()

    st.markdown(f"## {matches[mid]['title']} — Scoring")
    bat = state.get("bat_team","Team A")
    sc = state["score"][bat]
    st.write(f"Team {bat}: {sc.get('runs',0)}/{sc.get('wkts',0)} ({sc.get('balls',0)} balls)")

    # --- Enhanced scoreboard (includes target when chasing) ---
    overs_completed = sc.get("balls",0)
    overs_done = f"{overs_completed//6}.{overs_completed%6}"
    overs_limit = int(state.get("overs_limit",0) or 0)
    rr = (sc.get("runs",0) / (overs_completed/6)) if overs_completed>0 else 0.0

    target_info = ""
    if state.get("status") == "INNINGS2":
        other = "Team A" if state.get("bat_team")=="Team B" else "Team B"
        opp_runs = state["score"].get(other, {}).get("runs",0)
        target = opp_runs + 1
        runs_needed = max(0, target - sc.get("runs",0))
        balls_remaining = max(0, overs_limit*6 - sc.get("balls",0)) if overs_limit>0 else None
        req_rr = (runs_needed/(balls_remaining/6)) if balls_remaining and balls_remaining>0 else None
        req_str = f"{runs_needed} runs needed from {balls_remaining} balls" if balls_remaining is not None else f"{runs_needed} runs needed"
        req_rr_text = f" • Required RR: {req_rr:.2f}" if req_rr is not None else ""
        target_info = f"<div style='font-size:14px;color:#fff;opacity:0.95;margin-top:6px;'>Target: {target} • {req_str}{req_rr_text}</div>"

    st.markdown(f"""
    <div style='background:#0b6efd;padding:18px;border-radius:12px;text-align:center;color:white;margin-bottom:18px;'>
      <div style='font-size:34px;font-weight:900;'>{state.get('bat_team')}: {sc.get('runs',0)}/{sc.get('wkts',0)}</div>
      <div style='font-size:14px;margin-top:6px;'>Overs: {overs_done} &nbsp; • &nbsp; Run Rate: {rr:.2f}</div>
      {target_info}
    </div>
    """, unsafe_allow_html=True)

    # player cards + responsive selector row
    striker = state["batting"].get("striker","")
    non_striker = state["batting"].get("non_striker","")
    bowler = state["bowling"].get("current_bowler","")
    s_stats = state.get("batsman_stats", {}).get(striker, {"R":0,"B":0})
    ns_stats = state.get("batsman_stats", {}).get(non_striker, {"R":0,"B":0})
    bw_stats = state.get("bowler_stats", {}).get(bowler, {"B":0,"R":0,"W":0})

    st.markdown("""
    <style>
    .player-row { display:flex; gap:16px; align-items:flex-start; flex-wrap:nowrap; overflow-x:auto; padding-bottom:8px; }
    .player-card { background:#f8fafc;padding:12px;border-radius:10px;min-width:220px; flex:0 0 auto; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class='player-row'>
      <div class='player-card'>
        <div style='font-size:12px;color:#555;'>STRIKER</div>
        <div style='font-size:16px;font-weight:700;margin-top:6px;'>{striker or "-"}</div>
        <div style='font-size:12px;color:#333;margin-top:6px;'>{s_stats.get("R",0)} runs • {s_stats.get("B",0)} balls</div>
      </div>
      <div class='player-card'>
        <div style='font-size:12px;color:#555;'>NON-STRIKER</div>
        <div style='font-size:16px;font-weight:700;margin-top:6px;'>{non_striker or "-"}</div>
        <div style='font-size:12px;color:#333;margin-top:6px;'>{ns_stats.get("R",0)} runs • {ns_stats.get("B",0)} balls</div>
      </div>
      <div class='player-card'>
        <div style='font-size:12px;color:#555;'>BOWLER</div>
        <div style='font-size:16px;font-weight:700;margin-top:6px;'>{bowler or "-"}</div>
        <div style='font-size:12px;color:#333;margin-top:6px;'>{bw_stats.get("B",0)//6}.{bw_stats.get("B",0)%6} overs • {bw_stats.get("R",0)} runs • {bw_stats.get("W",0)} wkts</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # scorer lock & controls
    user_mobile = normalize_mobile(cm["Mobile"]) if cm else ""
    lock = state.get("scorer_lock", {})
    lock_owner = lock.get("locked_by") if lock else None

    if lock and lock_owner and lock_owner != user_mobile:
        st.warning(f"Scoring locked by {lock_owner} until {lock.get('expires_at')}")
    else:
        if not lock or not lock_owner:
            if st.button("Acquire Scorer Lock"):
                ok = try_acquire_scorer_lock(state, mid, user_mobile)
                if ok:
                    st.success("Lock acquired for 15 minutes"); safe_rerun()
                else:
                    st.error("Could not acquire lock")
        else:
            st.info(f"You hold the lock until {lock.get('expires_at')}")
            c1, c2 = st.columns(2)
            if c1.button("Extend Lock"):
                state["scorer_lock"]["expires_at"] = (datetime.utcnow()+timedelta(minutes=15)).isoformat()
                save_match_state(mid, state); st.success("Lock extended"); safe_rerun()
            if c2.button("Release Lock"):
                release_scorer_lock(state, mid, user_mobile); st.success("Lock released"); safe_rerun()

    # selectors row
    team_list = state.get("teams", {}).get(state.get("bat_team","Team A"), [])
    opp_team = "Team B" if state.get("bat_team")=="Team A" else "Team A"
    opp_list = state.get("teams", {}).get(opp_team, [])
    cols = st.columns([3,3,3])
    with cols[0]:
        try:
            idx0 = team_list.index(state["batting"].get("striker",""))
        except:
            idx0 = 0
        striker_select = st.selectbox("Striker", options=team_list, index=idx0)
    with cols[1]:
        try:
            idx1 = team_list.index(state["batting"].get("non_striker",""))
        except:
            idx1 = 0
        non_striker_select = st.selectbox("Non-Striker", options=team_list, index=idx1)
    with cols[2]:
        try:
            idx2 = opp_list.index(state["bowling"].get("current_bowler",""))
        except:
            idx2 = 0
        bowler_select = st.selectbox("Bowler", options=opp_list, index=idx2)

    if st.button("Set Players for Over"):
        state["batting"]["striker"] = striker_select
        state["batting"]["non_striker"] = non_striker_select
        state["bowling"]["current_bowler"] = bowler_select
        save_match_state(mid, state); safe_rerun()

    # ---------------- Scoring Pad (guarded) ----------------
    lock_owner = state.get("scorer_lock", {}).get("locked_by")
    can_score = (state.get("status") in ("INNINGS1","INNINGS2")) and (lock_owner == user_mobile)
    if state.get("status") not in ("INNINGS1","INNINGS2"):
        st.info("Scoring disabled — innings not active or match completed.")
    elif lock_owner and lock_owner != user_mobile:
        st.warning(f"Scoring locked by {lock_owner}. You cannot score.")
    elif not lock_owner:
        st.info("Acquire scorer lock to start scoring.")
    else:
        # scoring pad
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
                    st.success(f"Recorded {v}"); safe_rerun()
        if st.button("Undo Last Ball"):
            ok = undo_last_ball_full(state, mid)
            if ok:
                st.success("Undo successful"); safe_rerun()
            else:
                st.warning("No ball to undo")

    # commentary (recent)
    st.markdown("### Commentary (recent)")
    for txt in state.get("commentary", [])[-20:][::-1]:
        st.markdown(f"<div style='background:#f1f5f9;padding:8px;border-radius:8px;margin-bottom:6px;'>{txt}</div>", unsafe_allow_html=True)

    # If match completed show result & summary & MOTM
    if state.get("status") == "COMPLETED":
        teamA = state["score"].get("Team A",{})
        teamB = state["score"].get("Team B",{})
        a_runs = teamA.get("runs",0); a_wkts = teamA.get("wkts",0)
        b_runs = teamB.get("runs",0); b_wkts = teamB.get("wkts",0)
        if a_runs > b_runs:
            result_text = f"Team A won by {a_runs - b_runs} runs"
        elif b_runs > a_runs:
            # compute wickets remaining
            teamB_players = len(state.get("teams", {}).get("Team B", []))
            wickets_remaining = max(0, (teamB_players - 1) - b_wkts) if teamB_players>0 else "-"
            result_text = f"Team B won by {wickets_remaining} wickets" if isinstance(wickets_remaining,int) else "Team B won"
        else:
            result_text = "Match tied"

        st.markdown(f"<div style='background:#e6ffed;border-left:6px solid #16a34a;padding:12px;border-radius:6px;margin-top:12px;'><b>Result:</b> {result_text}</div>", unsafe_allow_html=True)

        st.markdown("### Full Scorecard")
        def pretty(s): return f"{s.get('runs',0)}/{s.get('wkts',0)} ({format_over_ball(s.get('balls',0))})"
        st.write(f"Team A: {pretty(teamA)}")
        st.write(f"Team B: {pretty(teamB)}")

        # Man of the Match heuristic
        bats = state.get("batsman_stats", {})
        bowl = state.get("bowler_stats", {})
        top_bats = sorted([(p,vals.get("R",0), vals.get("6",0)) for p,vals in bats.items()], key=lambda x:(x[1],x[2]), reverse=True)
        top_bowl = sorted([(p,vals.get("W",0), vals.get("R",0)) for p,vals in bowl.items()], key=lambda x:(x[1], -x[2]), reverse=True)
        motm = None
        if top_bats:
            best_bat = top_bats[0]
            if top_bowl and top_bowl[0][1] >= max(3, best_bat[1]//15):
                motm = top_bowl[0][0]
            else:
                motm = best_bat[0]
        elif top_bowl:
            motm = top_bowl[0][0]
        if motm:
            st.markdown(f"### Man of the Match: **{motm}**")
        else:
            st.markdown("### Man of the Match: TBD")

        st.markdown("### Highlights")
        if top_bats:
            st.write(f"Top scorer: {top_bats[0][0]} — {top_bats[0][1]} runs")
        if top_bowl:
            st.write(f"Best bowling: {top_bowl[0][0]} — {top_bowl[0][1]} wkts")

    # Exports
    if st.button("Download Match JSON"):
        st.download_button("Download JSON", data=export_match_json(state), file_name=f"match_{mid}.json", mime="application/json")
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

    # compute target info same as scorer
    overs_completed = sc.get("balls",0)
    overs_done = f"{overs_completed//6}.{overs_completed%6}"
    rr = (sc.get("runs",0) / (overs_completed/6)) if overs_completed>0 else 0.0
    target_info = ""
    if state.get("status") == "INNINGS2":
        other = "Team A" if state.get("bat_team")=="Team B" else "Team B"
        opp_runs = state["score"].get(other, {}).get("runs",0)
        target = opp_runs + 1
        runs_needed = max(0, target - sc.get("runs",0))
        balls_remaining = max(0, int(state.get("overs_limit",0))*6 - sc.get("balls",0)) if int(state.get("overs_limit",0))>0 else None
        req_rr = (runs_needed/(balls_remaining/6)) if balls_remaining and balls_remaining>0 else None
        req_rr_text = f" • Required RR: {req_rr:.2f}" if req_rr is not None else ""
        target_info = f"<div style='font-size:14px;color:#fff;opacity:0.95;margin-top:6px;'>Target: {target} • {runs_needed} runs needed from {balls_remaining} balls{req_rr_text}</div>"

    st.markdown(f"""
    <div style='background:#0b6efd;padding:18px;border-radius:12px;text-align:center;color:white;margin-bottom:18px;'>
      <div style='font-size:34px;font-weight:900;'>{state.get('bat_team')}: {sc.get('runs',0)}/{sc.get('wkts',0)}</div>
      <div style='font-size:14px;margin-top:6px;'>Overs: {overs_done} &nbsp; • &nbsp; Run Rate: {rr:.2f}</div>
      {target_info}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### Score details")
    def pretty(s): return f"{s.get('runs',0)}/{s.get('wkts',0)} ({format_over_ball(s.get('balls',0))})"
    st.write(f"Team A: {pretty(state['score'].get('Team A',{}))}")
    st.write(f"Team B: {pretty(state['score'].get('Team B',{}))}")

    st.markdown("### Commentary")
    for txt in state.get("commentary", [])[-20:][::-1]:
        st.markdown(f"<div style='background:#f8fafc;padding:8px;border-radius:8px;margin-bottom:6px;'>{txt}</div>", unsafe_allow_html=True)

    if state.get("status") == "COMPLETED":
        st.success("Match completed — scoring closed.")

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

# ---------------- Admin ----------------
if menu == "Admin":
    cmember = current_member()
    if not cmember or normalize_mobile(cmember.get("Mobile")) != normalize_mobile(ADMIN_PHONE):
        st.warning("Admin only — login with admin mobile to access."); st.stop()
    st.subheader("Admin Panel")
    up = st.file_uploader("Upload paid list (CSV/XLSX)", type=["csv","xlsx"])
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
            res = sync_paid_with_registry()
            st.info(f"Registry updated: {res['updated_count']} members marked Paid.")
            if res["unmatched"]:
                st.warning(f"{len(res['unmatched'])} paid mobiles not found in registry.")
        except Exception as e:
            st.error(f"Upload failed: {e}")

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
    st.markdown("### Member registry")
    st.dataframe(read_members())

# ---------------- Footer ----------------
st.markdown("---")
st.markdown("Note: Login by mobile only. Photos stored in `data/photos/`. Admin mobile is restricted.")
