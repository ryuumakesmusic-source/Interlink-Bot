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
    """Convert next frame millisecond timestamp to seconds remaining"""
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
                        "loginId":           parts[0].strip(),
                        "passcode":          parts[1].strip(),
                        "email":             parts[2].strip(),
                        "gmail_app_password": parts[3].strip(),
                        "groupId":           parts[4].strip()
                    })
                else:
                    print(colored(f"  ⚠️  Line {line_num}: bad format, skipping.", 'red'))
        return accounts
    except Exception as e:
        print(colored(f"  ❌ Cannot read data.txt: {e}", 'red'))
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
#  TOKEN STORAGE
# ─────────────────────────────────────────────

def read_token(login_id):
    try:
        with open(f'token_{login_id}.txt', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def save_token(login_id, token):
    with open(f'token_{login_id}.txt', 'w') as f:
        f.write(token)

def delete_token(login_id):
    path = f'token_{login_id}.txt'
    if os.path.exists(path):
        os.remove(path)

def is_token_expired(token):
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp = decoded.get('exp')
        if exp:
            # expired if less than 5 min remaining
            return exp * 1000 < (get_timestamp() + 300_000)
        return True
    except:
        return True

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

        valid_otp        = None
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

                    otp = None
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
#  AUTHENTICATE  (login once → return token)
# ─────────────────────────────────────────────

def authenticate(account, device_id):
    """
    Full login flow.
    Returns a fresh token string, or None on failure.
    Logs into Gmail ONCE to grab the OTP.
    """
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

    resp = api_verify_otp(account, otp, device_id)
    token = resp and resp.get('data', {}).get('accessToken')
    if not token:
        print(colored("   ❌ OTP verification failed.", 'red'))
        return None

    save_token(account['loginId'], token)
    print(colored("   ✅ Login successful!", 'green', attrs=['bold']))
    return token

# ─────────────────────────────────────────────
#  MINING APIS  (need valid token)
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
#  PROCESS ONE ACCOUNT
#  Returns: seconds until this account needs
#           attention again (or None on hard fail)
# ─────────────────────────────────────────────

def process_account(account, idx, total):
    login_id  = account['loginId']
    email_addr = account['email']
    group_id  = account.get('groupId', '')

    # ── header ───────────────────────────────
    print(colored(
        f"\n╔══════════════════════════════════════════════════════════╗\n"
        f"║  [{idx}/{total}]  {email_addr.ljust(49)}║\n"
        f"╚══════════════════════════════════════════════════════════╝",
        'cyan', attrs=['bold']
    ))

    device_id = get_device_id(login_id)

    # ── get a valid token ─────────────────────
    token = read_token(login_id)
    if not token or is_token_expired(token):
        token = authenticate(account, device_id)
        if not token:
            return None          # skip this account

    # ── fetch user info (airdrop status) ─────
    user_info = api_get_user_info(token, device_id)
    if not user_info:
        print(colored("   ❌ get_user_info failed – deleting token, will retry next cycle.", 'red'))
        delete_token(login_id)
        return None

    data          = user_info.get('data', {})
    ui            = data.get('userInfo', {})
    tok           = data.get('token', {})
    claimable     = data.get('isClaimable', {})

    print(colored(f"   👤 {ui.get('username')}  |  🪙 {tok.get('interlinkGoldTokenAmount', 0)} ITLG", 'white'))

    # seconds until each claim window
    next_airdrop_sec = time_remaining_seconds(claimable.get('nextFrame', 0))
    next_group_sec   = None   # filled below

    # ── AIRDROP ──────────────────────────────
    print(colored("\n   ┌─ Solo Airdrop", 'yellow', attrs=['bold']))
    if claimable.get('isClaimable'):
        print(colored("   │  🎯 Ready!  Claiming...", 'green'))
        if api_claim_airdrop(token, device_id):
            print(colored("   │  ✅ Airdrop claimed!", 'green', attrs=['bold']))
        else:
            print(colored("   │  ❌ Claim failed.", 'red'))
        # after a successful claim the server resets nextFrame to +4 h
        next_airdrop_sec = 4 * 3600
    else:
        print(colored(f"   │  ⏰ Next in {format_time(next_airdrop_sec)}", 'cyan'))

    # ── GROUP MINING ─────────────────────────
    if group_id:
        print(colored("\n   ├─ Group Mining", 'magenta', attrs=['bold']))
        g_resp = api_check_group(token, device_id, group_id)

        if g_resp and g_resp.get('data'):
            g = g_resp['data']
            print(colored(
                f"   │  Group {g.get('groupId')}  │  {g.get('statusLabel')}  │  "
                f"Reward: {g.get('totalReward')}", 'magenta'
            ))

            if g.get('status') == "READY_TO_CLAIM":
                print(colored("   │  🎯 Ready!  Claiming...", 'green'))
                c_resp = api_claim_group(token, device_id, group_id)
                if c_resp:
                    cd = c_resp.get('data', {})
                    print(colored("   │  ✅ Group claimed!", 'green', attrs=['bold']))
                    print(colored(
                        f"   │  💎 Reward {cd.get('totalReward')}  │  "
                        f"Claimable {cd.get('maxClaimable')}", 'yellow'
                    ))
                    next_group_sec = 24 * 3600
                else:
                    print(colored("   │  ❌ Group claim failed.", 'red'))
            else:
                raw_next = g.get('nextTimeClaim', 0)
                next_group_sec = time_remaining_seconds(raw_next) if raw_next > 0 else None
                if next_group_sec is not None:
                    print(colored(f"   │  ⏰ Next in {format_time(next_group_sec)}", 'cyan'))
        else:
            print(colored("   │  ⚠️  Could not fetch group info.", 'yellow'))

    print(colored("   └─────────────────────────────────────────", 'cyan'))

    # ── return how long until this account needs to wake up ──
    candidates = [next_airdrop_sec]
    if next_group_sec is not None:
        candidates.append(next_group_sec)

    return min(candidates)   # seconds

# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────

def main():
    clear_terminal()
    display_banner()

    accounts = read_credentials()
    if not accounts:
        print(colored("❌ No accounts loaded. Exiting.", 'red'))
        return

    print(colored(
        f"  ✨ {len(accounts)} account(s) loaded.\n"
        f"  Logic: login once per cycle → read next-claim times → sleep until earliest.\n",
        'green', attrs=['bold']
    ))

    cycle = 0
    while True:
        try:
            cycle += 1
            clear_terminal()
            display_banner()

            print(colored(
                f"  🔄 Cycle #{cycle}  │  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  │  "
                f"{len(accounts)} account(s)",
                'yellow', attrs=['bold']
            ))
            print(colored("─" * 62, 'cyan'))

            sleep_candidates = []

            for idx, account in enumerate(accounts, 1):
                secs = process_account(account, idx, len(accounts))
                if secs is not None and secs > 0:
                    sleep_candidates.append(secs)
                time.sleep(2)   # small gap between accounts

            # ── decide how long to sleep ──────────────────
            print(colored("\n" + "═" * 62, 'cyan', attrs=['bold']))

            if sleep_candidates:
                # wake up just when the earliest claim is ready (+10 s buffer)
                sleep_for = min(sleep_candidates) + 10
            else:
                # something went wrong for all accounts – retry in 5 min
                sleep_for = 300

            wake_at = datetime.fromtimestamp(time.time() + sleep_for).strftime('%H:%M:%S')
            print(colored(
                f"  ✅ All done.  Sleeping {format_time(int(sleep_for))}  "
                f"│  wake at {wake_at}",
                'green', attrs=['bold']
            ))
            print(colored("═" * 62 + "\n", 'cyan', attrs=['bold']))

            # countdown (print every 60 s so terminal isn't spammy)
            remaining = int(sleep_for)
            while remaining > 0:
                print(colored(
                    f"  ⏰  Next cycle in {format_time(remaining)} …",
                    'cyan'
                ), end='\r')
                chunk = min(60, remaining)
                time.sleep(chunk)
                remaining -= chunk

        except KeyboardInterrupt:
            print(colored("\n\n  👋 Stopped by user. Bye!\n", 'yellow', attrs=['bold']))
            break
        except Exception as e:
            print(colored(f"\n  ❌ Unexpected error: {e}", 'red', attrs=['bold']))
            print(colored("  ⏳ Retrying in 5 minutes…\n", 'yellow'))
            time.sleep(300)

if __name__ == "__main__":
    main()
