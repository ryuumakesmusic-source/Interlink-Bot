import requests
import time
import base64
import os
import imaplib
import email
import email.utils
from datetime import datetime, timezone
import jwt
from bs4 import BeautifulSoup
import re
from termcolor import colored
import uuid
import json

# ─────────────────────────────────────────────
#  UTILS
# ─────────────────────────────────────────────

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_timestamp():
    return int(time.time() * 1000)

def format_time(seconds):
    if seconds <= 0:
        return "Now"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

def time_remaining_seconds(next_frame_ms):
    current = get_timestamp()
    diff = (next_frame_ms - current) / 1000
    return max(0, int(diff))

# ─────────────────────────────────────────────
#  BANNER
# ─────────────────────────────────────────────

def display_banner():
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║      ██████╗ ██╗   ██╗██╗   ██╗██╗   ██╗                    ║
║      ██╔══██╗╚██╗ ██╔╝██║   ██║██║   ██║                    ║
║      ██████╔╝ ╚████╔╝ ██║   ██║██║   ██║                    ║
║      ██╔══██╗  ╚██╔╝  ██║   ██║██║   ██║                    ║
║      ██║  ██║   ██║   ╚██████╔╝╚██████╔╝                    ║
║      ╚═╝  ╚═╝   ╚═╝    ╚═════╝  ╚═════╝                    ║
║                                                              ║
║          🚀  INTERLINK MINING BOT  🚀                        ║
║               ✨  Crafted by Ryuu  ✨                         ║
║                                                              ║
║      Smart Claim │ Auto Sleep │ Multi-Account                ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(colored(banner, 'cyan', attrs=['bold']))

# ─────────────────────────────────────────────
#  CREDENTIALS
# ─────────────────────────────────────────────

def read_credentials():
    accounts = []
    try:
        with open('data.txt', 'r') as file:
            for line_num, line in enumerate(file.readlines(), 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|')
                if len(parts) >= 5:
                    accounts.append({
                        "loginId":            parts[0].strip(),
                        "passcode":           parts[1].strip(),
                        "email":              parts[2].strip(),
                        "gmail_app_password": parts[3].strip(),
                        "groupId":            parts[4].strip()
                    })
                else:
                    print(colored(f"  ⚠️  Line {line_num}: bad format, skipping.", 'red'))
        return accounts
    except Exception as e:
        print(colored(f"  ❌ Cannot read data.txt: {e}", 'red'))
        return None

# ─────────────────────────────────────────────
#  SCHEDULE STORAGE
#  Save/load next claim timestamps locally
#  so we NEVER need to login just to check time
# ─────────────────────────────────────────────

def save_schedule(login_id, next_airdrop_ms, next_group_ms):
    """Save next claim timestamps to disk"""
    data = {
        "next_airdrop_ms": next_airdrop_ms,
        "next_group_ms":   next_group_ms
    }
    with open(f'schedule_{login_id}.json', 'w') as f:
        json.dump(data, f)

def load_schedule(login_id):
    """Load saved next claim timestamps from disk"""
    try:
        with open(f'schedule_{login_id}.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

# ─────────────────────────────────────────────
#  DEVICE ID
# ─────────────────────────────────────────────

def get_device_id(login_id):
    filename = f'deviceid_{login_id}.txt'
    try:
        with open(filename, 'r') as f:
            did = f.read().strip()
            if did:
                return did
    except FileNotFoundError:
        pass
    did = uuid.uuid4().hex[:16]
    with open(filename, 'w') as f:
        f.write(did)
    return did

# ─────────────────────────────────────────────
#  HEADERS
# ─────────────────────────────────────────────

def base_headers(device_id, token=None):
    h = {
        'accept':          '*/*',
        'x-date':          str(get_timestamp()),
        'x-unique-id':     device_id,
        'x-model':         'Pixel 4',
        'x-brand':         'google',
        'x-system-name':   'Android',
        'x-device-id':     'smdk6400',
        'x-bundle-id':     'org.ai.interlinklabs.interlinkId',
        'content-type':    'application/json',
        'accept-encoding': 'gzip',
        'user-agent':      'okhttp/4.12.0',
        'x-signature':     base64.b64encode(os.urandom(32)).decode()[:44],
        'x-content-hash':  base64.b64encode(os.urandom(32)).decode()[:44],
    }
    if token:
        h['authorization'] = f'Bearer {token}'
    return h

# ─────────────────────────────────────────────
#  OTP / GMAIL
# ─────────────────────────────────────────────

def fetch_otp(email_address, app_password, request_timestamp):
    try:
        imap = imaplib.IMAP4_SSL('imap.gmail.com')
        imap.login(email_address, app_password)

        valid_otp         = None
        latest_valid_time = 0

        for folder in ['INBOX', '"[Gmail]/Spam"']:
            try:
                imap.select(folder)
                _, data = imap.search(None, '(FROM "noreply@interlinklabs.org")')
                if not data[0]:
                    continue

                for eid in reversed(data[0].split()[-5:]):
                    _, msg_data = imap.fetch(eid, '(RFC822)')
                    msg = email.message_from_bytes(msg_data[0][1])

                    date_tuple = email.utils.parsedate_tz(msg['Date'])
                    if not date_tuple:
                        continue

                    email_ts = email.utils.mktime_tz(date_tuple)
                    if email_ts < (request_timestamp - 180):
                        continue

                    otp   = None
                    parts = msg.walk() if msg.is_multipart() else [msg]
                    for part in parts:
                        ct   = part.get_content_type()
                        body = part.get_payload(decode=True)
                        if not body:
                            continue
                        body = body.decode('utf-8', errors='ignore')
                        if ct == 'text/html':
                            body = BeautifulSoup(body, 'html.parser').get_text()
                        m = re.search(r'\b\d{6}\b', body)
                        if m:
                            otp = m.group(0)
                            break

                    if otp and email_ts > latest_valid_time:
                        latest_valid_time = email_ts
                        valid_otp = otp

            except Exception:
                pass

        imap.logout()
        return valid_otp
    except Exception:
        return None

# ─────────────────────────────────────────────
#  AUTH APIS
# ─────────────────────────────────────────────

def api_check_passcode(account, device_id):
    try:
        r = requests.post(
            "https://prod.interlinklabs.ai/api/v1/auth/check-passcode",
            headers=base_headers(device_id),
            json={
                "loginId":  account['loginId'],
                "passcode": account['passcode'],
                "deviceId": device_id
            }
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def api_send_otp(account, device_id):
    try:
        r = requests.post(
            "https://prod.interlinklabs.ai/api/v1/auth/send-otp-email-verify-login",
            headers=base_headers(device_id),
            json={
                "loginId":  account['loginId'],
                "passcode": account['passcode'],
                "email":    account['email'],
                "deviceId": device_id
            }
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def api_verify_otp(account, otp, device_id):
    try:
        r = requests.post(
            "https://prod.interlinklabs.ai/api/v1/auth/check-otp-email-verify-login",
            headers=base_headers(device_id),
            json={
                "loginId":  account['loginId'],
                "otp":      otp,
                "deviceId": device_id
            }
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

# ─────────────────────────────────────────────
#  AUTHENTICATE  (login → fresh token)
# ─────────────────────────────────────────────

def authenticate(account, device_id):
    """Login flow. Returns token or None."""
    print(colored("   🔐 Logging in...", 'yellow'))

    if not api_check_passcode(account, device_id):
        print(colored("   ❌ Passcode check failed.", 'red'))
        return None

    request_ts = time.time()

    if not api_send_otp(account, device_id):
        print(colored("   ❌ OTP send failed.", 'red'))
        return None

    print(colored("   ⏳ Waiting 12s for OTP email...", 'cyan'))
    time.sleep(12)

    otp = fetch_otp(account['email'], account['gmail_app_password'], request_ts)
    if not otp:
        print(colored("   ❌ OTP not found in Gmail.", 'red'))
        return None

    print(colored(f"   📨 OTP: {otp}", 'cyan'))

    resp  = api_verify_otp(account, otp, device_id)
    token = resp and resp.get('data', {}).get('accessToken')
    if not token:
        print(colored("   ❌ OTP verification failed.", 'red'))
        return None

    print(colored("   ✅ Login successful!", 'green', attrs=['bold']))
    return token

# ─────────────────────────────────────────────
#  MINING APIS
# ─────────────────────────────────────────────

def api_get_user_info(token, device_id):
    try:
        r = requests.get(
            "https://prod.interlinklabs.ai/api/v1/auth/current-user-full"
            "?include=userInfo%2Ctoken%2CisClaimable",
            headers={
                **base_headers(device_id, token),
                'if-modified-since': datetime.now(timezone.utc)
                                     .strftime('%a, %d %b %Y %H:%M:%S GMT')
            }
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def api_claim_airdrop(token, device_id):
    try:
        r = requests.post(
            "https://prod.interlinklabs.ai/api/v1/token/claim-airdrop",
            headers={**base_headers(device_id, token), 'content-length': '0'}
        )
        return r.status_code == 200
    except Exception:
        return False

def api_check_group(token, device_id, group_id):
    try:
        r = requests.post(
            "https://prod.interlinklabs.ai/api/v1/group-mining/get-detail-group-mining",
            headers=base_headers(device_id, token),
            json={"groupId": group_id}
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def api_claim_group(token, device_id, group_id):
    try:
        r = requests.post(
            "https://prod.interlinklabs.ai/api/v1/group-mining/claim-group-mining",
            headers=base_headers(device_id, token),
            json={"groupId": group_id}
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

# ─────────────────────────────────────────────
#  FIRST RUN  –  login to learn the schedule
# ─────────────────────────────────────────────

def first_run(account, device_id):
    """
    Login once, fetch user info + group info,
    save next claim timestamps to disk.
    Returns (next_airdrop_ms, next_group_ms) or None on failure.
    """
    login_id = account['loginId']
    group_id = account.get('groupId', '')

    token = authenticate(account, device_id)
    if not token:
        return None

    # ── airdrop schedule ──────────────────────
    user_info = api_get_user_info(token, device_id)
    if not user_info:
        print(colored("   ❌ Could not fetch user info.", 'red'))
        return None

    data      = user_info.get('data', {})
    ui        = data.get('userInfo', {})
    tok       = data.get('token', {})
    claimable = data.get('isClaimable', {})

    print(colored(
        f"   👤 {ui.get('username')}  |  🪙 {tok.get('interlinkGoldTokenAmount', 0)} ITLG",
        'white'
    ))

    # If airdrop is already claimable, claim it now and schedule +4 h
    next_airdrop_ms = 0
    print(colored("\n   ┌─ Solo Airdrop", 'yellow', attrs=['bold']))
    if claimable.get('isClaimable'):
        print(colored("   │  🎯 Ready! Claiming...", 'green'))
        if api_claim_airdrop(token, device_id):
            print(colored("   │  ✅ Airdrop claimed!", 'green', attrs=['bold']))
            next_airdrop_ms = get_timestamp() + (4 * 3600 * 1000)
        else:
            print(colored("   │  ❌ Claim failed. Will retry next wake.", 'red'))
            next_airdrop_ms = get_timestamp() + (5 * 60 * 1000)  # retry in 5 min
    else:
        next_airdrop_ms = claimable.get('nextFrame', get_timestamp() + 4 * 3600 * 1000)
        secs = time_remaining_seconds(next_airdrop_ms)
        print(colored(f"   │  ⏰ Next in {format_time(secs)}", 'cyan'))

    # ── group schedule ────────────────────────
    next_group_ms = 0
    if group_id:
        print(colored("\n   ├─ Group Mining", 'magenta', attrs=['bold']))
        g_resp = api_check_group(token, device_id, group_id)

        if g_resp and g_resp.get('data'):
            g = g_resp['data']
            print(colored(
                f"   │  Group {g.get('groupId')}  │  {g.get('statusLabel')}  │  "
                f"Reward: {g.get('totalReward')}",
                'magenta'
            ))

            if g.get('status') == "READY_TO_CLAIM":
                print(colored("   │  🎯 Ready! Claiming...", 'green'))
                c = api_claim_group(token, device_id, group_id)
                if c:
                    cd = c.get('data', {})
                    print(colored("   │  ✅ Group claimed!", 'green', attrs=['bold']))
                    print(colored(
                        f"   │  💎 Reward {cd.get('totalReward')}  │  "
                        f"Claimable {cd.get('maxClaimable')}", 'yellow'
                    ))
                    next_group_ms = get_timestamp() + (24 * 3600 * 1000)
                else:
                    print(colored("   │  ❌ Claim failed. Will retry next wake.", 'red'))
                    next_group_ms = get_timestamp() + (5 * 60 * 1000)
            else:
                raw = g.get('nextTimeClaim', 0)
                next_group_ms = raw if raw > 0 else get_timestamp() + (24 * 3600 * 1000)
                secs = time_remaining_seconds(next_group_ms)
                print(colored(f"   │  ⏰ Next in {format_time(secs)}", 'cyan'))
        else:
            print(colored("   │  ⚠️  Could not fetch group info.", 'yellow'))
            next_group_ms = get_timestamp() + (24 * 3600 * 1000)

    print(colored("   └─────────────────────────────────────────", 'cyan'))

    # ── save schedule ─────────────────────────
    save_schedule(login_id, next_airdrop_ms, next_group_ms)
    print(colored(
        f"\n   💾 Schedule saved.  "
        f"Airdrop: {format_time(time_remaining_seconds(next_airdrop_ms))}  │  "
        f"Group: {format_time(time_remaining_seconds(next_group_ms)) if next_group_ms else 'N/A'}",
        'green'
    ))

    return next_airdrop_ms, next_group_ms

# ─────────────────────────────────────────────
#  CLAIM RUN  –  wake up, login, claim, save new schedule
# ─────────────────────────────────────────────

def claim_run(account, device_id, which_airdrop, which_group):
    """
    Login once, claim whatever is due, save updated schedule.
    which_airdrop / which_group = True means this claim is due now.
    Returns updated (next_airdrop_ms, next_group_ms) or None on auth fail.
    """
    login_id = account['loginId']
    group_id = account.get('groupId', '')

    # Load current schedule from disk
    schedule       = load_schedule(login_id) or {}
    next_airdrop_ms = schedule.get('next_airdrop_ms', 0)
    next_group_ms   = schedule.get('next_group_ms', 0)

    token = authenticate(account, device_id)
    if not token:
        return None

    # ── Airdrop ───────────────────────────────
    print(colored("\n   ┌─ Solo Airdrop", 'yellow', attrs=['bold']))
    if which_airdrop:
        print(colored("   │  🎯 Claiming...", 'green'))
        if api_claim_airdrop(token, device_id):
            print(colored("   │  ✅ Airdrop claimed!", 'green', attrs=['bold']))
            next_airdrop_ms = get_timestamp() + (4 * 3600 * 1000)
        else:
            print(colored("   │  ❌ Claim failed. Retry in 5 min.", 'red'))
            next_airdrop_ms = get_timestamp() + (5 * 60 * 1000)
    else:
        secs = time_remaining_seconds(next_airdrop_ms)
        print(colored(f"   │  ⏰ Not due yet. Next in {format_time(secs)}", 'cyan'))

    # ── Group Mining ──────────────────────────
    if group_id:
        print(colored("\n   ├─ Group Mining", 'magenta', attrs=['bold']))
        if which_group:
            print(colored("   │  🎯 Claiming...", 'green'))
            c = api_claim_group(token, device_id, group_id)
            if c:
                cd = c.get('data', {})
                print(colored("   │  ✅ Group claimed!", 'green', attrs=['bold']))
                print(colored(
                    f"   │  💎 Reward {cd.get('totalReward')}  │  "
                    f"Claimable {cd.get('maxClaimable')}", 'yellow'
                ))
                next_group_ms = get_timestamp() + (24 * 3600 * 1000)
            else:
                print(colored("   │  ❌ Claim failed. Retry in 5 min.", 'red'))
                next_group_ms = get_timestamp() + (5 * 60 * 1000)
        else:
            secs = time_remaining_seconds(next_group_ms)
            print(colored(f"   │  ⏰ Not due yet. Next in {format_time(secs)}", 'cyan'))

    print(colored("   └─────────────────────────────────────────", 'cyan'))

    # Save updated schedule
    save_schedule(login_id, next_airdrop_ms, next_group_ms)
    print(colored(
        f"\n   💾 Schedule updated.  "
        f"Airdrop: {format_time(time_remaining_seconds(next_airdrop_ms))}  │  "
        f"Group: {format_time(time_remaining_seconds(next_group_ms)) if next_group_ms else 'N/A'}",
        'green'
    ))

    return next_airdrop_ms, next_group_ms

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    clear_terminal()
    display_banner()

    accounts = read_credentials()
    if not accounts:
        print(colored("❌ No accounts loaded. Exiting.", 'red'))
        return

    print(colored(
        f"  ✨ {len(accounts)} account(s) loaded.\n",
        'green', attrs=['bold']
    ))

    # ── Step 1: first run for accounts with no saved schedule ──
    print(colored("─" * 62, 'cyan'))
    print(colored("  📋 Initialising schedules...", 'yellow', attrs=['bold']))
    print(colored("─" * 62, 'cyan'))

    for idx, account in enumerate(accounts, 1):
        login_id  = account['loginId']
        device_id = get_device_id(login_id)

        print(colored(
            f"\n╔══════════════════════════════════════════════════════════╗\n"
            f"║  [{idx}/{len(accounts)}]  {account['email'].ljust(49)}║\n"
            f"╚══════════════════════════════════════════════════════════╝",
            'cyan', attrs=['bold']
        ))

        schedule = load_schedule(login_id)
        if schedule:
            a_secs = time_remaining_seconds(schedule['next_airdrop_ms'])
            g_secs = time_remaining_seconds(schedule.get('next_group_ms', 0))
            print(colored(
                f"   ✅ Existing schedule found.\n"
                f"   🪙 Airdrop in {format_time(a_secs)}  │  "
                f"⛏️  Group in {format_time(g_secs)}",
                'green'
            ))
        else:
            print(colored("   ℹ️  No schedule found. Logging in to fetch...", 'yellow'))
            first_run(account, device_id)

        time.sleep(2)

    # ── Step 2: main sleep → wake → claim loop ──
    print(colored("\n" + "═" * 62, 'cyan', attrs=['bold']))
    print(colored("  🚀 All schedules ready. Entering claim loop...", 'green', attrs=['bold']))
    print(colored("═" * 62 + "\n", 'cyan', attrs=['bold']))

    while True:
        try:
            # Find the next wake-up time across ALL accounts
            all_next_times = []

            for account in accounts:
                login_id = account['loginId']
                schedule = load_schedule(login_id)
                if not schedule:
                    continue
                all_next_times.append(schedule['next_airdrop_ms'])
                g = schedule.get('next_group_ms', 0)
                if g > 0:
                    all_next_times.append(g)

            if not all_next_times:
                print(colored("  ⚠️  No schedules found. Re-initialising...", 'yellow'))
                time.sleep(30)
                continue

            # Sleep until the earliest claim across all accounts
            earliest_ms  = min(all_next_times)
            sleep_secs   = max(0, int((earliest_ms - get_timestamp()) / 1000)) + 10
            wake_at      = datetime.fromtimestamp(time.time() + sleep_secs).strftime('%Y-%m-%d %H:%M:%S')

            print(colored(
                f"  😴 Sleeping {format_time(sleep_secs)}  │  Wake at {wake_at}\n",
                'yellow', attrs=['bold']
            ))

            # Countdown
            remaining = sleep_secs
            while remaining > 0:
                print(colored(
                    f"  ⏰  Next claim in {format_time(remaining)}   ",
                    'cyan'
                ), end='\r')
                chunk = min(60, remaining)
                time.sleep(chunk)
                remaining -= chunk

            # ── Wake up ──────────────────────────────
            clear_terminal()
            display_banner()
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(colored(f"  ⏰ Woke up at {now_str}", 'yellow', attrs=['bold']))
            print(colored("─" * 62, 'cyan'))

            now_ms = get_timestamp()

            for idx, account in enumerate(accounts, 1):
                login_id  = account['loginId']
                device_id = get_device_id(login_id)
                schedule  = load_schedule(login_id)

                if not schedule:
                    continue

                next_airdrop_ms = schedule.get('next_airdrop_ms', 0)
                next_group_ms   = schedule.get('next_group_ms', 0)

                # Is anything due for this account?
                airdrop_due = next_airdrop_ms <= now_ms
                group_due   = next_group_ms > 0 and next_group_ms <= now_ms

                if not airdrop_due and not group_due:
                    # Nothing due for this account yet, skip
                    continue

                print(colored(
                    f"\n╔══════════════════════════════════════════════════════════╗\n"
                    f"║  [{idx}/{len(accounts)}]  {account['email'].ljust(49)}║\n"
                    f"╚══════════════════════════════════════════════════════════╝",
                    'cyan', attrs=['bold']
                ))

                # Login ONCE per account, claim everything due
                claim_run(account, device_id, airdrop_due, group_due)
                time.sleep(2)

            print(colored("\n" + "═" * 62, 'cyan', attrs=['bold']))
            print(colored("  ✅ Claim cycle done.", 'green', attrs=['bold']))
            print(colored("═" * 62, 'cyan', attrs=['bold']))

        except KeyboardInterrupt:
            print(colored("\n\n  👋 Stopped by user. Bye!\n", 'yellow', attrs=['bold']))
            break
        except Exception as e:
            print(colored(f"\n  ❌ Unexpected error: {e}", 'red', attrs=['bold']))
            print(colored("  ⏳ Retrying in 5 minutes…\n", 'yellow'))
            time.sleep(300)

if __name__ == "__main__":
    main()
