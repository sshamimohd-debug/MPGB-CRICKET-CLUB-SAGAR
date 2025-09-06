# APP_enhanced.py
# MPGB Cricket Scoring - Full Version with Registration, Paid Mgmt, Logo
# Language: Hindi comments

import streamlit as st
import pandas as pd
import json, os, uuid
from datetime import datetime, timedelta

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTORE = True
except:
    HAS_AUTORE = False

# ---------------- CONFIG ----------------
DATA_DIR = "data"
MEMBERS_CSV = os.path.join(DATA_DIR, "members.csv")     # Member registry
PAID_CSV = os.path.join(DATA_DIR, "Members_Paid.csv")  # Paid-only list
MATCH_INDEX = os.path.join(DATA_DIR, "matches_index.json")
ADMIN_PHONE = "8931883300"   # सिर्फ यही mobile admin allowed
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------- Helpers ----------------
def load_json(path, default=None):
    if default is None: default = {}
    try: return json.load(open(path,"r",encoding="utf-8"))
    except: return default

def save_json(path, obj):
    tmp = path+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(obj,f,indent=2,ensure_ascii=False)
    try: os.replace(tmp,path)
    except: os.rename(tmp,path)

def normalize_mobile(s):
    if pd.isna(s) or s is None: return ""
    s = str(s).strip()
    for ch in [" ","+","-","(",")"]: s=s.replace(ch,"")
    digits="".join([c for c in s if c.isdigit()])
    if len(digits)>10: digits=digits[-10:]
    return digits

# ------------- Members registry -------------
def ensure_members_file():
    if not os.path.exists(MEMBERS_CSV):
        pd.DataFrame(columns=["MemberID","Name","Mobile","Paid"]).to_csv(MEMBERS_CSV,index=False)

def read_members():
    ensure_members_file()
    try: df=pd.read_csv(MEMBERS_CSV,dtype=str)
    except: df=pd.DataFrame(columns=["MemberID","Name","Mobile","Paid"])
    if "Mobile" in df: df["Mobile"]=df["Mobile"].apply(normalize_mobile)
    if "Paid" not in df: df["Paid"]="N"
    return df.fillna("")

def write_members(df): df.to_csv(MEMBERS_CSV,index=False)

def next_member_id():
    df=read_members()
    if df.empty: return "M001"
    ids=df["MemberID"].dropna().tolist(); nums=[]
    for i in ids:
        try: nums.append(int(i.lstrip("M")))
        except: pass
    mx=max(nums) if nums else 0
    return f"M{(mx+1):03d}"

# ------------- Paid-members helpers -------------
def read_paid_list():
    if os.path.exists(PAID_CSV):
        try: df=pd.read_csv(PAID_CSV,dtype=str)
        except: df=pd.DataFrame(columns=["Mobile_No"])
    else: df=pd.DataFrame(columns=["Mobile_No"])
    if df.shape[0]>0:
        col=df.columns[0]; df=df.rename(columns={col:"Mobile_No"})
        df["Mobile_No"]=df["Mobile_No"].apply(normalize_mobile)
        df=df[df["Mobile_No"]!=""].drop_duplicates().reset_index(drop=True)
    return df

def write_paid_list(df):
    if "Mobile_No" not in df: df.columns=["Mobile_No"]
    df["Mobile_No"]=df["Mobile_No"].apply(normalize_mobile)
    df.to_csv(PAID_CSV,index=False)

# ------------- Roles -------------
def is_logged_in(): return bool(st.session_state.get("MemberID"))
def current_member():
    mid=st.session_state.get("MemberID",""); df=read_members()
    row=df[df["MemberID"]==mid]; return row.iloc[0].to_dict() if not row.empty else None
def is_member_paid(): mem=current_member(); return mem and mem.get("Paid")=="Y"
def is_admin(): mem=current_member(); return mem and normalize_mobile(mem.get("Mobile"))==normalize_mobile(ADMIN_PHONE)
# ---------------- Part-2: Matches, Scoring, Undo, Lock ----------------
# Note: paste this code after Part-1 content in same APP_enhanced.py

# ---------- Match index helpers ----------
def load_matches_index():
    return load_json(MATCH_INDEX, {})

def save_matches_index(idx):
    save_json(MATCH_INDEX, idx)

# ---------- Initialize new match (helper already used in Part-1) ----------
# init_match_state(mid,title,overs,teamA,teamB) defined earlier in short versions.
# We'll provide a more complete init that includes batting order names if names exist.

def init_match_state_full(mid, title, overs, teamA, teamB):
    """
    teamA/teamB: lists of player identifiers (mobile or names)
    """
    # batting order: use teamA list as provided
    state = {
        "mid": mid,
        "title": title,
        "venue": "",
        "overs_limit": int(overs),
        "status": "INNINGS1",   # or 'INNINGS2' etc
        "innings": 1,
        "bat_team": "Team A",
        "teams": {"Team A": teamA, "Team B": teamB},
        "score": {"Team A": {"runs":0,"wkts":0,"balls":0}, "Team B": {"runs":0,"wkts":0,"balls":0}},
        "batting": {
            "striker": teamA[0] if len(teamA)>0 else "",
            "non_striker": teamA[1] if len(teamA)>1 else "",
            "order": teamA[:],
            "next_index": 2
        },
        "bowling": {"current_bowler": "", "last_over_bowler": ""},
        "batsman_stats": {},   # each: {R,B,4,6,0s...}
        "bowler_stats": {},    # each: {B,R,W}
        "balls_log": [],       # list of ball objects for undo/audit
        "commentary": [],
        "overs_detail": [],    # list of over summaries
        "man_of_match_override": "",
        "scorer_lock": {}
    }
    save_match_state(mid, state)
    return state

# ---------- Ball record / apply logic (comprehensive) ----------
def record_ball_full(state, mid, outcome, extras=None, wicket_info=None):
    """
    outcome: string like '0','1','2','3','4','6','W' for wicket, 'WD' wide, 'NB' no-ball, 'BY','LB' for byes/legbyes
    extras: dict for extras details e.g. {'runs':1} or {'runs_off_bat_nb':2}
    wicket_info: dict with details if needed (type, howout, fielder, new_batsman)
    """
    if extras is None: extras = {}
    bat_team = state["bat_team"]
    sc = state["score"][bat_team]
    striker = state["batting"].get("striker","")
    non_striker = state["batting"].get("non_striker","")
    bowler = state["bowling"].get("current_bowler","") or "Unknown"

    # snapshot for undo
    entry = {
        "time": datetime.utcnow().isoformat(),
        "over_no": None,   # we can compute later
        "outcome": outcome,
        "extras": extras,
        "wicket": wicket_info,
        "striker": striker,
        "non_striker": non_striker,
        "bowler": bowler,
        "prev_score": sc.copy(),
        "prev_batsman": {striker: state["batsman_stats"].get(striker, {}).copy(),
                         non_striker: state["batsman_stats"].get(non_striker, {}).copy()},
        "prev_bowler": {bowler: state["bowler_stats"].get(bowler, {}).copy()}
    }

    # Helper to ensure batsman/bowler records exist
    state["batsman_stats"].setdefault(striker, {"R":0,"B":0,"4":0,"6":0})
    state["batsman_stats"].setdefault(non_striker, {"R":0,"B":0,"4":0,"6":0})
    state["bowler_stats"].setdefault(bowler, {"B":0,"R":0,"W":0})

    # apply different outcomes
    legal_ball = True
    if outcome in ["0","1","2","3","4","6"]:
        runs = int(outcome)
        # batsman
        state["batsman_stats"][striker]["R"] += runs
        state["batsman_stats"][striker]["B"] += 1
        if runs == 4: state["batsman_stats"][striker]["4"] += 1
        if runs == 6: state["batsman_stats"][striker]["6"] += 1
        # bowler
        state["bowler_stats"][bowler]["B"] += 1
        state["bowler_stats"][bowler]["R"] += runs
        # team score
        sc["runs"] += runs
        sc["balls"] += 1
        # strike change
        if runs % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker

    elif outcome == "W" or outcome == "Wicket":
        # wicket: legal ball
        state["batsman_stats"][striker]["B"] += 1
        state["bowler_stats"][bowler]["B"] += 1
        state["bowler_stats"][bowler]["W"] += 1
        sc["wkts"] += 1
        sc["balls"] += 1
        # new batsman if provided
        nxt = state["batting"].get("next_index", 0)
        order = state["batting"].get("order", [])
        next_player = None
        # if wicket_info gives new_batsman use that, else pick from order
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
    elif outcome == "WD" or outcome == "Wide":
        # wides: add runs (extras.get('runs') or default 1), not legal ball
        add = int(extras.get("runs",1))
        state["bowler_stats"][bowler]["R"] += add
        sc["runs"] += add
        legal_ball = False
    elif outcome == "NB" or outcome == "No-Ball":
        # no-ball: 1 extra + possible runs off bat
        offbat = int(extras.get("runs_off_bat",0))
        add = 1 + offbat
        state["bowler_stats"][bowler]["R"] += add
        sc["runs"] += add
        if offbat>0:
            state["batsman_stats"][striker]["R"] += offbat
        legal_ball = False
    elif outcome in ["BY","LB","Bye","LegBye"]:
        add = int(extras.get("runs",1))
        sc["runs"] += add
        # count as legal ball: batsman B doesn't get runs, but ball counts
        state["batsman_stats"][striker]["B"] += 1
        state["bowler_stats"][bowler]["B"] += 1
        sc["balls"] += 1
        if add % 2 == 1:
            state["batting"]["striker"], state["batting"]["non_striker"] = non_striker, striker
    else:
        # unknown: treat as 0 legal
        state["batsman_stats"][striker]["B"] += 1
        state["bowler_stats"][bowler]["B"] += 1
        sc["balls"] += 1

    # compute over/ball index if needed (optional)
    # append entry
    entry["post_score"] = sc.copy()
    state["balls_log"].append(entry)
    # append commentary
    txt = f"{datetime.now().strftime('%H:%M:%S')} — {outcome} — {striker} vs {bowler}"
    state["commentary"].append(txt)

    # Save
    save_match_state(mid, state)
    return entry

# ---------- Undo last ball (comprehensive revert) ----------
def undo_last_ball_full(state, mid):
    if not state.get("balls_log"):
        return False
    last = state["balls_log"].pop()
    # restore previous score snapshot (stored earlier)
    state["score"][state["bat_team"]] = last.get("prev_score", state["score"][state["bat_team"]])
    # restore batsman/bowler stats if prev snapshots exist
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
    # commentary revert
    if state.get("commentary"):
        state["commentary"].pop()
    save_match_state(mid, state)
    return True

# ---------- Scorer lock helpers ----------
def try_acquire_scorer_lock(state, mid, phone):
    lock = state.get("scorer_lock", {})
    now = datetime.utcnow()
    if not lock or not lock.get("locked_by"):
        state["scorer_lock"] = {"locked_by": phone, "locked_at": now.isoformat(), "expires_at": (now + timedelta(minutes=15)).isoformat()}
        save_match_state(mid, state)
        return True
    # check expiry
    try:
        exp = datetime.fromisoformat(lock.get("expires_at"))
        if exp < now:
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

# ---------- Match creation UI helper (used in Part-3) ----------
def create_match_flow_ui():
    """
    Returns: mid if created, else None
    This helper can be used in Match Setup page to render form and create match full state.
    """
    st.markdown("### Create a new match")
    matches = load_matches_index()
    paid = read_paid_list()
    member_choices = paid["Mobile_No"].tolist() if not paid.empty else []
    with st.form("create_match_form", clear_on_submit=True):
        title = st.text_input("Match title (e.g., Team A vs Team B)")
        venue = st.text_input("Venue (optional)")
        overs = st.number_input("Overs per innings", min_value=1, max_value=50, value=20)
        st.markdown("Select players for Team A (from paid-members) or add manually (one per line)")
        teamA_select = st.multiselect("Team A (select)", options=member_choices, default=[])
        teamA_manual = st.text_area("Team A manual entries")
        st.markdown("Select players for Team B (from paid-members) or add manually")
        teamB_select = st.multiselect("Team B (select)", options=member_choices, default=[])
        teamB_manual = st.text_area("Team B manual entries")
        create = st.form_submit_button("Create Match")
    if create:
        def parse_manual(txt):
            return [x.strip() for x in txt.splitlines() if x.strip()]
        tA = [normalize_mobile(x) if any(ch.isdigit() for ch in x) else x for x in list(teamA_select) + parse_manual(teamA_manual)]
        tB = [normalize_mobile(x) if any(ch.isdigit() for ch in x) else x for x in list(teamB_select) + parse_manual(teamB_manual)]
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
            st.error(f"Duplicate players in both teams: {', '.join(dups)}")
            return None
        if not title or not tA or not tB:
            st.error("Title and at least one player per team required")
            return None
        mid = datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
        matches[mid] = {"title": title, "venue": venue, "overs": int(overs), "teamA": tA, "teamB": tB, "created_at": datetime.now().isoformat()}
        save_matches_index(matches)
        # initialize full match state
        init_match_state_full(mid, title, overs, tA, tB)
        st.success(f"Match created: {title} ({mid})")
        return mid
    return None

# ---------- Utility: show match list helper ----------
def show_matches_list_ui():
    matches = load_matches_index()
    if not matches:
        st.info("No matches currently")
        return
    st.markdown("### Matches")
    for mid, info in sorted(matches.items(), key=lambda x:x[0], reverse=True):
        st.write(f"- **{info.get('title','')}**  ({mid}) — Overs: {info.get('overs')} — Created: {info.get('created_at')}")
# ---------------- Part-3: UI Pages ----------------

st.set_page_config(page_title="MPGB Scoring", layout="wide")

# --- CSS for header and ball chips ---
st.markdown("""
<style>
.header { background: linear-gradient(90deg,#0b8457,#0b572c); color:#fff; padding:12px; border-radius:8px; margin-bottom:10px; }
.ball-chip { padding:6px 10px; border-radius:999px; background:#f3f4f6; display:inline-block; margin-right:6px; }
</style>
""", unsafe_allow_html=True)

# --- Sidebar: Login/Register ---
st.sidebar.title("Member Login / Register")

# Login form
mid_in = st.sidebar.text_input("Member ID", key="login_mid")
if st.sidebar.button("Login"):
    df = read_members()
    if mid_in.strip() in df["MemberID"].tolist():
        st.session_state["MemberID"] = mid_in.strip()
        st.experimental_rerun()
    else:
        st.sidebar.error("Invalid MemberID")

# Register form
with st.sidebar.expander("Register new member"):
    name = st.text_input("Name", key="reg_name")
    mob = st.text_input("Mobile", key="reg_mob")
    if st.button("Register", key="reg_btn"):
        if not name or not mob:
            st.error("Fill both fields")
        else:
            mems = read_members()
            nm = normalize_mobile(mob)
            if nm in mems["Mobile"].tolist():
                st.info("Mobile already registered")
            else:
                nid = next_member_id()
                new = pd.DataFrame([{"MemberID": nid, "Name": name, "Mobile": nm, "Paid": "N"}])
                write_members(pd.concat([mems, new], ignore_index=True))
                st.session_state["MemberID"] = nid
                st.success(f"Registered. ID: {nid}")
                st.experimental_rerun()

# Logout
if is_logged_in() and st.sidebar.button("Logout"):
    st.session_state.pop("MemberID")
    st.experimental_rerun()

# --- Header with logo ---
col1, col2 = st.columns([4,1])
with col1:
    st.markdown('<div class="header"><h2>MPGB Cricket Club — Live Scoring</h2></div>', unsafe_allow_html=True)
with col2:
    logo = os.path.join(DATA_DIR, "logo.png")
    if os.path.exists(logo): st.image(logo, width=80)
    else: st.markdown("**MPGB**")

# --- Menu ---
page = st.sidebar.selectbox("Menu", ["Home","Match Setup","Live Scorer","Live Score (Public)","Player Stats","Admin"])

# ---------------- HOME ----------------
if page == "Home":
    st.subheader("Welcome")
    st.write("👥 Guests can view Live Score and Player Stats.\n\n"
             "💳 Paid members can create matches and score.\n\n"
             "🛠️ Admin (only mobile 8931883300) can manage paid members and matches.")

# ---------------- Match Setup ----------------
if page == "Match Setup":
    if not (is_member_paid() or is_admin()):
        st.warning("Only paid members can create matches")
        st.stop()
    mid = create_match_flow_ui()
    show_matches_list_ui()

# ---------------- Live Scorer ----------------
if page == "Live Scorer":
    if not (is_member_paid() or is_admin()):
        st.warning("Only paid members can score")
        st.stop()
    matches = load_matches_index()
    if not matches: st.info("No matches"); st.stop()
    mid = st.selectbox("Select Match", list(matches.keys()),
                       format_func=lambda x:f"{x} — {matches[x]['title']}")
    state = load_match_state(mid)

    st.markdown(f"### {matches[mid]['title']}")
    sc = state["score"]
    st.write(f"Team A: {sc['Team A']['runs']}/{sc['Team A']['wkts']}  |  Team B: {sc['Team B']['runs']}/{sc['Team B']['wkts']}")

    # Lock system
    phone = normalize_mobile(current_member().get("Mobile",""))
    lock = state.get("scorer_lock",{})
    if lock and lock.get("locked_by") and lock.get("locked_by")!=phone:
        st.warning(f"Scoring locked by {lock.get('locked_by')} until {lock.get('expires_at')}")
        st.stop()
    else:
        if not lock:
            if st.button("Acquire Lock"): 
                if try_acquire_scorer_lock(state, mid, phone): st.experimental_rerun()
        else:
            st.info(f"You hold the lock until {lock['expires_at']}")
            c1,c2 = st.columns(2)
            if c1.button("Extend Lock"):
                state["scorer_lock"]["expires_at"] = (datetime.utcnow()+timedelta(minutes=15)).isoformat()
                save_match_state(mid,state); st.experimental_rerun()
            if c2.button("Release Lock"):
                release_scorer_lock(state, mid, phone); st.experimental_rerun()

    # Player set
    bat_team = state["bat_team"]; teams = state["teams"]
    cols = st.columns(3)
    with cols[0]:
        sel_str = st.selectbox("Striker", teams.get(bat_team,[]))
    with cols[1]:
        sel_non = st.selectbox("Non-Striker", teams.get(bat_team,[]))
    with cols[2]:
        opp = "Team B" if bat_team=="Team A" else "Team A"
        sel_bowl = st.selectbox("Bowler", teams.get(opp,[]))
    if st.button("Set Players"):
        state["batting"]["striker"]=sel_str; state["batting"]["non_striker"]=sel_non
        state["bowling"]["current_bowler"]=sel_bowl
        save_match_state(mid,state); st.experimental_rerun()

    # Scoring pad
    st.markdown("### Scoring Pad")
    for row in [["0","1","2"],["3","4","6"],["W","WD","NB"],["BY","LB"]]:
        cols = st.columns(len(row))
        for i,val in enumerate(row):
            if cols[i].button(val, key=f"btn_{val}"):
                record_ball_full(state, mid, val)
                st.experimental_rerun()
    if st.button("Undo Last"):
        undo_last_ball_full(state, mid); st.experimental_rerun()

    # Commentary
    st.markdown("### Recent Commentary")
    for c in state.get("commentary",[])[-10:][::-1]:
        st.write(c)

# ---------------- Live Score (Public) ----------------
if page == "Live Score (Public)":
    matches = load_matches_index()
    if not matches: st.info("No matches"); st.stop()
    mid = st.selectbox("Match", list(matches.keys()),
                       format_func=lambda x:f"{x} — {matches[x]['title']}")
    state = load_match_state(mid)
    if HAS_AUTORE: st_autorefresh(interval=3000, key=f"ref_{mid}")
    st.markdown(f"## {matches[mid]['title']}")
    bat = state.get("bat_team","Team A")
    sc = state["score"][bat]
    st.write(f"{bat}: {sc['runs']}/{sc['wkts']} ({sc['balls']} balls)")
    chips = state.get("balls_log",[])[-12:]
    for e in reversed(chips):
        st.markdown(f"<span class='ball-chip'>{e['outcome']}</span>", unsafe_allow_html=True)

# ---------------- Player Stats ----------------
if page == "Player Stats":
    st.subheader("Player Statistics (all matches)")
    matches = load_matches_index()
    stats = {}
    for mid in matches:
        s = load_match_state(mid)
        for name, vals in s.get("batsman_stats",{}).items():
            rec = stats.setdefault(name, {"R":0,"B":0,"4":0,"6":0})
            rec["R"]+=vals.get("R",0); rec["B"]+=vals.get("B",0)
            rec["4"]+=vals.get("4",0); rec["6"]+=vals.get("6",0)
    if not stats: st.info("No stats yet")
    else:
        df = pd.DataFrame.from_dict(stats, orient="index").reset_index().rename(columns={"index":"Player"})
        df["SR"] = (df["R"]/df["B"].replace(0,1))*100
        st.dataframe(df.sort_values("R",ascending=False))

# ---------------- Admin ----------------
if page == "Admin":
    if not is_admin():
        st.warning("Admin only"); st.stop()
    st.subheader("Admin Panel")

    # Upload Paid Members
    up = st.file_uploader("Upload Paid CSV/XLSX", type=["csv","xlsx"])
    if up:
        if up.name.endswith(".csv"): df = pd.read_csv(up,dtype=str)
        else: df = pd.read_excel(up,engine="openpyxl",dtype=str)
        if "Mobile_No" not in df: df.columns=["Mobile_No"]
        df["Mobile_No"]=df["Mobile_No"].apply(normalize_mobile)
        df=df[df["Mobile_No"]!=""].drop_duplicates()
        write_paid_list(df); st.success("Paid list updated")

    # Manual Add/Delete
    st.markdown("### Manual Paid Members")
    nm = st.text_input("Add Mobile"); 
    if st.button("Add Paid"):
        if nm.strip():
            df = read_paid_list(); m=normalize_mobile(nm)
            if m not in df["Mobile_No"].tolist():
                df=pd.concat([df,pd.DataFrame({"Mobile_No":[m]})],ignore_index=True)
                write_paid_list(df); st.success("Added")
    df = read_paid_list()
    if not df.empty:
        dm = st.selectbox("Delete Mobile", df["Mobile_No"].tolist())
        if st.button("Delete Paid"): 
            df2=df[df["Mobile_No"]!=dm]; write_paid_list(df2); st.success("Deleted")
    else: st.info("No paid members")
