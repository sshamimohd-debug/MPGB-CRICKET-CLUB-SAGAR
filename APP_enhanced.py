# APP_enhanced.py
# MPGB Cricket Scoring - Enhanced
# Features: mobile-friendly scoring pad, members dropdown selection, instant ball add, undo, scorer lock, OTP scaffold, payment prompt.
# Replace your existing file with this.

import streamlit as st
import pandas as pd
import json, os, uuid, time, hashlib, random
from datetime import datetime, timedelta

# attempt autorefresh import (optional)
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTorefresh = True
except Exception:
    HAS_AUTorefresh = False

# ------ CONFIG ------
DATA_DIR = "data"
MATCH_INDEX = os.path.join(DATA_DIR, "matches_index.json")
PAID_XLSX = os.path.join(DATA_DIR, "Members_Paid.xlsx")
OTP_STORE = os.path.join(DATA_DIR, "otp_store.json")
PAY_REQS = os.path.join(DATA_DIR, "payment_requests.json")
ADMIN_PHONE = "8931883300"  # your admin mobile
DEFAULT_PIN = "4321"  # legacy pin for admin actions (if used)

# ensure data dir exists
os.makedirs(DATA_DIR, exist_ok=True)

# ------ HELPERS: JSON read/write -------
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

# ------ Members (paid) helpers -------
def read_paid_members():
    # returns DataFrame with column "Mobile_No" (string)
    if os.path.exists(PAID_XLSX):
        try:
            df = pd.read_excel(PAID_XLSX, engine="openpyxl")
            if "Mobile_No" not in df.columns:
                # try guess
                cols = df.columns.tolist()
                if len(cols)>0:
                    df = df.rename(columns={cols[0]:"Mobile_No"})
            df["Mobile_No"] = df["Mobile_No"].astype(str)
            return df
        except Exception:
            return pd.DataFrame(columns=["Mobile_No"])
    else:
        return pd.DataFrame(columns=["Mobile_No"])

def write_paid_members(df):
    try:
        df2 = df.copy()
        if "Mobile_No" not in df2.columns:
            df2 = pd.DataFrame({"Mobile_No": df2})
        df2.to_excel(PAID_XLSX, index=False)
    except Exception as e:
        st.error(f"Failed to write paid members: {e}")

# ------ Match index helpers -------
def match_state_path(mid):
    return os.path.join(DATA_DIR, f"match_{mid}_state.json")

def init_match_state(mid, title, overs, teamA, teamB):
    # default initial state
    state = {
        "mid": mid,
        "title": title,
        "overs_limit": int(overs),
        "status": "INNINGS1",
        "innings": 1,
        "bat_team": "Team A",
        "teams": {"Team A": teamA, "Team B": teamB},
        "score": {"Team A": {"runs":0,"wkts":0,"balls":0}, "Team B":{"runs":0,"wkts":0,"balls":0}},
        "batting": {"striker": teamA[0] if teamA else "", "non_striker": (teamA[1] if len(teamA)>1 else ""), "order": teamA[:], "next_index": 2},
        "bowling": {"current_bowler": "", "last_over_bowler": ""},
        "batsman_stats": {},
        "bowler_stats": {},
        "balls_log": [],
        "commentary": [],
        "man_of_match_override": "",
        "scorer_lock": {}
    }
    save_json(match_state_path(mid), state)
    return state

# ------ OTP helpers (simple, testing-mode shows OTP) -------
def gen_otp():
    return str(random.randint(100000, 999999))

def store_otp(phone, otp):
    d = load_json(OTP_STORE, {})
    d[phone] = {"hash": hashlib.sha256(otp.encode()).hexdigest(), "expires": time.time()+300}
    save_json(OTP_STORE, d)

def verify_otp(phone, otp):
    d = load_json(OTP_STORE, {})
    rec = d.get(phone)
    if not rec:
        return False
    if rec.get("expires",0) < time.time():
        return False
    return rec.get("hash") == hashlib.sha256(otp.encode()).hexdigest()

# ------ ball record / undo helpers (atomic updates) -------
def save_match_state(mid, state):
    save_json(match_state_path(mid), state)

def load_match_state(mid):
    return load_json(match_state_path(mid), {})

def record_ball_in_state(state, mid, outcome, **kw):
    """
    outcome: '0','1','2','3','4','6','Wicket','Wide','No-Ball','Bye','Leg Bye'
    kw may contain runs_off_bat_nb, wide_runs, wicket_info etc.
    This function appends a snapshot entry to balls_log and mutates state.
    """
    bat_team = state["bat_team"]
    sc = state["score"][bat_team]
    striker = state["batting"].get("striker","")
    non_striker = state["batting"].get("non_striker","")
    bowler = state["bowling"].get("current_bowler","") or "Unknown"
    # snapshot for undo
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
        # update batsman
        b = state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})
        b["R"] += runs; b["B"] += 1
        if runs == 4: b["4"] = b.get("4",0) + 1
        if runs == 6: b["6"] = b.get("6",0) + 1
        # bowler
        bo = state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})
        bo["B"] += 1; bo["R"] += runs
        sc["runs"] += runs; sc["balls"] += 1
        # change strike on odd runs
        if runs % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker

    elif outcome == "Wicket":
        # record wicket
        state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})
        state["batsman_stats"][striker]["B"] += 1
        bo = state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})
        bo["B"] += 1; bo["W"] += 1
        sc["wkts"] += 1; sc["balls"] += 1
        # pick next batter
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
        # wide not legal -> ball not count

    elif outcome == "No-Ball":
        runs_off = int(kw.get("runs_off_bat_nb", 0))
        add = 1 + runs_off
        state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})["R"] += add
        if runs_off>0:
            state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})["R"] += runs_off
        sc["runs"] += add
        # not legal extras

    elif outcome in ["Bye","Leg Bye"]:
        add = int(kw.get("runs", 1))
        sc["runs"] += add
        state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})["B"] += 1
        state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})["B"] += 1
        sc["balls"] += 1
        if add % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker

    else:
        # fallback treat as 0
        state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})["B"] += 1
        state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})["B"] += 1
        sc["balls"] += 1

    # append comment snippet
    entry["post_score"] = sc.copy()
    state["balls_log"].append(entry)
    # simple commentary text
    txt = f"{datetime.now().strftime('%H:%M:%S')} — {outcome} — {striker} vs {bowler}"
    state["commentary"].append(txt)
    save_match_state(mid, state)

def undo_last_ball(state, mid):
    if not state.get("balls_log"):
        return False
    last = state["balls_log"].pop()
    # restore
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
    # remove last commentary
    if state.get("commentary"):
        state["commentary"].pop()
    save_match_state(mid, state)
    return True

# ------ Scorer lock (one scorer at a time) -------
def try_acquire_lock(state, mid, phone):
    lock = state.get("scorer_lock", {})
    now = datetime.utcnow()
    if not lock or not lock.get("locked_by"):
        state["scorer_lock"] = {"locked_by": phone, "locked_at": now.isoformat(), "expires_at": (now + timedelta(minutes=15)).isoformat()}
        save_match_state(mid, state)
        return True
    # check expiry
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

# ------ UI & App Flow -------
st.set_page_config(page_title="MPGB Scoring", layout="wide")
# CSS block (mobile friendly)
st.markdown("""
<style>
:root{ --accent:#0b8457; --muted:#f3f4f6; --card:#ffffff; --danger:#e02424; }
.header-wrap { background: linear-gradient(90deg,#062c2a,#0b8457); color:#fff; padding:14px; border-radius:12px; margin-bottom:10px; }
.score-strip { background:linear-gradient(90deg,#071a1a,#063e34); color:#fff; padding:10px 12px; border-radius:10px; font-weight:700; }
.score-pad { display:grid; grid-template-columns: repeat(3,1fr); gap:10px; padding:12px; }
.score-btn { border-radius:12px; padding:16px 10px; font-weight:800; font-size:18px; border: none; box-shadow:0 6px 18px rgba(2,6,23,0.06); background:#fff; cursor:pointer; }
.score-btn.out { background:#ffefef; color:var(--danger); border:1px solid rgba(224,36,36,0.08); }
.score-actions { display:flex; gap:8px; margin-top:8px; }
.ball-feed { display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; }
.ball-chip { padding:6px 10px; border-radius:999px; background:#f3f4f6; font-weight:700; }
.ball-chip.six { background:#ffe9e9; color:#d32f2f; }
.ball-chip.four { background:#e5f7ee; color:#0b7a44; }
.ball-chip.w { background:#111827; color:#fff; }
.admin-note { font-size:13px; color:#fff; background:#0b8457; padding:6px; border-radius:6px; }
@media (max-width:720px) {
  .score-pad { grid-template-columns: repeat(3,1fr); gap:8px; }
  .score-btn { padding:14px; font-size:16px; }
}
</style>
""", unsafe_allow_html=True)

# Session init
if "phone" not in st.session_state:
    st.session_state["phone"] = ""
if "verified_mobile" not in st.session_state:
    st.session_state["verified_mobile"] = ""
if "auth_ok" not in st.session_state:
    st.session_state["auth_ok"] = False

# Top bar
col1, col2 = st.columns([3,1])
with col1:
    st.markdown('<div class="header-wrap"><h3 style="margin:0">MPGB Cricket Club — Live Scoring</h3></div>', unsafe_allow_html=True)
with col2:
    if st.session_state.get("verified_mobile"):
        st.markdown(f'<div class="admin-note">Logged as: {st.session_state["verified_mobile"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align:right; font-size:12px">Not logged</div>', unsafe_allow_html=True)

# Sidebar navigation
st.sidebar.title("Menu")
page = st.sidebar.selectbox("Go to", ["Home", "Match Setup", "Live Scorer", "Live Score (Public)", "Player Stats", "Admin"])

# ---------- Home ----------
if page == "Home":
    st.subheader("Welcome")
    st.write("Use the sidebar to setup matches, score live, view stats, or admin tasks.")
    st.info("OTP login required for scoring. For testing OTP will be displayed on screen. Later you can enable Twilio to send SMS.")

# ---------- Member login / verify / payment ----------
def show_membership_login():
    st.markdown("### Membership / Login")
    paid_df = read_paid_members()
    mobile_input = st.text_input("Enter your mobile number (with country code if needed)", value=st.session_state.get("login_mobile",""))
    if st.button("Request OTP"):
        if not mobile_input.strip():
            st.error("Enter a mobile number.")
        else:
            st.session_state["login_mobile"] = mobile_input.strip()
            # check paid list
            is_paid = (paid_df["Mobile_No"].astype(str) == mobile_input.strip()).any()
            if not is_paid:
                st.warning("⚠️ You have not paid membership. Please contribute Rs 500.")
                st.markdown("""
                **How to pay (example):**
                - UPI ID: `yourupi@bank`
                - PhonePe / GPay: +91-XXXXXXXXXX
                - After payment click Confirm (or request admin verification)
                """)
                if st.button("I have paid Rs 500 (Confirm)"):
                    # Add mobile to paid members (self-approval - small club)
                    newdf = paid_df.copy()
                    newdf = pd.concat([newdf, pd.DataFrame({"Mobile_No":[mobile_input.strip()]})], ignore_index=True)
                    newdf.drop_duplicates(subset=["Mobile_No"], keep="last", inplace=True)
                    write_paid_members(newdf)
                    st.success("Payment recorded. You are now a paid member.")
                    st.session_state["verified_mobile"] = mobile_input.strip()
                    st.session_state["auth_ok"] = True
                    return
                if st.button("Request Admin Verification"):
                    reqs = load_json(PAY_REQS, {})
                    reqs[mobile_input.strip()] = {"requested_at": datetime.now().isoformat(), "status":"pending"}
                    save_json(PAY_REQS, reqs)
                    st.info("Request sent to admin for verification.")
                    return
            # Paid or just confirmed - generate OTP (testing: show OTP)
            otp = gen_otp()
            store_otp(mobile_input.strip(), otp)
            # If Twilio configured (st.secrets), send SMS (optional)
            if st.secrets.get("TWILIO_SID", None):
                try:
                    from twilio.rest import Client
                    client = Client(st.secrets["TWILIO_SID"], st.secrets["TWILIO_AUTH"])
                    client.messages.create(body=f"Your MPGB OTP: {otp}", from_=st.secrets["TWILIO_FROM"], to=mobile_input.strip())
                    st.success("OTP sent via SMS.")
                except Exception as e:
                    st.warning(f"Couldn't send SMS: {e}. OTP shown below for testing.")
                    st.info(f"OTP (test): {otp}")
            else:
                st.info(f"OTP (test): {otp}")

    otp_input = st.text_input("Enter OTP (6 digits)")
    if st.button("Verify OTP"):
        if verify_otp(st.session_state.get("login_mobile",""), otp_input.strip()):
            st.success("OTP verified.")
            st.session_state["verified_mobile"] = st.session_state.get("login_mobile","")
            st.session_state["auth_ok"] = True
        else:
            st.error("Invalid or expired OTP.")

# ---------- Match Setup ----------
if page == "Match Setup":
    # require login for creating match
    show_membership_login()
    if not st.session_state.get("auth_ok", False):
        st.info("Please verify mobile to create/manage matches.")
        st.stop()

    st.subheader("Create a New Match")
    matches = load_json(MATCH_INDEX, {})
    paid_df = read_paid_members()
    # prepare readable members choices (if have name - attempt)
    member_choices = []
    if not paid_df.empty:
        if "Name" in paid_df.columns:
            for _, r in paid_df.iterrows():
                member_choices.append(f"{r.get('Name','') or ''} — {r['Mobile_No']}")
        else:
            member_choices = paid_df["Mobile_No"].astype(str).tolist()

    with st.form("create_match_form", clear_on_submit=True):
        title = st.text_input("Match Title (Team A vs Team B)")
        venue = st.text_input("Venue (optional)")
        overs = st.number_input("Overs per innings", min_value=1, max_value=50, value=20)
        st.markdown("**Select Team A players (use dropdown or add manually)**")
        teamA_selected = st.multiselect("Team A (select)", options=member_choices, default=[])
        teamA_manual = st.text_area("Or enter Team A players manually (one per line)", "")
        st.markdown("**Select Team B players (use dropdown or add manually)**")
        teamB_selected = st.multiselect("Team B (select)", options=member_choices, default=[])
        teamB_manual = st.text_area("Or enter Team B players manually (one per line)", "")
        create = st.form_submit_button("Create Match")

    if create:
        # normalize players (if member_choices contain "Name — mobile", keep as typed)
        def parse_manual(txt):
            return [x.strip() for x in txt.splitlines() if x.strip()]
        tA = [x.split(" — ")[-1] if " — " in x else x for x in teamA_selected] + parse_manual(teamA_manual)
        tB = [x.split(" — ")[-1] if " — " in x else x for x in teamB_selected] + parse_manual(teamB_manual)
        # dedupe preserving order
        def dedup(seq):
            out=[]; seen=set()
            for s in seq:
                if s and s not in seen:
                    out.append(s); seen.add(s)
            return out
        tA = dedup(tA); tB = dedup(tB)
        dups = set(tA).intersection(set(tB))
        if dups:
            st.error(f"Duplicate players in both teams: {', '.join(dups)}. Remove duplicates.")
        elif not title or not tA or not tB:
            st.error("Provide title and at least one player for each team.")
        else:
            mid = datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
            matches[mid] = {"title": title, "venue": venue, "overs": int(overs), "teamA": tA, "teamB": tB, "created_at": datetime.now().isoformat()}
            save_json(MATCH_INDEX, matches)
            init_match_state(mid, title, overs, tA, tB)
            st.success(f"Match created: {title} (id: {mid})")

    st.markdown("### Existing Matches")
    for mid, info in sorted(matches.items(), key=lambda x:x[0], reverse=True):
        st.write(f"- **{info.get('title')}**  ({mid}) — Overs: {info.get('overs')}. Created: {info.get('created_at')}")

# ---------- Live Scorer ----------
if page == "Live Scorer":
    # require login and paid
    show_membership_login()
    if not st.session_state.get("auth_ok", False):
        st.info("Please verify mobile to access scorer.")
        st.stop()

    st.subheader("Scorer Interface")
    matches = load_json(MATCH_INDEX, {})
    if not matches:
        st.info("No matches. Create one under Match Setup.")
        st.stop()
    mid = st.selectbox("Select Match", options=list(matches.keys()), format_func=lambda x: f"{x} — {matches[x]['title']}")
    # load match state
    state = load_match_state(mid)
    if not state:
        st.error("Match state missing. Please recreate or init.")
        st.stop()

    # show basic info
    info = matches[mid]
    st.markdown(f"**{info['title']}** — {info.get('venue','')}")
    # scorer lock handling
    user_phone = st.session_state.get("verified_mobile", "")
    lock = state.get("scorer_lock", {})
    if lock and lock.get("locked_by") and lock.get("locked_by") != user_phone:
        # locked by someone else
        st.warning(f"Scoring currently locked by {lock.get('locked_by')}. Expires at {lock.get('expires_at')}")
        if st.button("Request lock (notify)"):
            st.info("Notification placeholder — contact current scorer to release lock.")
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
            st.info(f"You hold lock until {lock.get('expires_at')} (phone: {lock.get('locked_by')})")
            c1, c2 = st.columns(2)
            if c1.button("Extend lock"):
                # extend by resetting expires
                state["scorer_lock"]["expires_at"] = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
                save_match_state(mid, state)
                st.success("Lock extended by 15 minutes.")
            if c2.button("Release lock"):
                if release_lock(state, mid, user_phone):
                    st.success("Lock released.")
                    state = load_match_state(mid)
                    st.experimental_rerun()

    # batting/bowling assign (simple selectors)
    teams = state.get("teams", {})
    st.markdown("**Innings**: " + state.get("status",""))
    st.write(f"Score — Team A: {state['score']['Team A']['runs']}/{state['score']['Team A']['wkts']} ({state['score']['Team A']['balls']} balls)   |   Team B: {state['score']['Team B']['runs']}/{state['score']['Team B']['wkts']} ({state['score']['Team B']['balls']} balls)")
    # choose striker/non-striker/bowler if empty
    col_s = st.columns(3)
    with col_s[0]:
        striker = st.selectbox("Striker", options=state['teams'][state['bat_team']], index=0 if state['batting'].get('striker')=="" else state['teams'][state['bat_team']].index(state['batting']['striker']) if state['batting']['striker'] in state['teams'][state['bat_team']] else 0)
    with col_s[1]:
        non_striker = st.selectbox("Non-Striker", options=state['teams'][state['bat_team']], index=1 if state['batting'].get('non_striker')=="" else state['teams'][state['bat_team']].index(state['batting']['non_striker']) if state['batting']['non_striker'] in state['teams'][state['bat_team']] else 1)
    with col_s[2]:
        bowler = st.selectbox("Bowler", options=state['teams']["Team B"] if state['bat_team']=="Team A" else state['teams']["Team A"], index=0 if state['bowling'].get('current_bowler','')=="" else 0)

    # save chosen roles
    if st.button("Set Players for Over"):
        state['batting']['striker'] = striker
        state['batting']['non_striker'] = non_striker
        state['bowling']['current_bowler'] = bowler
        save_match_state(mid, state)
        st.success("Players set for this over.")

    # scoring pad (instant)
    st.markdown("### Scoring Pad (tap to record ball)")
    pad_cols = st.columns([1,1,1])
    if pad_cols[0].button("0"):
        record_ball_in_state(state, mid, "0"); st.experimental_rerun()
    if pad_cols[1].button("1"):
        record_ball_in_state(state, mid, "1"); st.experimental_rerun()
    if pad_cols[2].button("2"):
        record_ball_in_state(state, mid, "2"); st.experimental_rerun()

    pad_cols = st.columns([1,1,1])
    if pad_cols[0].button("3"):
        record_ball_in_state(state, mid, "3"); st.experimental_rerun()
    if pad_cols[1].button("4"):
        record_ball_in_state(state, mid, "4"); st.experimental_rerun()
    if pad_cols[2].button("6"):
        record_ball_in_state(state, mid, "6"); st.experimental_rerun()

    pad_cols = st.columns([1,1,1])
    if pad_cols[0].button("Wicket"):
        record_ball_in_state(state, mid, "Wicket"); st.experimental_rerun()
    if pad_cols[1].button("Wide"):
        record_ball_in_state(state, mid, "Wide", wide_runs=1); st.experimental_rerun()
    if pad_cols[2].button("No-Ball"):
        record_ball_in_state(state, mid, "No-Ball", runs_off_bat_nb=0); st.experimental_rerun()

    if st.button("Undo last ball"):
        ok = undo_last_ball(state, mid)
        if ok:
            st.success("Last ball undone.")
            st.experimental_rerun()
        else:
            st.warning("No ball to undo.")

    # show last 6 balls
    logs = state.get("balls_log", [])[-12:]
    if logs:
        st.markdown("Recent balls:")
        for lb in reversed(logs):
            out = lb.get("outcome")
            txt = f"{lb.get('time')} — {out} — {lb.get('striker')} vs {lb.get('bowler')}"
            st.markdown(f"- {txt}")

# ---------- Live Score (Public) ----------
if page == "Live Score (Public)":
    st.subheader("Live Scoreboard (public view)")
    matches = load_json(MATCH_INDEX, {})
    if not matches:
        st.info("No active matches.")
        st.stop()
    mid = st.selectbox("Match", options=list(matches.keys()), format_func=lambda x: f"{x} — {matches[x]['title']}")
    state = load_match_state(mid)
    if not state:
        st.error("Match not initialized.")
        st.stop()

    # auto refresh
    if HAS_AUTorefresh:
        st_autorefresh(interval=2000, key=f"autoref_{mid}")
    else:
        # simple refresh button
        if st.button("Refresh"):
            st.experimental_rerun()

    st.markdown(f"## {matches[mid]['title']}")
    st.markdown(f"**{state['bat_team']}**: {state['score'][state['bat_team']]['runs']}/{state['score'][state['bat_team']]['wkts']} ({state['score'][state['bat_team']]['balls']} balls)")
    # show ball chips
    sp = state.get("balls_log", [])[-12:]
    chips = []
    for e in reversed(sp):
        o = e.get("outcome")
        cls = ""
        if o == "6": cls = "six"
        elif o == "4": cls = "four"
        elif o == "Wicket": cls = "w"
        chips.append((o, cls))
    cols = st.columns(len(chips) if chips else 1)
    for i, (label, cls) in enumerate(chips):
        c = cols[i] if chips else cols[0]
        c.markdown(f'<div class="ball-chip {cls}">{label}</div>', unsafe_allow_html=True)

    st.markdown("### Commentary")
    for c in state.get("commentary", [])[-20:]:
        st.write(c)

# ---------- Player Stats (simple) ----------
if page == "Player Stats":
    st.subheader("Player Stats (Aggregate)")
    # aggregate over matches in data dir
    matches = load_json(MATCH_INDEX, {})
    if not matches:
        st.info("No matches.")
        st.stop()
    # build simple stats from all match state files
    pstats = {}
    for mid in matches.keys():
        s = load_match_state(mid)
        for name, vals in s.get("batsman_stats", {}).items():
            rec = pstats.setdefault(name, {"R":0,"B":0,"4":0,"6":0,"M":0})
            rec["R"] += vals.get("R",0); rec["B"] += vals.get("B",0); rec["4"] += vals.get("4",0); rec["6"] += vals.get("6",0)
            rec["M"] += 1
    if not pstats:
        st.info("No player data yet.")
    else:
        df = pd.DataFrame.from_dict(pstats, orient="index")
        df["SR"] = (df["R"] / df["B"].replace(0,1)) * 100
        st.dataframe(df.sort_values("R", ascending=False).reset_index().rename(columns={"index":"Player"}))

# ---------- Admin ----------
if page == "Admin":
    st.subheader("Admin Panel")
    # require admin auth (mobile & OTP)
    show_membership_login()
    if not st.session_state.get("auth_ok", False) or st.session_state.get("verified_mobile","") != ADMIN_PHONE:
        st.warning("Admin functions available only to admin mobile.")
        st.stop()

    st.markdown("### Payment Requests")
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

    st.markdown("### Matches management")
    matches = load_json(MATCH_INDEX, {})
    if matches:
        for mid, info in list(matches.items()):
            st.write(f"- {mid} — {info.get('title')}")
            if st.button(f"Delete match {mid}", key=f"del_{mid}"):
                # remove files
                matches.pop(mid, None); save_json(MATCH_INDEX, matches)
                try:
                    os.remove(match_state_path(mid))
                except Exception:
                    pass
                st.success(f"Deleted match {mid}")
    else:
        st.info("No matches.")

# End of file
