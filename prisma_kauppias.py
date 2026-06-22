import time
import requests
from datetime import datetime

# ==================== CONFIGURATION ====================
API_URL = "https://storefront-api.prisma.fi/products/111354656/availability?category=elektroniikka%2Fgaming%2Fkerailykortit-ja-tuotteet"

# Scan interval in seconds (180 seconds = 3 minutes)
CHECK_INTERVAL = 180 

# 🚨 CHOOSE YOUR UNIQUE TOPIC NAME HERE
# Type this exact same name into your phone's ntfy app to subscribe!
NTFY_TOPIC = "prisma-pokemon-7739"
# =======================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
    "Origin": "https://www.prisma.fi",
    "Referer": "https://www.prisma.fi/"
}

def send_ntfy_alert(store_name, old_shelf, new_shelf, old_cc, new_cc):
    """Sends a push notification directly to your phone via ntfy.sh"""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    
    # Construct a clean message for your phone screen
    message = (
        f" {store_name}\n"
        f" Shelf: {old_shelf} -> {new_shelf}\n"
        f" Pickup: {old_cc} -> {new_cc}"
    )
    
    headers = {
        "Title": "PRISMA STOCK UPDATE",
        "Priority": "high",          # Makes your phone buzz/sound even in background
        "Tags": "warning,shopping_bags" # Adds emojis to the notification bar
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

def monitor_stock():
    print("🚀 Starting Direct Prisma Storefront API Inventory Monitor")
    print(f"⏱️ Interrogating live balances every {CHECK_INTERVAL // 60} minutes. Press Ctrl+C to stop.\n")
    print(f"📲 ntfy target topic active: https://ntfy.sh/{NTFY_TOPIC}\n")
    
    last_state = {}
    is_first_run = True
    
    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = fetch_live_inventory()
        
        if data is not None:
            current_state = {}
            
            # 1. Capture Central Webstore stock
            ecom_quantity = int(data.get("ecomQuantity", 0))
            current_state["📦 ONLINE WEBSTORE"] = {
                "shelf_qty": ecom_quantity,
                "cc_qty": 0,
                "is_online": True
            }
            
            # 2. Process physical locations using the exact JSON keys discovered
            store_list = data.get("storeQuantities", [])
            for store in store_list:
                name = store.get("displayName", f"Unknown Store ({store.get('storeId')})")
                
                # Extract the precise inventory metrics
                shelf_qty = int(store.get("rawShelfQuantity", 0))
                cc_qty = int(store.get("clickAndCollectQuantity", 0))
                
                current_state[name] = {
                    "shelf_qty": shelf_qty,
                    "cc_qty": cc_qty,
                    "is_online": False
                }
            
            # 3. First Run: Initialize baseline configuration
            if is_first_run:
                print(f"[{timestamp}] ✅ Connection Successful! Tracking {len(current_state) - 1} physical stores + Central Online Warehouse.")
                print(f"   • Online Webstore Stock: {ecom_quantity} units available")
                
                # Find physical locations that actually have stock on shelves
                stores_with_stock = {
                    k: v for k, v in current_state.items() 
                    if v["shelf_qty"] > 0 and not v["is_online"]
                }
                
                if stores_with_stock:
                    print("\n🔥 Physical local stores with active shelf stock:")
                    for store, details in stores_with_stock.items():
                        print(f"   • {store}: {details['shelf_qty']} on shelf (Click & Collect: {details['cc_qty']})")
                else:
                    print("   • Physical Stores: 0 units on local shelves nationwide.")
                
                print("\n📡 Active monitor engaged. Watching for changes...\n")
                last_state = current_state
                is_first_run = False
            
            # 4. Subsequent Runs: Detect stock variations
            else:
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
                            
                            # 🚀 THIS IS WHERE THE FUNCTION TRiggers
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
                
                last_state = current_state
        else:
            print(f"[{timestamp}] API scan dropped. Retrying next cycle.")
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        monitor_stock()
    except KeyboardInterrupt:
        print("\n👋 Monitor shutting down cleanly.")