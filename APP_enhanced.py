# APP_enhanced.py - FINAL (MPGB Cricket Club - Sagar)
# Features: CrickPro-like scorer, commentary rules, autosave, auto innings end, MOTM etc.

import os, io, json, uuid, random
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

# optional auto-refresh
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
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
ADMIN_PHONE = "8931883300"  # change if needed
LOGO_PATH = os.path.join(DATA_DIR, "logo.png")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# ---------------- Commentary templates ----------------
RUN_TEMPLATES = [
    "Quick push and a run taken.",
    "Good placement and a run.",
    "Worked away for a couple.",
    "Nice timing, that'll be a quick two.",
    "Smart running between the wickets."
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
    "Crowd enjoying the contest."
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

def is_mobile_paid(mobile):
    m = normalize_mobile(mobile)
    if not m:
        return False
    try:
        paid_df = read_paid_list()
        if not paid_df.empty and m in paid_df['Mobile_No'].tolist():
            return True
    except Exception:
        pass
    try:
        members = read_members()
        if 'Mobile' in members.columns and 'Paid' in members.columns:
            rows = members[members['Mobile'] == m]
            if not rows.empty and str(rows.iloc[0].get('Paid','')).upper() == 'Y':
                return True
    except Exception:
        pass
    return False

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

def format_over_ball(total_balls):
    try:
        total_balls = int(total_balls or 0)
    except:
        total_balls = 0
    over_num = total_balls // 6
    ball_in_over = total_balls % 6
    return f"{over_num}.{ball_in_over}"

# Robust player comparison helper (used in wicket/new batsman logic)
def same_player(a, b):
    """Robust compare: names or mobile numbers (compare last 10 digits if digits present)."""
    if not a or not b:
        return False
    sa = str(a).strip()
    sb = str(b).strip()
    if any(ch.isdigit() for ch in sa) and any(ch.isdigit() for ch in sb):
        da = "".join([c for c in sa if c.isdigit()])
        db = "".join([c for c in sb if c.isdigit()])
        if len(da) >= 10 and len(db) >= 10:
            return da[-10:] == db[-10:]
        return da == db
    return sa.lower() == sb.lower()

def player_team(state, player_name):
    """Return team name ('Team A'/'Team B' or None) for a given player using state['teams']."""
    if not player_name:
        return None
    teams = state.get("teams", {})
    for tname, members in teams.items():
        for m in members:
            if same_player(m, player_name):
                return tname
    return None

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
    if df.empty:
        return "M001"
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

# ---------------- Finalize / Summary helpers ----------------
def compute_man_of_match(state):
    """
    Simple heuristic:
      - batsman score weight = runs
      - bowler score weight = wickets*25 + negative runs concession
    """
    best = None
    best_score = -10**9
    # batsmen
    for p,vals in state.get("batsman_stats", {}).items():
        runs = int(vals.get("R",0) or 0)
        score = runs
        if score > best_score:
            best_score = score; best = p
    # bowlers
    for p,vals in state.get("bowler_stats", {}).items():
        wk = int(vals.get("W",0) or 0)
        runs_conceded = int(vals.get("R",0) or 0)
        score = wk * 25 - (runs_conceded//10)
        if score > best_score:
            best_score = score; best = p
    return best or state.get("man_of_match_override","")

def save_final_scorecard_files(mid, state):
    """Save JSON and CSV snapshot in backups dir and return paths."""
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    base = os.path.join(BACKUP_DIR, f"match_{mid}_final_{ts}")
    json_path = base + ".json"
    csv_path = base + ".csv"
    # JSON
    save_json(json_path, state)
    # CSV (balls_log to flat csv)
    rows = []
    for b in state.get("balls_log", []):
        rows.append({
            "time": b.get("time"),
            "outcome": b.get("outcome"),
            "striker": b.get("striker"),
            "non_striker": b.get("non_striker"),
            "bowler": b.get("bowler"),
            "extras": json.dumps(b.get("extras", {}), ensure_ascii=False),
            "wicket": json.dumps(b.get("wicket", {}), ensure_ascii=False),
            "prev_runs": b.get("prev_score", {}).get("runs"),
            "post_runs": b.get("post_score", {}).get("runs")
        })
    try:
        df = pd.DataFrame(rows)
        df.to_csv(csv_path, index=False)
    except Exception:
        pass
    return json_path, csv_path

def finalize_match(mid, state):
    """
    Called when a match ends. Computes result, MOTM, saves files, updates matches index.
    """
    # compute final result
    if state.get("status") != "COMPLETED":
        state["status"] = "COMPLETED"
    ta = "Team A"; tb = "Team B"
    ra = int(state.get("score", {}).get(ta, {}).get("runs", 0) or 0)
    rb = int(state.get("score", {}).get(tb, {}).get("runs", 0) or 0)
    wa = int(state.get("score", {}).get(ta, {}).get("wkts", 0) or 0)
    wb = int(state.get("score", {}).get(tb, {}).get("wkts", 0) or 0)

    result_text = ""
    if ra == rb:
        result_text = "Match tied"
    else:
        # determine by runs/wickets
        if ra > rb:
            margin = ra - rb
            result_text = f"Team A won by {margin} runs"
        else:
            # Team B won — compute wickets remaining (approx)
            teamA_players = state.get("teams", {}).get("Team A", [])
            team_size = max(0, len(teamA_players))
            wkts_fallen = state.get("score", {}).get("Team B", {}).get("wkts", 0)
            wickets_remaining = max(0, team_size - 1 - wkts_fallen)
            result_text = f"Team B won by {wickets_remaining} wickets"

    motm_auto = compute_man_of_match(state)
    state["man_of_match_auto"] = motm_auto

    summary = {
        "result_text": result_text,
        "runs": {"Team A": ra, "Team B": rb},
        "wkts": {"Team A": wa, "Team B": wb},
        "man_of_match_auto": motm_auto,
        "completed_at": datetime.utcnow().isoformat()
    }
    state["final_summary"] = summary

    jpath, cpath = save_final_scorecard_files(mid, state)

    idx = load_matches_index()
    if mid in idx:
        idx[mid]["completed_at"] = summary["completed_at"]
        idx[mid]["final_summary_brief"] = {"result": result_text, "motm": motm_auto}
        save_matches_index(idx)

    save_match_state(mid, state)
    return summary

# ---------------- Scoring function ----------------
def record_ball_full(state, mid, outcome, extras=None, wicket_info=None):
    if extras is None:
        extras = {}

    if state.get("status") == "COMPLETED":
        return {"stopped": True, "reason": "Match already completed"}

    bat_team = state.get("bat_team", "Team A")
    sc = state["score"].get(bat_team, {"runs":0, "wkts":0, "balls":0})
    striker = state.get("batting", {}).get("striker","")
    non_striker = state.get("batting", {}).get("non_striker","")
    bowler = state.get("bowling", {}).get("current_bowler","") or "Unknown"

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
        if runs == 4:
            state["batsman_stats"][striker]["4"] = state["batsman_stats"][striker].get("4",0) + 1
        if runs == 6:
            state["batsman_stats"][striker]["6"] = state["batsman_stats"][striker].get("6",0) + 1
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
            state["bat_team"] = "Team B" if state.get("bat_team") == "Team A" else "Team A"
            # do not auto set striker; scorer should set players
        else:
            state["status"] = "COMPLETED"

    save_match_state(mid, state)
    return entry

# ---------------- Undo last ball ----------------
def undo_last_ball_full(state, mid):
    if not state.get("balls_log"):
        return False
    last = state["balls_log"].pop()
    state["score"][state.get("bat_team")] = last.get("prev_score", state["score"].get(state.get("bat_team"), {"runs":0,"wkts":0,"balls":0}))
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

# ---------------- UI ----------------
st.set_page_config(page_title="MPGB Cricket Club - Sagar", layout="wide")

# Banner
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

logo_html = ""
if os.path.exists(LOGO_PATH):
    try:
        import base64
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

# Button style
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

# Sidebar member card
def current_member():
    mid = st.session_state.get("MemberID","")
    if not mid:
        return None
    df = read_members()
    row = df[df["MemberID"] == mid]
    if row.empty:
        return None
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
    for ext in ["png","jpg","jpeg"]:
        p = os.path.join(PHOTOS_DIR, f"{mem.get('MemberID')}.{ext}")
        if os.path.exists(p):
            ppath = p; break
    if ppath:
        try: st.sidebar.image(ppath, width=120)
        except: pass

    # safe id generation
    id_bytes = None
    try:
        buf = generate_id_card_image(mem)
        if hasattr(buf, "getvalue"):
            id_bytes = io.BytesIO(buf.getvalue())
        else:
            id_bytes = io.BytesIO(buf)
    except Exception:
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

# Sidebar menu
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
                    normalized = normalize_mobile(mnorm)
                    try:
                        paid_flag = is_mobile_paid(normalized)
                    except Exception:
                        paid_flag = False
                    if paid_flag:
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
                            if ext not in ["png","jpg","jpeg"]:
                                ext = "png"
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
                if s and s not in seen:
                    out.append(s); seen.add(s)
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
    st.header("Live Scorer — Compact View (KDM-style)")

    st.markdown("""
    <style>
    .score-card {background: linear-gradient(90deg,#0b6efd,#055ecb);color:white;padding:18px;border-radius:12px;}
    .small-card {background:#fff;padding:12px;border-radius:10px;box-shadow:0 6px 20px rgba(2,6,23,0.06);}
    .btn-grid button{min-width:60px;height:44px;border-radius:8px;margin:3px;font-weight:700}
    .batsman-row{display:flex;justify-content:space-between;align-items:center;padding:8px 6px;border-bottom:1px solid #f1f5f9}
    </style>
    """, unsafe_allow_html=True)

    cm = current_member()
    if not cm:
        st.warning("स्कोर करने के लिए पहले login करें (Sidebar → Login).")
        st.stop()

    role = "admin" if normalize_mobile(cm.get("Mobile","")) == normalize_mobile(ADMIN_PHONE) else ("member" if is_mobile_paid(cm.get("Mobile","")) else "guest")
    if role not in ["member","admin"]:
        st.warning("Scoring के लिए paid member होना ज़रूरी है.")
        st.stop()

    matches = load_matches_index()
    if not matches:
        st.info("कोई मैच उपलब्ध नहीं है — पहले Match Setup में मैच बनाइए.")
        st.stop()

    mid = st.selectbox("Select Match", options=list(matches.keys()), format_func=lambda x: f"{x} — {matches[x]['title']}")
    state = load_match_state(mid)
    if not state:
        st.error("Match state लोड नहीं हो पाया — match state missing.")
        st.stop()

    # Auto-refresh every 25s (for viewers) — scorer actions call safe_rerun()
    if HAS_AUTORE:
        st_autorefresh(interval=25000, key=f"auto_{mid}")

    bat = state.get("bat_team","Team A")
    sc = state.get("score", {}).get(bat, {"runs":0,"wkts":0,"balls":0})
    other = "Team A" if bat == "Team B" else "Team B"
    opp_sc = state.get("score", {}).get(other, {"runs":0,"wkts":0,"balls":0})

    # If match completed show final scorecard and downloads
    if state.get("status") == "COMPLETED":
        st.success("Match completed — final scorecard available.")
        fs = state.get("final_summary", {})
        if fs:
            st.markdown(f"**Result:** {fs.get('result_text','')}")
            motm = fs.get("man_of_match_auto") or state.get("man_of_match_override","")
            if motm:
                st.markdown(f"**Man of the Match:** {motm}")
        # downloads
        try:
            json_bytes = export_match_json(state)
            csv_bytes = export_match_csv(state)
            st.download_button("Download final (JSON)", data=json_bytes, file_name=f"match_{mid}_final.json", mime="application/json")
            st.download_button("Download final (CSV)", data=csv_bytes, file_name=f"match_{mid}_final.csv", mime="text/csv")
        except Exception:
            pass

    col1, col2 = st.columns([2,1])
    with col1:
        st.markdown(f"<div class='score-card'>\n  <div style='font-size:28px;font-weight:900'>{state.get('title','Match')}</div>\n  <div style='font-size:22px;margin-top:8px'>{bat}: <span style='font-size:28px'>{sc.get('runs',0)}</span>/<span style='font-size:22px'>{sc.get('wkts',0)}</span></div>\n  <div style='font-size:14px;margin-top:6px'>Overs: {format_over_ball(sc.get('balls',0))} &nbsp; • &nbsp; RR: {((sc.get('runs',0)/(sc.get('balls',0)/6)) if sc.get('balls',0)>0 else 0):.2f}</div>\n</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='margin-top:8px' class='small-card'><strong>Opponent:</strong> {other} — {opp_sc.get('runs',0)}/{opp_sc.get('wkts',0)} ({format_over_ball(opp_sc.get('balls',0))})</div>", unsafe_allow_html=True)
    with col2:
        st.markdown("**Current Players**")
        br = state.get('batting',{})
        st.markdown(f"- Striker: **{br.get('striker','-')}**")
        st.markdown(f"- Non-striker: **{br.get('non_striker','-')}**")
        st.markdown(f"- Next index: **{br.get('next_index',0)}**")
        st.markdown("---")
        st.markdown("**Bowling**")
        st.markdown(f"- Current: **{state.get('bowling',{}).get('current_bowler','-')}**")
        st.markdown(f"- Last over: **{state.get('bowling',{}).get('last_over_bowler','-')}**")

    st.markdown("---")

    lock = state.get('scorer_lock', {})
    locked_by = lock.get('locked_by')
    colA, colB = st.columns([1,1])
    with colA:
        if locked_by and locked_by != normalize_mobile(cm.get('Mobile','')):
            st.warning(f"स्कोरर लॉक: यह मैच पहले से {locked_by} द्वारा लॉक है।")
        elif locked_by == normalize_mobile(cm.get('Mobile','')):
            st.success("आपके पास स्कोरर लॉक है।")
        else:
            if st.button("Acquire Lock"):
                ok = try_acquire_scorer_lock(state, mid, normalize_mobile(cm.get('Mobile','')))
                if ok:
                    st.experimental_rerun()
                else:
                    st.error("लॉक नहीं लिया जा सका।")
    with colB:
        if st.button("Release Lock"):
            ok = release_scorer_lock(state, mid, normalize_mobile(cm.get('Mobile','')))
            if ok:
                st.success("लॉक छोड़ा गया।")
                st.experimental_rerun()
            else:
                st.info("आपके पास लॉक नहीं था।")

    lock_ok = (not state.get('scorer_lock')) or (state.get('scorer_lock',{}).get('locked_by') == normalize_mobile(cm.get('Mobile','')))
    if not lock_ok:
        st.info("स्कोर करने से पहले Acquire Lock लें।")
        st.stop()

    # ---- Player & Bowler selector (paste this before Quick Actions block) ----
    # team batting now (bat) and other team (other) already defined above
    team_players = state.get('teams', {}).get(bat, [])[:]   # batting team order/names
    other_team_players = state.get('teams', {}).get(other, [])[:]  # potential bowlers

    # Make readable labels: if mobile numbers present, show last 4 or name
    def player_label(p):
        if not p: return "-"
        if any(ch.isdigit() for ch in str(p)) and len(str(p))>=4:
            s = str(p)
            return s if len(s)<=12 else (s[-10:])  # show last 10 digits
        return str(p)

    # Current on-field defaults
    cur_striker = state.get('batting',{}).get('striker','') or (team_players[0] if team_players else '')
    cur_non = state.get('batting',{}).get('non_striker','') or (team_players[1] if len(team_players)>1 else '')
    cur_bowler = state.get('bowling',{}).get('current_bowler','') or (other_team_players[0] if other_team_players else '')

    # UI selectors (unique keys per match)
    st.markdown("### Set On-field Players (required)")
    sel_col1, sel_col2, sel_col3 = st.columns(3)
    with sel_col1:
        striker_sel = st.selectbox("Striker", options=team_players, index=(team_players.index(cur_striker) if cur_striker in team_players else 0), key=f"striker_{mid}")
    with sel_col2:
        non_sel = st.selectbox("Non-striker", options=team_players, index=(team_players.index(cur_non) if cur_non in team_players else (1 if len(team_players)>1 else 0)), key=f"nonstriker_{mid}")
    with sel_col3:
        bowler_sel = st.selectbox("Current Bowler", options=other_team_players, index=(other_team_players.index(cur_bowler) if cur_bowler in other_team_players else 0), key=f"bowler_{mid}")

    # Save selections button
    if st.button("Set Players / Bowler", key=f"setplayers_{mid}"):
        state.setdefault('batting',{})['striker'] = striker_sel
        state.setdefault('batting',{})['non_striker'] = non_sel
        state.setdefault('bowling',{})['current_bowler'] = bowler_sel
        save_match_state(mid, state)
        st.experimental_rerun()

    # End over / select new bowler control
    cur_balls = state.get('score',{}).get(bat,{}).get('balls',0)
    if cur_balls > 0 and cur_balls % 6 == 0:
        # mark flag in state (persist) so other users know over-change required
        if not state.setdefault('bowling',{}).get('over_needs_change', False):
            state.setdefault('bowling',{})['over_needs_change'] = True
            save_match_state(mid, state)
        st.info("Over completed — कृपया नया गेंदबाज़ (Next Bowler) चुनें।")
        nb_col1, nb_col2 = st.columns([2,1])
        with nb_col1:
            next_bowler = st.selectbox("Select next bowler", options=other_team_players, index=0, key=f"nextbowler_{mid}")
        with nb_col2:
            if st.button("Set Next Bowler", key=f"setnext_{mid}"):
                try:
                    if not next_bowler or str(next_bowler).strip() == "":
                        st.error("कृपया एक वैध अगले गेंदबाज़ का चयन करें।")
                    else:
                        last = state.get('bowling',{}).get('current_bowler','')
                        state.setdefault('bowling',{})['last_over_bowler'] = last
                        state.setdefault('bowling',{})['current_bowler'] = next_bowler
                        state.setdefault('bowling',{})['over_needs_change'] = False
                        save_match_state(mid, state)
                        try:
                            for k in [f"nextbowler_{mid}", f"bowler_{mid}", f"striker_{mid}", f"nonstriker_{mid}"]:
                                if k in st.session_state:
                                    del st.session_state[k]
                        except Exception:
                            pass
                        st.success(f"Next bowler set to {next_bowler}. Scoring resumed.")
                        safe_rerun()

    # ---- Quick Actions & Scoring buttons ----
    left, right = st.columns([2,1])
    with left:
        st.subheader("Quick Actions")
        runs = st.columns(6)
        labels = ["0","1","2","3","4 🎯","6 🔥"]
        values = ["0","1","2","3","4","6"]
        for i in range(6):
            with runs[i]:
                if st.button(labels[i]):
                    try:
                        entry = record_ball_full(state, mid, values[i]); save_match_state(mid, state); st.experimental_rerun()
                    except Exception as e:
                        st.error(e)

        ex1, ex2, ex3 = st.columns(3)
        with ex1:
            if st.button("Wide (WD)"):
                try:
                    entry = record_ball_full(state, mid, 'WD', extras={'runs':1}); save_match_state(mid, state); st.experimental_rerun()
                except Exception as e:
                    st.error(e)
        with ex2:
            if st.button("No Ball (NB)"):
                try:
                    entry = record_ball_full(state, mid, 'NB', extras={'runs_off_bat':0}); save_match_state(mid, state); st.experimental_rerun()
                except Exception as e:
                    st.error(e)
        with ex3:
            if st.button("Bye (BY)"):
                try:
                    entry = record_ball_full(state, mid, 'BY', extras={'runs':1}); save_match_state(mid, state); st.experimental_rerun()
                except Exception as e:
                    st.error(e)

        # Wicket expander - require new batsman from batting order (robust matching)
        with st.expander("Wicket ⚠️"):
            wtype = st.selectbox("Wicket Type", options=["Bowled","Caught","LBW","Run Out","Stumped","Hit Wicket","Other"], key=f"wtype_{mid}")

            # batting team (current)
            bat_team = state.get("bat_team", "Team A")
            bat_order = state.get('teams', {}).get(bat_team, [])[:]

            # who is dismissed (most likely striker) — normalize via same_player
            dismissed = state.get('batting',{}).get('striker','')

            # on-field (striker, non-striker)
            on_field = [
                state.get('batting',{}).get('striker',''),
                state.get('batting',{}).get('non_striker','')
            ]

            # used players heuristic (already batted)
            used_raw = [p for p,v in state.get('batsman_stats', {}).items() if (v.get('B',0)>0 or v.get('R',0)>0)]
            # build candidates excluding: on_field, used, and the dismissed player
            candidates = []
            for p in bat_order:
                # skip if p equals any on-field (including dismissed) or used
                skip = False
                for of in on_field:
                    if same_player(p, of):
                        skip = True; break
                if skip:
                    continue
                for u in used_raw:
                    if same_player(p, u):
                        skip = True; break
                if skip:
                    continue
                # extra guard: also skip if p is same as dismissed (to avoid showing the out batsman)
                if same_player(p, dismissed):
                    continue
                # else candidate
                candidates.append(p)

            # fallback: if no candidates, allow any from batting order not currently on field
            if not candidates:
                candidates = [p for p in bat_order if not any(same_player(p, of) for of in on_field)]

            # final fallback: allow free-text entry
            if candidates:
                newbat = st.selectbox("New batsman (required)", options=candidates, key=f"newbat_{mid}")
            else:
                newbat = st.text_input("New batsman (enter name)", key=f"newbatfree_{mid}")

            if st.button("Record Wicket", key=f"recw_{mid}"):
                if not newbat or str(newbat).strip()=="":
                    st.error("नया बल्लेबाज़ चुनें/डालें — wicket record करने के लिए आवश्यक।")
                else:
                    try:
                        winfo = {'type': wtype, 'new_batsman': newbat}
                        with st.spinner("Recording wicket..."):
                            entry = record_ball_full(state, mid, 'W', wicket_info=winfo)
                            save_match_state(mid, state)
                        safe_rerun()
                    except Exception as e:
                        st.error(f"Wicket record failed: {e}")

    with right:
        st.subheader("Batsmen")
        bats = state.get('batsman_stats', {})
        if not bats:
            st.info("No batsman data yet")
        else:
            rows = []
            for name, vals in bats.items():
                t = player_team(state, name)
                if t != bat:
                    continue
                R = vals.get("R",0); B = vals.get("B",0); F = vals.get("4",0); S6 = vals.get("6",0)
                SR = (R / B * 100) if B>0 else 0.0
                rows.append({"Player": name, "R": R, "B": B, "4s": F, "6s": S6, "SR": f"{SR:.1f}"})
            if rows:
                df = pd.DataFrame(rows).sort_values("R", ascending=False).reset_index(drop=True)
                st.table(df)
            else:
                st.info("No batsmen of current batting team recorded yet.")

        st.markdown("---")
        st.subheader("Bowlers")
        bowl = state.get('bowler_stats', {})
        if not bowl:
            st.info("No bowlers yet")
        else:
            rows = []
            opp_team = other
            for name, vals in bowl.items():
                t = player_team(state, name)
                if t != opp_team:
                    continue
                balls = vals.get("B",0); runs = vals.get("R",0); wkts = vals.get("W",0)
                rows.append({"Bowler": name, "Balls": format_over_ball(balls), "R": runs, "W": wkts})
            if rows:
                dfb = pd.DataFrame(rows).sort_values("W", ascending=False).reset_index(drop=True)
                st.table(dfb)
            else:
                st.info("No bowlers of opposition team recorded yet.")

        st.markdown("---")
        st.subheader("Last 12 Balls")
        last12 = state.get('balls_log', [])[-12:][::-1]
        if not last12:
            st.info("No balls recorded yet.")
        else:
            for i, b in enumerate(last12, start=1):
                st.markdown(f"{i}. {b.get('striker','-')} vs {b.get('bowler','-')} → {b.get('outcome','')} | Runs: {b.get('post_score',{}).get('runs','-')} / {b.get('post_score',{}).get('wkts','-')}")

        st.markdown("---")
        st.subheader("Commentary")
        for txt in state.get("commentary", [])[-12:][::-1]:
            st.markdown(f"- {txt}")

    st.markdown("---")
    f1, f2, f3 = st.columns(3)
    with f1:
        if st.button("Undo Last Ball"):
            ok = undo_last_ball_full(state, mid)
            if ok:
                save_match_state(mid, state); st.success("Last ball undone."); st.experimental_rerun()
            else:
                st.info("No ball to undo.")
    with f2:
        if st.button("Export JSON"):
            data = export_match_json(state)
            st.download_button("Download JSON", data=data, file_name=f"match_{mid}.json", mime="application/json")
    with f3:
        if st.button("End Match (Complete)"):
            try:
                summary = finalize_match(mid, state)
                st.success("Match marked completed.")
                st.info(summary.get("result_text","Result computed"))
                if summary.get("man_of_match_auto"):
                    st.info(f"Man of the Match (auto): {summary.get('man_of_match_auto')}")
                safe_rerun()
            except Exception as e:
                st.error(f"Failed to finalize match: {e}")

    save_match_state(mid, state)

# ---------------- Live Score (Public) ----------------
if menu == "Live Score (Public)":
    matches = load_matches_index()
    if not matches:
        st.info("No matches"); st.stop()
    mid = st.selectbox("Select Match", options=list(matches.keys()), format_func=lambda x: f"{x} — {matches[x]['title']}", key="pub_match_select")
    state = load_match_state(mid)
    if not state:
        st.error("Match state missing"); st.stop()
    if HAS_AUTORE:
        st_autorefresh(interval=5000, key=f"public_auto_{mid}")
    st.markdown(f"### {matches[mid]['title']}")

    # basic score
    bat = state.get("bat_team","Team A")
    sc = state.get("score", {}).get(bat, {"runs":0,"wkts":0,"balls":0})
    other = "Team A" if bat == "Team B" else "Team B"
    opp_sc = state.get("score", {}).get(other, {"runs":0,"wkts":0,"balls":0})

    overs_done = format_over_ball(sc.get("balls",0))
    rr = (sc.get("runs",0) / (sc.get("balls",0)/6)) if sc.get("balls",0)>0 else 0.0

    # header card
    st.markdown(f"""
    <div style='background:#0b6efd;padding:18px;border-radius:12px;text-align:center;color:white;margin-bottom:18px;'>
      <div style='font-size:28px;font-weight:900;'>{state.get('bat_team')}: {sc.get('runs',0)}/{sc.get('wkts',0)}</div>
      <div style='font-size:13px;margin-top:6px;'>Overs: {overs_done} &nbsp; • &nbsp; Run Rate: {rr:.2f}</div>
    </div>
    """, unsafe_allow_html=True)

    # current players area
    st.markdown("#### Current On-field")
    br = state.get("batting", {})
    bw = state.get("bowling", {})
    striker = br.get("striker", "-")
    non_striker = br.get("non_striker", "-")
    current_bowler = bw.get("current_bowler", "-")
    st.write(f"**Striker:** {striker}   •   **Non-striker:** {non_striker}   •   **Bowler:** {current_bowler}")

    # Target/Required when INNINGS2
    if state.get("status") == "INNINGS2":
        other_team = "Team A" if state.get("bat_team")=="Team B" else "Team B"
        opp_runs = state.get("score", {}).get(other_team, {}).get("runs", 0)
        target = opp_runs + 1
        runs_needed = max(0, target - sc.get("runs",0))
        balls_remaining = max(0, int(state.get("overs_limit",0))*6 - sc.get("balls",0)) if int(state.get("overs_limit",0))>0 else None
        req_rr = (runs_needed/(balls_remaining/6)) if balls_remaining and balls_remaining>0 else None
        req_text = f"{runs_needed} runs required from {balls_remaining} balls"
        if req_rr is not None:
            req_text += f" • Required RR: {req_rr:.2f}"
        st.info(req_text)

    st.markdown("### Score details")
    def pretty(s): return f"{s.get('runs',0)}/{s.get('wkts',0)} ({format_over_ball(s.get('balls',0))})"
    st.write(f"Team A: {pretty(state['score'].get('Team A',{}))}")
    st.write(f"Team B: {pretty(state['score'].get('Team B',{}))}")

    # Completed summary & downloads (public)
    if state.get("status") == "COMPLETED":
        fs = state.get("final_summary", {})
        st.success("Match completed — final scorecard")
        if fs:
            st.markdown(f"**Result:** {fs.get('result_text','')}")
            motm = fs.get("man_of_the_match") or fs.get("man_of_match_auto") or state.get("man_of_match_override","")
            if motm:
                st.markdown(f"**Man of the Match:** {motm}")
        st.download_button("Download final (JSON)", data=export_match_json(state), file_name=f"match_{mid}_final.json", mime="application/json")
        st.download_button("Download final (CSV)", data=export_match_csv(state), file_name=f"match_{mid}_final.csv", mime="text/csv")

    # Batsmen table (public) - show batting team's batsmen
    st.markdown("### Batsmen")
    bats = state.get("batsman_stats", {})
    rows = []
    for name, vals in bats.items():
        if player_team(state, name) != bat:
            continue
        R = vals.get("R",0); B = vals.get("B",0); F = vals.get("4",0); S6 = vals.get("6",0)
        SR = (R / B * 100) if B>0 else 0.0
        rows.append({"Player": name, "R": R, "B": B, "4s": F, "6s": S6, "SR": f"{SR:.1f}"})
    if rows:
        st.table(pd.DataFrame(rows).sort_values("R", ascending=False).reset_index(drop=True))
    else:
        st.info("No batsman stats available yet for current batting team.")

    # Bowlers table (public) - show opposition team's bowlers
    st.markdown("### Bowlers")
    bowls = state.get("bowler_stats", {})
    rows = []
    for name, vals in bowls.items():
        if player_team(state, name) != other:
            continue
        balls = vals.get("B",0); runs = vals.get("R",0); wkts = vals.get("W",0)
        rows.append({"Bowler": name, "Balls": format_over_ball(balls), "R": runs, "W": wkts})
    if rows:
        st.table(pd.DataFrame(rows).sort_values("W", ascending=False).reset_index(drop=True))
    else:
        st.info("No bowler stats available yet for opposition team.")

    # Last 12 balls
    st.markdown("### Last 12 Balls")
    last12 = state.get("balls_log", [])[-12:][::-1]
    if last12:
        for b in last12:
            t = b.get("time","")
            out = b.get("outcome","")
            s = b.get("striker","-")
            bow = b.get("bowler","-")
            st.markdown(f"- {format_over_ball(int(b.get('prev_score',{}).get('balls',0)))} → {s} vs {bow} → {out}")
    else:
        st.info("No balls recorded yet.")

    # Commentary (last 20)
    st.markdown("### Commentary")
    for txt in state.get("commentary", [])[-20:][::-1]:
        st.markdown(f"<div style='background:#f8fafc;padding:8px;border-radius:8px;margin-bottom:6px;'>{txt}</div>", unsafe_allow_html=True)

    # Match finished label
    if state.get("status") == "COMPLETED":
        st.success("Match completed — scoring closed.")

# ---------------- Player Stats ----------------
if menu == "Player Stats":
    st.subheader("Player Statistics (from completed matches)")
    matches = load_matches_index()
    stats = {}
    for mid,info in matches.items():
        # only completed
        if info.get("completed_at") or info.get("final_summary_brief"):
            s = load_match_state(mid)
            if not s:
                continue
            for name, vals in s.get("batsman_stats", {}).items():
                rec = stats.setdefault(name, {"R":0,"B":0,"4":0,"6":0,"matches":0})
                rec["R"] += int(vals.get("R",0) or 0)
                rec["B"] += int(vals.get("B",0) or 0)
                rec["4"] += int(vals.get("4",0) or 0)
                rec["6"] += int(vals.get("6",0) or 0)
            for name, vals in s.get("bowler_stats", {}).items():
                rec = stats.setdefault(name, {"W":0,"balls_bowled":0})
                rec["W"] += int(vals.get("W",0) or 0)
                rec["balls_bowled"] += int(vals.get("B",0) or 0)
            for p in set(list(s.get("batsman_stats",{}).keys()) + list(s.get("bowler_stats",{}).keys())):
                stats.setdefault(p, {}).setdefault("matches",0)
                stats[p]["matches"] = stats[p].get("matches",0) + 1

    if not stats:
        st.info("No completed matches / stats yet.")
    else:
        rows = []
        for p, v in stats.items():
            rows.append({
                "Player": p,
                "Runs": v.get("R",0),
                "Balls": v.get("B",0),
                "4s": v.get("4",0),
                "6s": v.get("6",0),
                "W": v.get("W",0),
                "Matches": v.get("matches",0),
                "SR": ( (v.get("R",0) / v.get("B",1)) * 100 ) if v.get("B",0)>0 else 0.0
            })
        df = pd.DataFrame(rows).sort_values("Runs", ascending=False).reset_index(drop=True)
        st.dataframe(df)
        st.download_button("Download Player Stats (CSV)", data=df.to_csv(index=False).encode("utf-8"), file_name="player_stats.csv", mime="text/csv")

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

    st.markdown("### Final scorecards / backups")
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith(f"match_")], reverse=True)
    if files:
        sel = st.selectbox("Select snapshot", options=files)
        p = os.path.join(BACKUP_DIR, sel)
        if sel.endswith(".json"):
            if st.button("Download selected JSON"):
                with open(p, "rb") as fh:
                    st.download_button("Download", data=fh.read(), file_name=sel, mime="application/json")
        else:
            if st.button("Download selected file"):
                with open(p, "rb") as fh:
                    st.download_button("Download", data=fh.read(), file_name=sel, mime="application/octet-stream")
    else:
        st.info("No backups found yet.")

# ---------------- Footer ----------------
st.markdown("---")
st.markdown("Note: Login by mobile only. Photos stored in `data/photos/`. Admin mobile is restricted.")
