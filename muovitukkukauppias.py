import json
import os
import re
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# ==================== CONFIGURATION ====================
# Kohdetuote Muovitukussa
URL = "https://www.muovitukku.fi/tuote/pokemon-tcg-first-partner-illustration-collection-series-2/"

# Ilmoituskanavat
NTFY_TOPIC_URL = "https://ntfy.sh/muovitukkukauppias-66666"
# DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"

# Erillinen tilatiedosto Muovitukulle (Ei sekoitu Prisman kanssa)
STATE_FILE = "muovitukku_state.json"

# Toimintojen kytkimet
ENABLE_NTFY = True
ENABLE_DISCORD = False

# AJOMODI: Aseta False jos ajat pilvessä (esim. GitHub Actions CRON 5min välein)
# Aseta True jos haluat testata omalla koneella jatkuvaa looppia taustalla
RUN_LOCAL_LOOP = False
LOOP_INTERVAL_SECONDS = 300
# =======================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def send_ntfy_status(message, title=None, tags=None):
    """Yleiskäyttöinen funktio ntfy-ilmoitusten lähettämiseen."""
    if not ENABLE_NTFY:
        return
    headers = {}
    if title:
        headers["Title"] = title
    if tags:
        headers["Tags"] = tags
        
    try:
        requests.post(NTFY_TOPIC_URL, data=message.encode('utf-8'), headers=headers, timeout=5)
    except Exception as e:
        print(f"[-] ntfy notification failed: {e}")


def load_last_state():
    """Lataa edellisen ajon tilatiedot levyltä/välimuistista."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] Failed to read state file: {e}")
    return {}


def save_current_state(state):
    """Tallentaa nykyisen tilan levylle seuraavaa ajoa varten."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[-] Failed to save state file: {e}")


def monitor_stock():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        response = requests.get(URL, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"[-] Error: Received status code {response.status_code}")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Etsitään oikea dataLayer-skripti sivun lähdekoodista
        script_tag = soup.find('script', string=re.compile(r'gtm4wp-additional-datalayer-pushes-js-after'))
        if not script_tag:
            print("[-] Could not find the targeted dataLayer script tag.")
            return

        # 2. Parsitaan objekti ulos JavaScript-koodista regexillä
        match = re.search(r'dataLayer\.push\((.*?)\);', script_tag.string, re.DOTALL)
        if not match:
            print("[-] Failed to parse dataLayer.push contents.")
            return
            
        data = json.loads(match.group(1))
        items = data.get("ecommerce", {}).get("items", [])
        if not items:
            print("[-] No items found inside the ecommerce object.")
            return
            
        product = items[0]
        name = product.get("item_name")
        status = product.get("stockstatus", "unknown")
        price = product.get("price", 0)
        stock_level = product.get("stocklevel", 0)
        
        # Rakennetaan tämän hetkinen tilakuva
        current_state = {
            "name": name,
            "status": status,
            "stock_level": stock_level,
            "price": price
        }
        
        last_state = load_last_state()
        
        # 3. Ensimmäinen ajo (tai jos tila puuttuu cachesta)
        if not last_state:
            print(f"[{timestamp}] ✅ Connection Successful! Initial state saved for {name}.")
            print(f"   • Status: {status.upper()} | Stock Level: {stock_level}")
            save_current_state(current_state)
            return

        # 4. Verrataan nykyistä tilaa vanhaan tilaan
        status_changed = current_state["status"] != last_state.get("status")
        level_changed = current_state["stock_level"] != last_state.get("stock_level")
        
        if status_changed or level_changed:
            print(f"🔔 [STOCK CHANGE DETECTED] {name} inventory updated!")
            
            # Rakennetaan nätti ilmoitusmuotoilu tilanmuutoksesta
            message_payload = (
                f"🏪 Muovitukku\n"
                f"📦 TUOTE: {name}\n"
                f"🔄 STATUS: {last_state.get('status')} -> {current_state['status']}\n"
                f"📊 MÄÄRÄ: {last_state.get('stock_level')} -> {current_state['stock_level']}\n"
                f"💰 HINTA: {price}€"
            )
            
            if ENABLE_NTFY:
                send_ntfy_status(message_payload, title="MUOVITUKKU STOCK UPDATE", tags="warning,package")
                
            if ENABLE_DISCORD and 'DISCORD_WEBHOOK_URL' in globals():
                discord_payload = {
                    "content": f"🚨 **MUOVITUKKU VARASTOPÄIVITYS SAATANA** 🚨\n\n**{name}**\n🔄 **STATUS:** `{last_state.get('status')}` ➡️ `{current_state['status']}`\n📊 **MÄÄRÄ:** `{last_state.get('stock_level')}` ➡️ `{current_state['stock_level']}`\n💰 **HINTA:** `{price}€`"
                }
                try:
                    requests.post(DISCORD_WEBHOOK_URL, json=discord_payload, timeout=5)
                except Exception as e:
                    print(f"[-] Discord webhook notification failed: {e}")
        else:
            print(f"[{timestamp}] Scan completed: No stock changes detected for {name}.")
            
        save_current_state(current_state)

    except Exception as e:
        print(f"[-] Scraping error during lifecycle execution: {e}")


if __name__ == "__main__":
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if RUN_LOCAL_LOOP:
        # --- LOCAL MODE: Sends startup/shutdown pings because it runs forever ---
        last_state = load_last_state()
        cached_stock = last_state.get("stock_level", "Ei tiedossa")
        
        send_ntfy_status(
            message=f"function activated adn timesttamp: {start_time}", 
            title=f"Monitori Online Tilassa. toimivuus ei taattu. Stockissa on... : {cached_stock}", 
            tags="gear"
        )
        
        print(f"[{start_time}] Starting continuous local loop...")
        try:
            while True:
                monitor_stock()
                time.sleep(LOOP_INTERVAL_SECONDS)
        finally:
            print("Shutting down tracker...")
            send_ntfy_status("deactivated", title="Monitor Offline")
            
    else:
        # --- CLOUD CRON MODE: Silent execution, alerts only on actual stock changes ---
        print(f"[{start_time}] Executing single cloud snapshot run...")
        monitor_stock()