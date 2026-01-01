import requests
import time
from datetime import datetime
import pandas as pd
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sys
import io

# Fix voor Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ===============================================================================
# SOCCER ODDS ANALYZER - SCHEDULED VERSION MET EMAIL NOTIFICATIES
# ===============================================================================
# Draait elk half uur en stuurt email bij nieuwe value bets
# ===============================================================================

# =============================================================================
# EMAIL CONFIGURATIE
# =============================================================================
# Voor ProtonMail Bridge of andere SMTP providers

EMAIL_ENABLED = True
EMAIL_TO = "mwolters@gmail.com"

# Optie 1: Gmail (makkelijkst - maak een "App Password" aan)
# Ga naar: https://myaccount.google.com/apppasswords
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587
EMAIL_FROM = "mwolters@gmail.com"          # Je Gmail adres
EMAIL_PASSWORD = "wnorzkzqfrkgkhod"          # App password (16 chars, geen gewoon wachtwoord!)

# Optie 2: ProtonMail Bridge (als je ProtonMail Bridge hebt draaien)
# EMAIL_SMTP_SERVER = "127.0.0.1"
# EMAIL_SMTP_PORT = 1025
# EMAIL_FROM = "mwltrs@protonmail.com"
# EMAIL_PASSWORD = "bridge_password"

# =============================================================================
# API CONFIGURATIE
# =============================================================================
API_KEY = "3af72d9e31mshfbcfb0f113f0c30p160696jsn0c5339b89a79"
API_HOST = "odds-api1.p.rapidapi.com"
BASE_URL = "https://odds-api1.p.rapidapi.com"

SOCCER_CONFIG = {
    "sportId": 10,
    "markets": {
        "ftresult": {"marketId": 101, "outcomes": [101, 102, 103], "n": 3},
        "ou25": {"marketId": 1010, "outcomes": [1010, 1011], "n": 2},
        "btts": {"marketId": 104, "outcomes": [104, 105], "n": 2}
    }
}

SOCCER_LEAGUES = [
    17, 23, 8, 35, 48, 7, 679, 34480, 37, 38, 39, 40, 41, 36, 45, 52, 152, 203,
    210, 211, 215, 218, 325, 332, 335, 238, 18, 24, 25, 44, 53, 54, 155,
    27665, 27070, 27072, 27098, 27100, 278, 242, 281, 650, 651, 136, 16, 1,
    270, 140, 384, 480, 19, 21, 217, 329, 328, 330, 346, 213, 341, 339
]

BOOKMAKERS = ["betmgm"]

DEBUG_MODE = False
SLEEP_BETWEEN_CALLS = 1.5
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2

SEEN_BETS_FILE = "seen_value_bets.json"


# =============================================================================
# EMAIL FUNCTIES
# =============================================================================

def send_email(subject, body_html):
    """Stuur een email"""
    if not EMAIL_ENABLED:
        print("[EMAIL] Uitgeschakeld")
        return False

    if EMAIL_PASSWORD == "JOUW_APP_PASSWORD":
        print("[EMAIL] Niet geconfigureerd - email niet verzonden")
        print(f"[BERICHT] {subject}")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO

    # Plain text versie
    body_text = body_html.replace('<br>', '\n').replace('<b>', '').replace('</b>', '')
    body_text = body_text.replace('<h2>', '\n').replace('</h2>', '\n')

    part1 = MIMEText(body_text, 'plain')
    part2 = MIMEText(body_html, 'html')

    msg.attach(part1)
    msg.attach(part2)

    try:
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()
        print(f"[EMAIL] Verzonden naar {EMAIL_TO}")
        return True
    except Exception as e:
        print(f"[EMAIL] Fout: {e}")
        return False


def format_value_bets_email(new_bets):
    """Maak een HTML email met alle nieuwe value bets"""
    bets_html = ""
    for row in new_bets:
        bets_html += f"""
        <div style="background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #4CAF50;">
            <h3 style="margin: 0 0 10px 0; color: #333;">{row['home']} vs {row['away']}</h3>
            <p style="margin: 5px 0; color: #666;"><b>Competitie:</b> {row['tournament']}</p>
            <p style="margin: 5px 0; color: #666;"><b>Datum/tijd:</b> {row['start_time']}</p>
            <p style="margin: 5px 0;"><b>Selectie:</b> {row['market']} - {row['selection']}</p>
            <table style="margin-top: 10px;">
                <tr>
                    <td style="padding-right: 20px;"><b>BetMGM:</b> <span style="color: #2196F3; font-size: 18px;">{row['bookmaker_odds']:.2f}</span></td>
                    <td style="padding-right: 20px;"><b>Pinnacle:</b> {row['pinnacle_odds']:.2f}</td>
                    <td><b>Value:</b> <span style="color: #4CAF50; font-weight: bold;">{row['value_percentage']:.2f}%</span></td>
                </tr>
            </table>
        </div>
        """

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">
            Value Bet Alert - {len(new_bets)} nieuwe bet(s)
        </h2>
        {bets_html}
        <p style="color: #999; font-size: 12px; margin-top: 20px;">
            Gegenereerd op {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </p>
    </body>
    </html>
    """
    return html


# =============================================================================
# SEEN BETS TRACKING
# =============================================================================

def load_seen_bets():
    if os.path.exists(SEEN_BETS_FILE):
        try:
            with open(SEEN_BETS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_seen_bets(seen_bets):
    with open(SEEN_BETS_FILE, 'w') as f:
        json.dump(seen_bets, f)


def create_bet_key(row):
    return f"{row['fixture_id']}_{row['market']}_{row['selection']}"


# =============================================================================
# API FUNCTIES
# =============================================================================

def get_tournaments_batch(tournament_ids, bookmaker, retry_count=0):
    tournament_ids_str = ",".join(str(tid) for tid in tournament_ids)
    url = f"{BASE_URL}/odds-by-tournaments"

    query_params = {
        "bookmaker": bookmaker,
        "tournamentIds": tournament_ids_str,
        "verbosity": "3"
    }

    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST
    }

    try:
        response = requests.get(url, params=query_params, headers=headers, timeout=60)
    except Exception as e:
        return None

    if response.status_code == 429:
        if retry_count < MAX_RETRIES:
            retry_delay = RETRY_DELAY_BASE * (2 ** retry_count)
            time.sleep(retry_delay)
            return get_tournaments_batch(tournament_ids, bookmaker, retry_count + 1)
        return None

    if response.status_code != 200:
        return None

    try:
        fixtures = response.json()
        if isinstance(fixtures, list) and len(fixtures) > 0:
            tournaments_data = {}
            for fixture in fixtures:
                if fixture is None or fixture.get("tournamentId") is None:
                    continue
                tid = str(fixture["tournamentId"])
                if tid not in tournaments_data:
                    tournaments_data[tid] = []
                tournaments_data[tid].append(fixture)
            return tournaments_data
        return None
    except:
        return None


def extract_odds_from_markets(bookmaker_odds, bookmaker, market_type="ftresult"):
    if bookmaker_odds is None or bookmaker not in bookmaker_odds:
        return None

    markets = bookmaker_odds.get(bookmaker, {}).get("markets")
    if markets is None:
        return None

    market_config = SOCCER_CONFIG["markets"][market_type]
    market_id_str = str(market_config["marketId"])

    if market_id_str not in markets:
        return None

    market = markets[market_id_str]
    if market.get("outcomes") is None:
        return None

    outcomes = market["outcomes"]
    odds_list = {}

    for outcome_id in market_config["outcomes"]:
        outcome_id_str = str(outcome_id)
        if outcome_id_str in outcomes:
            outcome = outcomes[outcome_id_str]
            players = outcome.get("players")
            if players and "0" in players:
                player = players["0"]
                if player.get("price") is not None and player.get("active"):
                    odds_list[outcome_id_str] = player["price"]

    if len(odds_list) != len(market_config["outcomes"]):
        return None

    return odds_list


def calculate_true_odds(odds_list, n_outcomes):
    odds_values = list(odds_list.values())
    implied_probs = [1 / odd for odd in odds_values]
    overround = sum(implied_probs)
    margin = overround - 1

    true_odds = {}
    for key, odd in odds_list.items():
        true_odds[key] = (n_outcomes * odd) / (n_outcomes - margin * odd)

    return {
        "true_odds": true_odds,
        "overround": overround,
        "margin": margin
    }


def find_value_bets(pinnacle_odds, bookmaker_odds, bookmaker_name, n_outcomes,
                    min_margin=1.02, max_bookmaker_overround=1.06, max_value_percentage=15.0):
    if pinnacle_odds is None or bookmaker_odds is None:
        return {}

    bookmaker_calc = calculate_true_odds(bookmaker_odds, n_outcomes)

    if bookmaker_calc["overround"] > max_bookmaker_overround:
        return {}

    pinnacle_calc = calculate_true_odds(pinnacle_odds, n_outcomes)

    value_bets = {}

    for outcome_id in pinnacle_calc["true_odds"]:
        if outcome_id in bookmaker_odds:
            true_odd = pinnacle_calc["true_odds"][outcome_id]
            bookmaker_odd = bookmaker_odds[outcome_id]

            if bookmaker_odd > true_odd * min_margin:
                value_percentage = ((bookmaker_odd / true_odd) - 1) * 100

                if bookmaker_odd <= 5 and value_percentage < max_value_percentage:
                    win_probability = 1 / true_odd

                    value_bets[outcome_id] = {
                        "outcome_id": outcome_id,
                        "bookmaker": bookmaker_name,
                        "bookmaker_odds": bookmaker_odd,
                        "true_odds": true_odd,
                        "win_probability": win_probability,
                        "value_percentage": value_percentage,
                    }

    return value_bets


# =============================================================================
# MAIN ANALYZE FUNCTIE
# =============================================================================

def soccer_analyze_value_bets():
    current_time = datetime.now()
    BATCH_SIZE = 3
    num_batches = (len(SOCCER_LEAGUES) + BATCH_SIZE - 1) // BATCH_SIZE

    all_results = []

    print(f"[{current_time.strftime('%H:%M:%S')}] Laden Pinnacle odds...")

    pinnacle_batches = {}
    for batch_idx in range(num_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min((batch_idx + 1) * BATCH_SIZE, len(SOCCER_LEAGUES))
        batch_leagues = SOCCER_LEAGUES[start_idx:end_idx]

        batch_data = get_tournaments_batch(batch_leagues, "pinnacle")
        if batch_data:
            pinnacle_batches.update(batch_data)

        time.sleep(SLEEP_BETWEEN_CALLS)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pinnacle: {len(pinnacle_batches)} tournaments")

    for bookmaker in BOOKMAKERS:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Laden {bookmaker.upper()} odds...")

        bookmaker_batches = {}
        for batch_idx in range(num_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min((batch_idx + 1) * BATCH_SIZE, len(SOCCER_LEAGUES))
            batch_leagues = SOCCER_LEAGUES[start_idx:end_idx]

            batch_data = get_tournaments_batch(batch_leagues, bookmaker)
            if batch_data:
                bookmaker_batches.update(batch_data)

            time.sleep(SLEEP_BETWEEN_CALLS)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] {bookmaker.upper()}: {len(bookmaker_batches)} tournaments")

        for tournament_id in bookmaker_batches:
            tournament_id_str = str(tournament_id)
            bookmaker_fixtures = bookmaker_batches[tournament_id_str]

            if tournament_id_str not in pinnacle_batches:
                continue

            pinnacle_fixtures = pinnacle_batches[tournament_id_str]

            for bookmaker_fixture in bookmaker_fixtures:
                pinnacle_fixture = None
                for pf in pinnacle_fixtures:
                    if pf.get("fixtureId") == bookmaker_fixture.get("fixtureId"):
                        pinnacle_fixture = pf
                        break

                if pinnacle_fixture is None:
                    continue

                try:
                    start_time_str = bookmaker_fixture.get("startTime", "")
                    start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    time_until_start = (start_time.replace(tzinfo=None) - current_time).total_seconds() / 3600
                except:
                    continue

                if time_until_start < 3:
                    continue

                for market_type, market_config in SOCCER_CONFIG["markets"].items():
                    bm_odds = extract_odds_from_markets(
                        bookmaker_fixture.get("bookmakerOdds"), bookmaker, market_type)
                    pin_odds = extract_odds_from_markets(
                        pinnacle_fixture.get("bookmakerOdds"), "pinnacle", market_type)

                    if bm_odds is None or pin_odds is None:
                        continue

                    value_bets = find_value_bets(pin_odds, bm_odds, bookmaker, market_config["n"])

                    for outcome_id, vb in value_bets.items():
                        outcome_names = {
                            "101": "Home", "102": "Draw", "103": "Away",
                            "1010": "Over 2.5", "1011": "Under 2.5",
                            "104": "BTTS Yes", "105": "BTTS No"
                        }

                        result = {
                            "start_time": start_time.strftime("%Y-%m-%d %H:%M"),
                            "hours_until_start": round(time_until_start, 1),
                            "tournament": bookmaker_fixtures[0].get("tournamentName", "Unknown"),
                            "home": bookmaker_fixture.get("participant1Name", ""),
                            "away": bookmaker_fixture.get("participant2Name", ""),
                            "market": market_type,
                            "selection": outcome_names.get(outcome_id, outcome_id),
                            "bookmaker": bookmaker.upper(),
                            "bookmaker_odds": vb["bookmaker_odds"],
                            "pinnacle_odds": pin_odds[outcome_id],
                            "value_percentage": round(vb["value_percentage"], 2),
                            "fixture_id": bookmaker_fixture.get("fixtureId")
                        }
                        all_results.append(result)

    if all_results:
        return pd.DataFrame(all_results).sort_values("value_percentage", ascending=False)
    return pd.DataFrame()


# =============================================================================
# SCHEDULER RUN
# =============================================================================

def run_scheduled_check():
    """Een check uitvoeren en notificaties sturen voor nieuwe bets"""
    print(f"\n{'='*60}")
    print(f"VALUE BET CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    seen_bets = load_seen_bets()
    value_bets = soccer_analyze_value_bets()

    if len(value_bets) == 0:
        print("Geen value bets gevonden")
        return

    print(f"\n{len(value_bets)} value bets gevonden")

    new_bets = []
    for idx, row in value_bets.iterrows():
        bet_key = create_bet_key(row)

        if bet_key not in seen_bets:
            new_bets.append(row)
            seen_bets[bet_key] = {
                "first_seen": datetime.now().isoformat(),
                "odds": row['bookmaker_odds'],
                "value": row['value_percentage']
            }

    save_seen_bets(seen_bets)

    if new_bets:
        print(f"\n** {len(new_bets)} NIEUWE value bets! **")
        for row in new_bets:
            print(f"  - {row['home']} vs {row['away']}: {row['selection']} @ {row['bookmaker_odds']:.2f} ({row['value_percentage']:.1f}%)")

        # Stuur email
        subject = f"Value Bet Alert: {len(new_bets)} nieuwe bet(s)"
        body = format_value_bets_email(new_bets)
        send_email(subject, body)
    else:
        print("Geen nieuwe value bets sinds laatste check")



def is_quiet_hours():
    """Check of het tussen 23:00 en 07:00 is (Nederlandse tijd)"""
    utc_now = datetime.utcnow()
    nl_hour = (utc_now.hour + 1) % 24
    return nl_hour >= 23 or nl_hour < 7


def run_scheduler(interval_minutes=90):
    """Start de scheduler die elk interval_minutes minuten draait"""
    print(f"""
================================================================
   VOETBAL VALUE BET SCHEDULER GESTART
================================================================
   Interval: elke {interval_minutes} minuten
   Rusttijd: 23:00 - 07:00 (geen checks)
   Email naar: {EMAIL_TO}
   Email geconfigureerd: {'JA' if EMAIL_PASSWORD != 'JOUW_APP_PASSWORD' else 'NEE - configureer eerst!'}

   Druk Ctrl+C om te stoppen
================================================================
""")

    if EMAIL_PASSWORD != "JOUW_APP_PASSWORD":
        send_email(
            "Value Bet Scanner Gestart",
            "<h2>Value Bet Scanner is gestart!</h2><p>Je ontvangt emails wanneer er nieuwe value bets worden gevonden.</p><p>Draait elke 90 minuten, pauzeert tussen 23:00-07:00.</p>"
        )

    while True:
        try:
            if is_quiet_hours():
                utc_now = datetime.utcnow()
                nl_hour = (utc_now.hour + 1) % 24
                print(f"\n[{datetime.now().strftime('%H:%M')}] Rusttijd (23:00-07:00 NL tijd, nu {nl_hour}:00) - slaap 30 min...")
                time.sleep(30 * 60)
            else:
                run_scheduled_check()
                print(f"\nVolgende check over {interval_minutes} minuten...")
                time.sleep(interval_minutes * 60)

        except KeyboardInterrupt:
            print("\n\nScheduler gestopt door gebruiker")
            break
        except Exception as e:
            print(f"\nError: {e}")
            print("Wacht 5 minuten en probeer opnieuw...")
            time.sleep(300)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_scheduled_check()
    else:
        run_scheduler(interval_minutes=90)
