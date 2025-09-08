# MPGB Cricket Club - Sagar (Streamlit Scorer)

This is a Streamlit-based cricket scorer app for **MPGB Cricket Club - Sagar**.  
It provides professional-style scoring (similar to CricHeroes/KDM scorer) with features like:

- Member login / register (by mobile no.)
- Match setup (teams, overs, venue)
- Live scoring (runs, wickets, extras, commentary, auto innings switch)
- Live public scoreboard with auto-refresh
- Player stats & highlights
- Admin panel (verify members, manage paid list, set MOTM override)
- Download ID cards for members

---

## 🚀 Run Locally

```bash
python -m venv venv
source venv/bin/activate   # (on Windows: venv\Scripts\activate)
pip install -r requirements.txt
streamlit run APP_enhanced.py
