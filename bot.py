import requests
import json
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

# Clear Terminal Screen
def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

# Banner
def display_banner():
    banner = """
    ╔══════════════════════════════════════════╗
    ║  Interlink Mining ITLG Bot (Multi-Acc)   ║
    ║  Powered By C G M                        ║
    ╚══════════════════════════════════════════╝
    """
    print(colored(banner, 'cyan'))

# Read credentials from data.txt (Line by Line Format)
def read_credentials():
    accounts = []
    try:
        with open('data.txt', 'r') as file:
            lines = file.readlines()
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                # အလွတ်တွေနဲ့ # ပါတဲ့စာကြောင်းတွေကို ကျော်မယ်
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split('|')
                if len(parts) >= 5:
                    account = {
                        "loginId": parts[0].strip(),
                        "passcode": parts[1].strip(),
                        "email": parts[2].strip(),
                        "gmail_app_password": parts[3].strip(),
                        "groupId": parts[4].strip()
                    }
                    accounts.append(account)
                else:
                    print(colored(f"Line {line_num} format error. Expected 5 parts separated by '|'", 'red'))
        return accounts
    except Exception as e:
        print(colored(f"Error reading credentials from data.txt: {e}", 'red'))
        return None

# Generate or load device ID per account
def get_device_id(login_id):
    filename = f'deviceid_{login_id}.txt'
    try:
        with open(filename, 'r') as file:
            device_id = file.read().strip()
            if device_id:
                return device_id
    except FileNotFoundError:
        pass
    
    # Generate new device ID
    device_id = uuid.uuid4().hex[:16]
    with open(filename, 'w') as file:
        file.write(device_id)
    return device_id

# Header Generation
def generate_random_headers():
    return {
        'x-signature': base64.b64encode(os.urandom(32)).decode('utf-8')[:44],
        'x-content-hash': base64.b64encode(os.urandom(32)).decode('utf-8')[:44]
    }

def get_timestamp():
    return int(time.time() * 1000)

# Token Management per account
def read_token(login_id):
    try:
        with open(f'token_{login_id}.txt', 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        return None

def save_token(login_id, token):
    with open(f'token_{login_id}.txt', 'w') as file:
        file.write(token)

def delete_token(login_id):
    filename = f'token_{login_id}.txt'
    if os.path.exists(filename):
        os.remove(filename)

def is_token_expired(token):
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp = decoded.get('exp')
        if exp:
            return exp * 1000 < get_timestamp()
        return True
    except:
        return True

# Fetch OTP from Gmail
def fetch_otp(email_address, app_password, request_timestamp):
    try:
        imap = imaplib.IMAP4_SSL('imap.gmail.com')
        imap.login(email_address, app_password)
        
        folders_to_check = ['INBOX', '"[Gmail]/Spam"']
        valid_otp = None
        latest_valid_time = 0

        for folder in folders_to_check:
            try:
                imap.select(folder)
                _, data = imap.search(None, '(FROM "noreply@interlinklabs.org")')
                if not data[0]:
                    continue
                
                email_ids = data[0].split()[-5:]
                
                for email_id in reversed(email_ids):
                    _, msg_data = imap.fetch(email_id, '(RFC822)')
                    email_body = msg_data[0][1]
                    msg = email.message_from_bytes(email_body)
                    
                    date_tuple = email.utils.parsedate_tz(msg['Date'])
                    if date_tuple:
                        email_timestamp = email.utils.mktime_tz(date_tuple)
                        if email_timestamp >= (request_timestamp - 180):
                            otp = None
                            
                            if msg.is_multipart():
                                for part in msg.walk():
                                    content_type = part.get_content_type()
                                    if content_type == 'text/plain':
                                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        match = re.search(r'\b\d{6}\b', body)
                                        if match:
                                            otp = match.group(0)
                                            break
                                    elif content_type == 'text/html':
                                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        soup = BeautifulSoup(body, 'html.parser')
                                        text = soup.get_text()
                                        match = re.search(r'\b\d{6}\b', text)
                                        if match:
                                            otp = match.group(0)
                                            break
                            else:
                                content_type = msg.get_content_type()
                                if content_type == 'text/plain':
                                    body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    match = re.search(r'\b\d{6}\b', body)
                                    if match:
                                        otp = match.group(0)
                                elif content_type == 'text/html':
                                    body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    soup = BeautifulSoup(body, 'html.parser')
                                    text = soup.get_text()
                                    match = re.search(r'\b\d{6}\b', text)
                                    if match:
                                        otp = match.group(0)

                            if otp:
                                if email_timestamp > latest_valid_time:
                                    latest_valid_time = email_timestamp
                                    valid_otp = otp

            except Exception as e:
                pass 

        imap.logout()
        return valid_otp
            
    except Exception as e:
        return None

# APIs
def login_check_passcode(credentials, device_id):
    url = "https://prod.interlinklabs.ai/api/v1/auth/check-passcode"
    headers = {
        'accept': '*/*',
        'x-date': str(get_timestamp()),
        'x-unique-id': device_id,
        'x-model': 'Pixel 4',
        'x-brand': 'google',
        'x-system-name': 'Android',
        'x-device-id': 'smdk6400',
        'x-bundle-id': 'org.ai.interlinklabs.interlinkId',
        'content-type': 'application/json',
        'accept-encoding': 'gzip',
        'user-agent': 'okhttp/4.12.0'
    }
    headers.update(generate_random_headers())
    body = {
        "loginId": credentials['loginId'],
        "passcode": credentials['passcode'],
        "deviceId": device_id
    }
    try:
        response = requests.post(url, headers=headers, json=body)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def send_otp_email(credentials, device_id):
    url = "https://prod.interlinklabs.ai/api/v1/auth/send-otp-email-verify-login"
    headers = {
        'accept': '*/*',
        'x-date': str(get_timestamp()),
        'x-unique-id': device_id,
        'x-model': 'Pixel 4',
        'x-brand': 'google',
        'x-system-name': 'Android',
        'x-device-id': 'smdk6400',
        'x-bundle-id': 'org.ai.interlinklabs.interlinkId',
        'content-type': 'application/json',
        'accept-encoding': 'gzip',
        'user-agent': 'okhttp/4.12.0'
    }
    headers.update(generate_random_headers())
    body = {
        "loginId": credentials['loginId'],
        "passcode": credentials['passcode'],
        "email": credentials['email'],
        "deviceId": device_id
    }
    try:
        response = requests.post(url, headers=headers, json=body)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def check_otp(credentials, otp, device_id):
    url = "https://prod.interlinklabs.ai/api/v1/auth/check-otp-email-verify-login"
    headers = {
        'accept': '*/*',
        'x-date': str(get_timestamp()),
        'x-unique-id': device_id,
        'x-model': 'Pixel 4',
        'x-brand': 'google',
        'x-system-name': 'Android',
        'x-device-id': 'smdk6400',
        'x-bundle-id': 'org.ai.interlinklabs.interlinkId',
        'content-type': 'application/json',
        'accept-encoding': 'gzip',
        'user-agent': 'okhttp/4.12.0'
    }
    headers.update(generate_random_headers())
    body = {
        "loginId": credentials['loginId'],
        "otp": otp,
        "deviceId": device_id
    }
    try:
        response = requests.post(url, headers=headers, json=body)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def get_user_info(token, device_id):
    url = "https://prod.interlinklabs.ai/api/v1/auth/current-user-full?include=userInfo%2Ctoken%2CisClaimable"
    headers = {
        'accept': '*/*',
        'authorization': f'Bearer {token}',
        'x-date': str(get_timestamp()),
        'x-unique-id': device_id,
        'x-model': 'Pixel 4',
        'x-brand': 'google',
        'x-system-name': 'Android',
        'x-device-id': 'smdk6400',
        'x-bundle-id': 'org.ai.interlinklabs.interlinkId',
        'accept-encoding': 'gzip',
        'user-agent': 'okhttp/4.12.0',
        'if-modified-since': datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    }
    headers.update(generate_random_headers())
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def claim_airdrop(token, device_id):
    url = "https://prod.interlinklabs.ai/api/v1/token/claim-airdrop"
    headers = {
        'accept': '*/*',
        'authorization': f'Bearer {token}',
        'x-date': str(get_timestamp()),
        'x-unique-id': device_id,
        'x-model': 'Pixel 4',
        'x-brand': 'google',
        'x-system-name': 'Android',
        'x-device-id': 'smdk6400',
        'x-bundle-id': 'org.ai.interlinklabs.interlinkId',
        'content-length': '0',
        'accept-encoding': 'gzip',
        'user-agent': 'okhttp/4.12.0'
    }
    headers.update(generate_random_headers())
    try:
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            print(colored(f"   ✅ Airdrop claimed successfully!", 'green', attrs=['bold']))
        else:
            print(colored(f"   ❌ Airdrop claim failed.", 'red'))
    except Exception as e:
        print(colored(f"   ❌ Error claiming airdrop: {e}", 'red'))

def check_group_mining(token, device_id, group_id):
    url = "https://prod.interlinklabs.ai/api/v1/group-mining/get-detail-group-mining"
    headers = {
        'accept': '*/*',
        'authorization': f'Bearer {token}',
        'x-date': str(get_timestamp()),
        'x-unique-id': device_id,
        'x-model': 'Pixel 4',
        'x-brand': 'google',
        'x-system-name': 'Android',
        'x-device-id': 'smdk6400',
        'x-bundle-id': 'org.ai.interlinklabs.interlinkId',
        'content-type': 'application/json',
        'accept-encoding': 'gzip',
        'user-agent': 'okhttp/4.12.0'
    }
    headers.update(generate_random_headers())
    body = {"groupId": group_id}
    try:
        response = requests.post(url, headers=headers, json=body)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def claim_group_mining(token, device_id, group_id):
    url = "https://prod.interlinklabs.ai/api/v1/group-mining/claim-group-mining"
    headers = {
        'accept': '*/*',
        'authorization': f'Bearer {token}',
        'x-date': str(get_timestamp()),
        'x-unique-id': device_id,
        'x-model': 'Pixel 4',
        'x-brand': 'google',
        'x-system-name': 'Android',
        'x-device-id': 'smdk6400',
        'x-bundle-id': 'org.ai.interlinklabs.interlinkId',
        'content-type': 'application/json',
        'accept-encoding': 'gzip',
        'user-agent': 'okhttp/4.12.0'
    }
    headers.update(generate_random_headers())
    body = {"groupId": group_id}
    try:
        response = requests.post(url, headers=headers, json=body)
        if response.status_code == 200:
            data = response.json().get('data', {})
            print(colored("   ✅ Group Mining Claim Success!", 'green', attrs=['bold']))
            print(colored(f"   ➤ Reward: {data.get('totalReward')} | Claimable: {data.get('maxClaimable')}", 'magenta'))
        else:
            print(colored(f"   ❌ Group mining claim failed.", 'red'))
    except Exception as e:
        print(colored(f"   ❌ Error claiming group mining: {e}", 'red'))

def time_remaining(next_frame):
    current_time = get_timestamp()
    seconds_left = max((next_frame - current_time) // 1000, 0)
    hours = seconds_left // 3600
    minutes = (seconds_left % 3600) // 60
    seconds = seconds_left % 60
    return f"{hours}h {minutes}m {seconds}s"

# Main Flow
def main():
    clear_terminal()
    display_banner()
    
    # Read all accounts
    accounts = read_credentials()
    if not accounts:
        print(colored("Failed to load credentials from data.txt. Exiting...", 'red'))
        return

    while True:
        try:
            clear_terminal()
            display_banner()
            print(colored(f"● Bot Status: [ ACTIVE ] | Processing {len(accounts)} Account(s)...", 'green', attrs=['bold']))
            print(colored("==========================================================", 'cyan'))

            for idx, account in enumerate(accounts, 1):
                login_id = account.get('loginId')
                email_addr = account.get('email')
                target_group_id = account.get('groupId')
                
                print(colored(f"\n[ Account {idx}/{len(accounts)}: {email_addr} ]", 'yellow', attrs=['bold']))

                device_id = get_device_id(login_id)
                token = read_token(login_id)
                
                # Auto Login / Refresh Token per account
                if not token or is_token_expired(token):
                    print(colored(f"   ⚠️ Token expired. Re-authenticating...", 'yellow'))
                    login_response = login_check_passcode(account, device_id)
                    if not login_response:
                        print(colored("   ❌ Login API failed. Skipping to next account...", 'red'))
                        continue

                    request_timestamp = time.time()
                    otp_response = send_otp_email(account, device_id)
                    if not otp_response:
                        print(colored("   ❌ Send OTP failed. Skipping...", 'red'))
                        continue

                    print(colored("   ⏳ Waiting 10s for OTP...", 'cyan'))
                    time.sleep(10)
                    
                    otp = fetch_otp(account['email'], account['gmail_app_password'], request_timestamp)
                    if not otp:
                        print(colored("   ❌ Failed to fetch OTP from Gmail. Skipping...", 'red'))
                        continue

                    verify_response = check_otp(account, otp, device_id)
                    if verify_response and verify_response.get('data', {}).get('accessToken'):
                        token = verify_response['data']['accessToken']
                        save_token(login_id, token)
                        print(colored("   ✅ Authentication successful!", 'green'))
                    else:
                        print(colored("   ❌ OTP Verification failed. Skipping...", 'red'))
                        continue

                # Fetch Info
                user_info = get_user_info(token, device_id)
                if not user_info:
                    print(colored("   ❌ Failed to fetch info. Token might be invalid.", 'red'))
                    delete_token(login_id)
                    continue 

                # Data parsing
                data = user_info.get('data', {})
                user_info_data = data.get('userInfo', {})
                token_data = data.get('token', {})
                claimable_data = data.get('isClaimable', {})

                print(colored(f"   ➤ ID: {user_info_data.get('loginId')} | Username: {user_info_data.get('username')}", 'white'))
                print(colored(f"   ➤ Gold Tokens: {token_data.get('interlinkGoldTokenAmount', 0)}", 'yellow'))
                print(colored(f"   ➤ Airdrop Ready: {claimable_data.get('isClaimable', False)} | Next: {time_remaining(claimable_data.get('nextFrame', 0))}", 'cyan'))

                # Normal Claim
                if claimable_data.get('isClaimable'):
                    print(colored("   >>> Claiming Airdrop...", 'green', attrs=['blink']))
                    claim_airdrop(token, device_id)

                # Group Claim
                if target_group_id:
                    group_info = check_group_mining(token, device_id, target_group_id)
                    if group_info and group_info.get('data'):
                        g_data = group_info['data']
                        g_status = g_data.get('status')
                        print(colored(f"   ➤ Group [{g_data.get('groupId')}]: {g_data.get('statusLabel')} | Reward: {g_data.get('totalReward')}", 'magenta'))
                        
                        if g_status == "READY_TO_CLAIM":
                            print(colored("   >>> Claiming Group Mining...", 'green', attrs=['blink']))
                            claim_group_mining(token, device_id, target_group_id)
                        else:
                            next_time = g_data.get('nextTimeClaim', 0)
                            if next_time > 0:
                                print(colored(f"   ➤ Group Next Claim: {time_remaining(next_time)}", 'cyan'))

                time.sleep(2) 

            print(colored("\n==========================================================", 'cyan'))
            print(colored("All accounts checked. Waiting 10 seconds for next cycle...", 'white'))
            time.sleep(10)

        except Exception as e:
            print(colored(f"\n❌ Unexpected Error Occurred: {e} ❌", 'red'))
            print(colored("Resuming in 10 seconds...", 'yellow'))
            time.sleep(10)

if __name__ == "__main__":
    main()
