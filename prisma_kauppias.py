import json
import os
import requests
from datetime import datetime

# ==================== CONFIGURATION ====================
# TÄN VOI VAIHTAA HALUAMAANSA TUOTTEESEEN, PITÄÄ KUITENKI LÖYTÄÄ SEN TUOTTEEN API LINKKI, DEVELOPER CONSOLE AUKI, KLIKKAA TUOTETTA, KATO NETWORK TÄBILTÄ MIHIN KUTSU LÄHTEE
API_URL = "https://storefront-api.prisma.fi/products/111354656/availability?category=elektroniikka%2Fgaming%2Fkerailykortit-ja-tuotteet"
# TOPIC NIMI
NTFY_TOPIC = "prisma-pokemon-7739"
STATE_FILE = "last_state.json"  # GitHub Actions cache handles this file
# =======================================================

# KOIJATAAN ETTÄ OLLAAN IHMINEN :D 
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
    "Origin": "https://www.prisma.fi",
    "Referer": "https://www.prisma.fi/"
}

def send_ntfy_alert(store_name, old_shelf, new_shelf, old_cc, new_cc):
    """Sends a push notification directly via ntfy.sh with live stock quantities."""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    
    # Cleaned message formatting designed for a single snapshot alert
    message = (
        f" 🏪 {store_name}\n"
        f" 📦 HYLLYSSÄ: {old_shelf} -> {new_shelf}\n"
        f" 🛍️ NOUDETTAVISSA: {old_cc} -> {new_cc}"
    )
    
    headers = {
        "Title": "PRISMA STOCK UPDATE",
        "Priority": "high",          # Emt tekeekö jotai mut pitäis tulla puhelimeen piip
        "Tags": "warning" # Tästä tulee emoji varotuskolmio
    }
    
    try:
        response = requests.post(url, data=message.encode('utf-8'), headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"ntfy server returned an error: {response.status_code}")
    except Exception as e:
        print(f"Failed to send ntfy push notification: {e}")

def fetch_live_inventory():
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connection Error: {e}")
        return None

def load_last_state():
    """Loads previous inventory run if restored by GH Actions Cache step."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to read state file: {e}")
    return {}

def save_current_state(state):
    """Saves inventory configuration locally so GH Actions can upload it."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Failed to save state file: {e}")

def monitor_stock():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = fetch_live_inventory()
    
    if data is not None:
        last_state = load_last_state()
        current_state = {}
        
        # 1. Process Online Central Warehouse Stock
        ecom_quantity = int(data.get("ecomQuantity", 0))
        current_state["📦 ONLINE WEBSTORE"] = {
            "shelf_qty": ecom_quantity,
            "cc_qty": 0,
            "is_online": True
        }
        
        # 2. Process physical brick-and-mortar stores
        store_list = data.get("storeQuantities", [])
        for store in store_list:
            name = store.get("displayName", f"Unknown Store ({store.get('storeId')})")
            shelf_qty = int(store.get("rawShelfQuantity", 0))
            cc_qty = int(store.get("clickAndCollectQuantity", 0))
            
            current_state[name] = {
                "shelf_qty": shelf_qty,
                "cc_qty": cc_qty,
                "is_online": False
            }
            
        # 3. Handle First Run / Cache Missing
        if not last_state:
            print(f"[{timestamp}] ✅ Connection Successful! Tracking changes starting from next run.")
            print(f"   • Online Webstore Stock: {ecom_quantity} units available")
            save_current_state(current_state)
            return

        # 4. Subsequent Runs: Cross-compare state
        changes_detected = False
        
        for store_name, current_details in current_state.items():
            old_details = last_state.get(store_name)
            
            if old_details:
                shelf_changed = current_details["shelf_qty"] != old_details["shelf_qty"]
                cc_changed = current_details["cc_qty"] != old_details["cc_qty"]
                
                if shelf_changed or cc_changed:
                    print(f"🔔 [STOCK CHANGE DETECTED] {store_name} inventory updated!")
                    print(f"   ❌ Old State -> Shelf: {old_details['shelf_qty']} | Pickup: {old_details['cc_qty']}")
                    print(f"   ✅ New State -> Shelf: {current_details['shelf_qty']} | Pickup: {current_details['cc_qty']}")
                    
                    # 🚀 THIS IS WHERE THE FUNCTION TRIGGERS
                    send_ntfy_alert(
                        store_name=store_name,
                        old_shelf=old_details['shelf_qty'],
                        new_shelf=current_details['shelf_qty'],
                        old_cc=old_details['cc_qty'],
                        new_cc=current_details['cc_qty']
                    )
                    changes_detected = True

        if not changes_detected:
            print(f"[{timestamp}] Scan completed: No stock changes detected.")
            
        save_current_state(current_state)
    else:
        print(f"[{timestamp}] API processing failed this cycle.")

if __name__ == "__main__":
    monitor_stock()
