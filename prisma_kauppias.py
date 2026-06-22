import requests
from datetime import datetime

# ==================== CONFIGURATION ====================
API_URL = "https://storefront-api.prisma.fi/products/111354656/availability?category=elektroniikka%2Fgaming%2Fkerailykortit-ja-tuotteet"
NTFY_TOPIC = "prisma-pokemon-7739"
# =======================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
    "Origin": "https://www.prisma.fi",
    "Referer": "https://www.prisma.fi/"
}

def send_ntfy_alert(store_name, shelf_qty, cc_qty):
    """Sends a push notification directly via ntfy.sh using JSON payload."""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    
    message = (
        f"Location: {store_name}\n"
        f"Available on Shelf: {shelf_qty}\n"
        f"Click and Collect: {cc_qty}"
    )
    
    payload = {
        "title": "PRISMA ITEM IN STOCK",
        "message": message,
        "priority": 4, 
        "tags": ["warning", "shopping_bags"]
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Warning: ntfy server returned an error: {response.status_code}")
    except Exception as e:
        print(f"Warning: Failed to send ntfy push notification: {e}")

def fetch_live_inventory():
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connection Error: {e}")
        return None

def monitor_stock():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = fetch_live_inventory()
    
    if data is not None:
        # 1. Process Online Central Warehouse Stock
        ecom_quantity = int(data.get("ecomQuantity", 0))
        if ecom_quantity > 0:
            print(f"Stock found on Central Webstore: {ecom_quantity}")
            send_ntfy_alert("ONLINE WEBSTORE", ecom_quantity, 0)
        
        # 2. Process physical brick-and-mortar stores
        store_list = data.get("storeQuantities", [])
        stock_found_locally = False
        
        for store in store_list:
            name = store.get("displayName", f"Unknown Store ({store.get('storeId')})")
            shelf_qty = int(store.get("rawShelfQuantity", 0))
            cc_qty = int(store.get("clickAndCollectQuantity", 0))
            
            # If there is active inventory in this specific location, alert immediately
            if shelf_qty > 0 or cc_qty > 0:
                print(f"[{timestamp}] Stock found at {name}! Shelf: {shelf_qty} | Pickup: {cc_qty}")
                send_ntfy_alert(name, shelf_qty, cc_qty)
                stock_found_locally = True
                
        if not stock_found_locally and ecom_quantity == 0:
            print(f"[{timestamp}] Scan complete: Out of stock everywhere nationwide.")
    else:
        print(f"[{timestamp}] API processing failed this cycle.")

if __name__ == "__main__":
    monitor_stock()
