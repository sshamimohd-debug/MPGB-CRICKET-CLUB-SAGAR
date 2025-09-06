# APP_enhanced.py
# MPGB Cricket Scoring - Enhanced (Updated)
# Features: sidebar OTP login, paid members check, admin-only paid-list update, match setup by members, scoring pad, undo, scorer lock.

import streamlit as st
import pandas as pd
import json, os, uuid, time, hashlib, random
from datetime import datetime, timedelta

# optional autorefresh lib
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTORE = True
except Exception:
    HAS_AUTORE = False

# ----------------- CONFIG -----------------
DATA_DIR = "data"
MATCH_INDEX = os.path.join(DATA_DIR, "matches_index.json")
PAID_XLSX = os.path.join(DATA_DIR, "Members_Paid.xlsx")  # optional
PAID_CSV = os.path.join(DATA_DIR, "Members_Paid.csv")    # preferred for cloud
OTP_STORE = os.path.join(DATA_DIR, "otp_store.json")
PAY_REQS = os.path.join(DATA_DIR, "payment_requests.json")
ADMIN_PHONE = "8931883300"   # admin mobile (last 10 digits)
# ensure data dir
os.makedirs(DATA_DIR, exist_ok=True)

# ----------------- UTIL: JSON read/write -----------------
def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    try:
        os.replace(tmp, path)
    except Exception:
        os.rename(tmp, path)

# ----------------- Mobile normalization & paid-members helpers -----------------
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

def read_paid_members():
    """
    Returns DataFrame with column Mobile_No (normalized last 10 digits).
    Looks for CSV first (preferred), else XLSX.
    """
    if os.path.exists(PAID_CSV):
        try:
            df = pd.read_csv(PAID_CSV, dtype=str)
        except Exception:
            df = pd.DataFrame(columns=["Mobile_No"])
    elif os.path.exists(PAID_XLSX):
        try:
            df = pd.read_excel(PAID_XLSX, engine="openpyxl", dtype=str)
        except Exception:
            df = pd.DataFrame(columns=["Mobile_No"])
    else:
        return pd.DataFrame(columns=["Mobile_No"])

    # detect column for mobile
    col = None
    for c in df.columns:
        if "mob" in c.lower() or "phone" in c.lower() or "contact" in c.lower():
            col = c; break
    if col is None and len(df.columns) > 0:
        col = df.columns[0]
    df = df.rename(columns={col: "Mobile_No"})
    df["Mobile_No"] = df["Mobile_No"].apply(normalize_mobile)
    df = df[df["Mobile_No"] != ""].drop_duplicates(subset=["Mobile_No"]).reset_index(drop=True)
    return df

def write_paid_members(df):
    """
    Save paid list as CSV (more reliable on cloud).
    df must have Mobile_No column.
    """
    try:
        df2 = df.copy()
        if "Mobile_No" not in df2.columns:
            df2.columns = ["Mobile_No"]
        df2["Mobile_No"] = df2["Mobile_No"].apply(normalize_mobile)
        df2 = df2[df2["Mobile_No"]!=""].drop_duplicates(subset=["Mobile_No"])
        df2.to_csv(PAID_CSV, index=False)
    except Exception as e:
        st.error(f"Failed to write paid-members file: {e}")

# ----------------- Match state helpers -----------------
def match_state_path(mid):
    return os.path.join(DATA_DIR, f"match_{mid}_state.json")

def save_match_state(mid, state):
    save_json(match_state_path(mid), state)

def load_match_state(mid):
    return load_json(match_state_path(mid), {})

def init_match_state(mid, title, overs, teamA, teamB):
    state = {
        "mid": mid,
        "title": title,
        "overs_limit": int(overs),
        "status": "INNINGS1",
        "innings": 1,
        "bat_team": "Team A",
        "teams": {"Team A": teamA, "Team B": teamB},
        "score": {"Team A": {"runs":0,"wkts":0,"balls":0}, "Team B":{"runs":0,"wkts":0,"balls":0}},
        "batting": {"striker": teamA[0] if len(teamA)>0 else "", "non_striker": teamA[1] if len(teamA)>1 else "", "order": teamA[:], "next_index": 2},
        "bowling": {"current_bowler": "", "last_over_bowler": ""},
        "batsman_stats": {},
        "bowler_stats": {},
        "balls_log": [],
        "commentary": [],
        "man_of_match_override": "",
        "scorer_lock": {}
    }
    save_match_state(mid, state)
    return state

# ----------------- OTP helpers -----------------
def gen_otp():
    return str(random.randint(100000, 999999))

def store_otp(phone, otp):
    d = load_json(OTP_STORE, {})
    phn = normalize_mobile(phone)
    d[phn] = {"hash": hashlib.sha256(otp.encode()).hexdigest(), "expires": time.time()+300}
    save_json(OTP_STORE, d)

def verify_otp(phone, otp):
    d = load_json(OTP_STORE, {})
    phn = normalize_mobile(phone)
    rec = d.get(phn)
    if not rec:
        return False
    if rec.get("expires",0) < time.time():
        return False
    return rec.get("hash") == hashlib.sha256(otp.encode()).hexdigest()

# ----------------- Ball record + undo -----------------
def record_ball_in_state(state, mid, outcome, **kw):
    """
    outcome: '0','1','2','3','4','6','Wicket','Wide','No-Ball','Bye','Leg Bye'
    Stores snapshot for undo and updates state.
    """
    bat_team = state["bat_team"]
    sc = state["score"][bat_team]
    striker = state["batting"].get("striker","")
    non_striker = state["batting"].get("non_striker","")
    bowler = state["bowling"].get("current_bowler","") or "Unknown"

    entry = {
        "time": datetime.utcnow().isoformat(),
        "outcome": outcome,
        "striker": striker,
        "non_striker": non_striker,
        "bowler": bowler,
        "prev_score": sc.copy(),
        "prev_batsman": {striker: state["batsman_stats"].get(striker, {}).copy(),
                         non_striker: state["batsman_stats"].get(non_striker, {}).copy()},
        "prev_bowler": {bowler: state["bowler_stats"].get(bowler, {}).copy()},
        "meta": kw
    }

    # handle outcomes
    if outcome in ["0","1","2","3","4","6"]:
        runs = int(outcome)
        b = state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})
        b["R"] += runs; b["B"] += 1
        if runs == 4: b["4"] = b.get("4",0) + 1
        if runs == 6: b["6"] = b.get("6",0) + 1
        bo = state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})
        bo["B"] += 1; bo["R"] += runs
        sc["runs"] += runs; sc["balls"] += 1
        if runs % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker

    elif outcome == "Wicket":
        state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})
        state["batsman_stats"][striker]["B"] += 1
        bo = state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})
        bo["B"] += 1; bo["W"] += 1
        sc["wkts"] += 1; sc["balls"] += 1
        order = state["batting"].get("order", [])
        nxt = state["batting"].get("next_index", 0)
        next_player = ""
        while nxt < len(order):
            candidate = order[nxt]; nxt += 1
            if candidate not in [striker, non_striker]:
                next_player = candidate
                break
        state["batting"]["next_index"] = nxt
        if next_player:
            state["batting"]["striker"] = next_player
            state["batsman_stats"].setdefault(next_player, {"R":0,"B":0,"4":0,"6":0})

    elif outcome == "Wide":
        add = int(kw.get("wide_runs", 1))
        state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})["R"] += add
        sc["runs"] += add

    elif outcome == "No-Ball":
        runs_off = int(kw.get("runs_off_bat_nb", 0))
        add = 1 + runs_off
        state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})["R"] += add
        if runs_off>0:
            state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})["R"] += runs_off
        sc["runs"] += add

    elif outcome in ["Bye","Leg Bye"]:
        add = int(kw.get("runs", 1))
        sc["runs"] += add
        state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})["B"] += 1
        state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})["B"] += 1
        sc["balls"] += 1
        if add % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker
    else:
        state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})["B"] += 1
        state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})["B"] += 1
        sc["balls"] += 1

    entry["post_score"] = sc.copy()
    state["balls_log"].append(entry)
    txt = f"{datetime.now().strftime('%H:%M:%S')} — {outcome} — {striker} vs {bowler}"
    state["commentary"].append(txt)
    save_match_state(mid, state)

def undo_last_ball(state, mid):
    if not state.get("balls_log"):
        return False
    last = state["balls_log"].pop()
    state["score"][state["bat_team"]] = last["prev_score"]
    for p, vals in last["prev_batsman"].items():
        if vals == {}:
            state["batsman_stats"].pop(p, None)
        else:
            state["batsman_stats"][p] = vals
    for p, vals in last["prev_bowler"].items():
        if vals == {}:
            state["bowler_stats"].pop(p, None)
        else:
            state["bowler_stats"][p] = vals
    if state.get("commentary"):
        state["commentary"].pop()
    save_match_state(mid, state)
    return True

# ----------------- Scorer lock -----------------
def try_acquire_lock(state, mid, phone):
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
    except Exception:
        pass
    return False

def release_lock(state, mid, phone):
    lock = state.get("scorer_lock", {})
    if lock.get("locked_by") == phone:
        state["scorer_lock"] = {}
        save_match_state(mid, state)
        return True
    return False

# ----------------- Roles helpers -----------------
def is_member():
    paid = read_paid_members()
    phone = st.session_state.get("verified_mobile","")
    if not phone:
        return False
    ph = normalize_mobile(phone)
    if ph == "": return False
    return (paid["Mobile_No"] == ph).any()

def is_admin():
    phone = st.session_state.get("verified_mobile","")
    ph = normalize_mobile(phone)
    return ph == normalize_mobile(ADMIN_PHONE)

# ----------------- UI Start -----------------
st.set_page_config(page_title="MPGB Scoring", layout="wide")
# CSS (simple mobile friendly)
st.markdown("""
<style>
:root{ --accent:#0b8457; --muted:#f3f4f6; --card:#ffffff; --danger:#e02424; }
.header { background: linear-gradient(90deg,#062c2a,#0b8457); color:#fff; padding:12px; border-radius:10px; margin-bottom:10px; }
.score-pad { display:grid; grid-template-columns: repeat(3,1fr); gap:10px; }
.score-btn { border-radius:10px; padding:14px; font-weight:700; font-size:18px; background:#fff; border: none; box-shadow:0 6px 12px rgba(0,0,0,0.06); cursor:pointer; }
.ball-chip { padding:6px 10px; border-radius:999px; background:#f3f4f6; font-weight:700; margin-right:6px; display:inline-block; }
.small { font-size:13px; color:#666; }
</style>
""", unsafe_allow_html=True)

# Session init
if "login_mobile" not in st.session_state:
    st.session_state["login_mobile"] = ""
if "verified_mobile" not in st.session_state:
    st.session_state["verified_mobile"] = ""
if "auth_ok" not in st.session_state:
    st.session_state["auth_ok"] = False

# Sidebar: persistent login form
st.sidebar.title("Member Login")
if not st.session_state.get("auth_ok", False):
    mb = st.sidebar.text_input("Mobile number", value=st.session_state.get("login_mobile",""), key="sb_mob")
    if st.sidebar.button("Request OTP", key="sb_req"):
        if not mb.strip():
            st.sidebar.error("Enter mobile first")
        else:
            st.session_state["login_mobile"] = mb.strip()
            # Check paid list first (inform)
            paid = read_paid_members()
            user_norm = normalize_mobile(mb)
            if not (paid["Mobile_No"] == user_norm).any():
                st.sidebar.warning("You are not in paid list. Please pay Rs 500 or request admin verification.")
            otp = gen_otp()
            store_otp(mb, otp)
            if st.secrets.get("TWILIO_SID", None):
                # optional: sending SMS via Twilio if configured
                try:
                    from twilio.rest import Client
                    client = Client(st.secrets["TWILIO_SID"], st.secrets["TWILIO_AUTH"])
                    client.messages.create(body=f"Your MPGB OTP: {otp}", from_=st.secrets["TWILIO_FROM"], to=mb)
                    st.sidebar.success("OTP sent via SMS (if configured).")
                except Exception as e:
                    st.sidebar.info(f"OTP (test): {otp} — SMS sending failed: {e}")
            else:
                st.sidebar.info(f"OTP (test): {otp}")
    otp_val = st.sidebar.text_input("Enter OTP", key="sb_otp")
    if st.sidebar.button("Verify OTP", key="sb_v"):
        phone_norm = normalize_mobile(st.session_state.get("login_mobile",""))
        if verify_otp(phone_norm, otp_val.strip()):
            st.session_state["verified_mobile"] = phone_norm
            st.session_state["auth_ok"] = True
            st.sidebar.success("Login successful")
        else:
            st.sidebar.error("Invalid or expired OTP")
else:
    st.sidebar.markdown(f"**Logged in:** {st.session_state.get('verified_mobile')}")
    if st.sidebar.button("Logout", key="sb_lo"):
        st.session_state["verified_mobile"] = ""
        st.session_state["auth_ok"] = False
        st.sidebar.success("Logged out")

# Top header
col1, col2 = st.columns([4,1])
with col1:
    st.markdown('<div class="header"><h2 style="margin:4px 0">MPGB Cricket Club — Live Scoring</h2></div>', unsafe_allow_html=True)
with col2:
    if st.session_state.get("verified_mobile"):
        st.markdown(f"<div class='small'>Logged: {st.session_state.get('verified_mobile')}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='small'>Not logged</div>", unsafe_allow_html=True)

# Sidebar Menu
page = st.sidebar.selectbox("Menu", ["Home", "Match Setup", "Live Scorer", "Live Score (Public)", "Player Stats", "Admin"])

# ----------------- HOME -----------------
if page == "Home":
    st.subheader("Welcome to MPGB Scoring")
    st.write("Use sidebar to login and navigate. Paid members can create matches, score, and view stats.")
    st.info("For testing OTP will show on screen. To enable real SMS, add Twilio credentials to Streamlit Secrets.")

# ----------------- MATCH SETUP (members+admin) -----------------
if page == "Match Setup":
    if not (is_member() or is_admin()):
        st.info("Match creation available to paid members. Please login and complete membership.")
        st.stop()

    st.subheader("Create / Manage Matches")
    matches = load_json(MATCH_INDEX, {})
    paid_df = read_paid_members()
    # prepare choices (show name-mobile if present)
    member_choices = []
    if not paid_df.empty:
        member_choices = paid_df["Mobile_No"].astype(str).tolist()

    with st.form("create_match", clear_on_submit=True):
        title = st.text_input("Match Title (e.g., Team A vs Team B)")
        venue = st.text_input("Venue (optional)")
        overs = st.number_input("Overs per innings", min_value=1, max_value=50, value=20)
        st.markdown("**Team A** (select from paid members or type names)")
        teamA_select = st.multiselect("Team A (select mobiles)", options=member_choices, default=[])
        teamA_manual = st.text_area("Team A manual (one per line)")
        st.markdown("**Team B**")
        teamB_select = st.multiselect("Team B (select mobiles)", options=member_choices, default=[])
        teamB_manual = st.text_area("Team B manual (one per line)")
        create = st.form_submit_button("Create Match")

    if create:
        def parse_manual(txt):
            return [x.strip() for x in txt.splitlines() if x.strip()]
        tA = list(teamA_select) + parse_manual(teamA_manual)
        tB = list(teamB_select) + parse_manual(teamB_manual)
        # dedupe & normalize mobiles if they look numeric
        def dedup(seq):
            out=[]; seen=set()
            for s in seq:
                if s is None: continue
                s2 = normalize_mobile(s) if any(ch.isdigit() for ch in s) else s.strip()
                if s2 and s2 not in seen:
                    out.append(s2); seen.add(s2)
            return out
        tA = dedup(tA); tB = dedup(tB)
        dups = set(tA).intersection(set(tB))
        if dups:
            st.error(f"Duplicate players in both teams: {', '.join(dups)}")
        elif not title or not tA or not tB:
            st.error("Provide title and players for both teams.")
        else:
            mid = datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
            matches[mid] = {"title": title, "venue": venue, "overs": int(overs), "teamA": tA, "teamB": tB, "created_at": datetime.now().isoformat()}
            save_json(MATCH_INDEX, matches)
            init_match_state(mid, title, overs, tA, tB)
            st.success(f"Match created: {title} (id: {mid})")

    st.markdown("### Existing Matches")
    if matches:
        for mid, info in sorted(matches.items(), key=lambda x:x[0], reverse=True):
            st.write(f"- **{info.get('title')}**  ({mid}) — Overs: {info.get('overs')}. Created: {info.get('created_at')}")
    else:
        st.info("No matches created yet.")

# ----------------- LIVE SCORER (members+admin) -----------------
if page == "Live Scorer":
    if not (is_member() or is_admin()):
        st.info("Live scoring available to paid members. Please login or pay membership first.")
        st.stop()

    st.subheader("Scorer")
    matches = load_json(MATCH_INDEX, {})
    if not matches:
        st.info("No matches found. Create match in Match Setup.")
        st.stop()
    mid = st.selectbox("Select Match", options=list(matches.keys()), format_func=lambda x: f"{x} — {matches[x]['title']}")
    state = load_match_state(mid)
    if not state:
        st.error("Match state missing.")
        st.stop()

    st.markdown(f"**{matches[mid]['title']}**")
    # lock logic
    user_phone = st.session_state.get("verified_mobile","")
    lock = state.get("scorer_lock", {})
    if lock and lock.get("locked_by") and lock.get("locked_by") != user_phone:
        st.warning(f"Scoring locked by {lock.get('locked_by')} until {lock.get('expires_at')}")
        if st.button("Request lock"):
            st.info("Lock request noted. Contact current scorer.")
        st.stop()
    else:
        if not lock or not lock.get("locked_by"):
            if st.button("Acquire scoring lock"):
                ok = try_acquire_lock(state, mid, user_phone)
                if ok:
                    st.success("Lock acquired for 15 minutes.")
                    state = load_match_state(mid)
                else:
                    st.error("Could not acquire lock.")
        else:
            st.info(f"You hold lock until {lock.get('expires_at')}")
            c1, c2 = st.columns(2)
            if c1.button("Extend lock"):
                state["scorer_lock"]["expires_at"] = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
                save_match_state(mid, state)
                st.success("Lock extended by 15 minutes.")
            if c2.button("Release lock"):
                if release_lock(state, mid, user_phone):
                    st.success("Lock released.")
                    state = load_match_state(mid)
                    st.experimental_rerun()

    # set striker/non-striker/bowler
    st.write("Score:", f"Team A {state['score']['Team A']['runs']}/{state['score']['Team A']['wkts']} ({state['score']['Team A']['balls']} balls)",
             "|", f"Team B {state['score']['Team B']['runs']}/{state['score']['Team B']['wkts']} ({state['score']['Team B']['balls']} balls)")
    col_s = st.columns(3)
    bat_team = state.get("bat_team","Team A")
    teams = state.get("teams", {})
    team_list = teams.get(bat_team, [])
    striker_idx = 0
    if state["batting"].get("striker") in team_list:
        striker_idx = team_list.index(state["batting"].get("striker"))
    non_idx = 1 if len(team_list) > 1 else 0
    if state["batting"].get("non_striker") in team_list:
        non_idx = team_list.index(state["batting"].get("non_striker"))
    with col_s[0]:
        sel_striker = st.selectbox("Striker", options=team_list, index=striker_idx)
    with col_s[1]:
        sel_non = st.selectbox("Non-Striker", options=team_list, index=non_idx)
    with col_s[2]:
        opp_team = "Team B" if bat_team=="Team A" else "Team A"
        sel_bowler = st.selectbox("Bowler", options=teams.get(opp_team, []), index=0 if teams.get(opp_team) else 0)

    if st.button("Set players for over"):
        state["batting"]["striker"] = sel_striker
        state["batting"]["non_striker"] = sel_non
        state["bowling"]["current_bowler"] = sel_bowler
        save_match_state(mid, state)
        st.success("Players set.")

    # scoring pad
    st.markdown("### Scoring Pad")
    r1 = st.columns(3)
    if r1[0].button("0"): record_ball_in_state(state, mid, "0"); st.experimental_rerun()
    if r1[1].button("1"): record_ball_in_state(state, mid, "1"); st.experimental_rerun()
    if r1[2].button("2"): record_ball_in_state(state, mid, "2"); st.experimental_rerun()

    r2 = st.columns(3)
    if r2[0].button("3"): record_ball_in_state(state, mid, "3"); st.experimental_rerun()
    if r2[1].button("4"): record_ball_in_state(state, mid, "4"); st.experimental_rerun()
    if r2[2].button("6"): record_ball_in_state(state, mid, "6"); st.experimental_rerun()

    r3 = st.columns(3)
    if r3[0].button("Wicket"): record_ball_in_state(state, mid, "Wicket"); st.experimental_rerun()
    if r3[1].button("Wide"): record_ball_in_state(state, mid, "Wide", wide_runs=1); st.experimental_rerun()
    if r3[2].button("No-Ball"): record_ball_in_state(state, mid, "No-Ball", runs_off_bat_nb=0); st.experimental_rerun()

    if st.button("Undo last ball"):
        ok = undo_last_ball(state, mid)
        if ok:
            st.success("Last ball undone.")
            st.experimental_rerun()
        else:
            st.warning("No ball to undo.")

    # recent balls
    logs = state.get("balls_log", [])[-12:]
    if logs:
        st.markdown("Recent balls:")
        for lb in reversed(logs):
            out = lb.get("outcome")
            st.write(f"- {lb.get('time')} — {out} — {lb.get('striker')} vs {lb.get('bowler')}")

# ----------------- LIVE SCORE (public) -----------------
if page == "Live Score (Public)":
    st.subheader("Live Score (Public)")
    matches = load_json(MATCH_INDEX, {})
    if not matches:
        st.info("No matches.")
        st.stop()
    mid = st.selectbox("Match", options=list(matches.keys()), format_func=lambda x: f"{x} — {matches[x]['title']}")
    state = load_match_state(mid)
    if not state:
        st.error("Match state missing.")
        st.stop()
    if HAS_AUTORE:
        st_autorefresh(interval=2000, key=f"autoref_{mid}")
    else:
        if st.button("Refresh"):
            st.experimental_rerun()
    st.markdown(f"## {matches[mid]['title']}")
    st.markdown(f"**{state['bat_team']}**: {state['score'][state['bat_team']]['runs']}/{state['score'][state['bat_team']]['wkts']} ({state['score'][state['bat_team']]['balls']} balls)")
    chips = state.get("balls_log", [])[-12:]
    if chips:
        for e in reversed(chips):
            st.markdown(f"<span class='ball-chip'>{e.get('outcome')}</span>", unsafe_allow_html=True)
    st.markdown("### Commentary")
    for c in state.get("commentary", [])[-30:]:
        st.write(c)

# ----------------- PLAYER STATS -----------------
if page == "Player Stats":
    st.subheader("Player Stats Aggregated")
    matches = load_json(MATCH_INDEX, {})
    if not matches:
        st.info("No matches yet.")
        st.stop()
    pstats = {}
    for mid in matches.keys():
        s = load_match_state(mid)
        for name, vals in s.get("batsman_stats", {}).items():
            rec = pstats.setdefault(name, {"R":0,"B":0,"4":0,"6":0,"M":0})
            rec["R"] += vals.get("R",0); rec["B"] += vals.get("B",0); rec["4"] += vals.get("4",0); rec["6"] += vals.get("6",0)
            rec["M"] += 1
    if not pstats:
        st.info("No player data.")
    else:
        df = pd.DataFrame.from_dict(pstats, orient="index")
        df["SR"] = (df["R"] / df["B"].replace(0,1)) * 100
        st.dataframe(df.sort_values("R", ascending=False).reset_index().rename(columns={"index":"Player"}))

# ----------------- ADMIN -----------------
if page == "Admin":
    # admin login required
    if not st.session_state.get("auth_ok", False) or not is_admin():
        st.warning("Admin features available only to admin mobile.")
        st.stop()

    st.subheader("Admin Panel")
    st.markdown("### Update Paid Members (Upload CSV/XLSX)")
    uploaded = st.file_uploader("Upload Members CSV/XLSX (one column containing mobile numbers or 'Mobile_No' header)", type=["csv","xlsx"])
    if uploaded is not None:
        try:
            if uploaded.name.endswith(".csv"):
                dfnew = pd.read_csv(uploaded, dtype=str)
            else:
                dfnew = pd.read_excel(uploaded, engine="openpyxl", dtype=str)
            if "Mobile_No" not in dfnew.columns:
                # assume first column
                col = dfnew.columns[0]
                dfnew = dfnew.rename(columns={col: "Mobile_No"})
            dfnew["Mobile_No"] = dfnew["Mobile_No"].apply(normalize_mobile)
            dfnew = dfnew[dfnew["Mobile_No"]!=""].drop_duplicates(subset=["Mobile_No"])
            write_paid_members(dfnew)
            st.success("Paid members list updated.")
        except Exception as e:
            st.error(f"Upload failed: {e}")

    st.markdown("### Pending Payment Requests")
    reqs = load_json(PAY_REQS, {})
    if reqs:
        for m, info in list(reqs.items()):
            st.write(f"- {m} requested at {info.get('requested_at')}")
            c1, c2 = st.columns(2)
            if c1.button(f"Approve {m}", key=f"ap_{m}"):
                df = read_paid_members()
                df = pd.concat([df, pd.DataFrame({"Mobile_No":[m]})], ignore_index=True)
                df.drop_duplicates(subset=["Mobile_No"], keep="last", inplace=True)
                write_paid_members(df)
                reqs.pop(m, None); save_json(PAY_REQS, reqs)
                st.success(f"{m} approved.")
            if c2.button(f"Reject {m}", key=f"rj_{m}"):
                reqs.pop(m, None); save_json(PAY_REQS, reqs)
                st.info(f"{m} rejected.")
    else:
        st.info("No payment requests.")

    st.markdown("### Manage Matches")
    matches = load_json(MATCH_INDEX, {})
    if matches:
        for mid, info in list(matches.items()):
            st.write(f"- {mid} — {info.get('title')}")
            if st.button(f"Delete match {mid}", key=f"del_{mid}"):
                matches.pop(mid, None); save_json(MATCH_INDEX, matches)
                try:
                    os.remove(match_state_path(mid))
                except Exception:
                    pass
                st.success(f"Deleted match {mid}")
    else:
        st.info("No matches.")

# ----------------- END -----------------
