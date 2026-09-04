import os
import sys
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Mandatory Spoolman URL configuration
base_url = os.environ.get("SPOOLMAN_URL")
if not base_url:
    print("FATAL ERROR: SPOOLMAN_URL environment variable is mandatory.", file=sys.stderr)
    sys.exit(1)

SPOOLMAN_URL = f"{base_url.rstrip('/')}/api/v1"

# Defaults
BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("BIND_PORT", 5000))
DEFAULT_WEIGHT = float(os.environ.get("DEFAULT_WEIGHT", 1000.0))
DEFAULT_EMPTY_WEIGHT = float(os.environ.get("DEFAULT_EMPTY_WEIGHT", 250.0))
DEFAULT_DIAMETER = float(os.environ.get("DEFAULT_DIAMETER", 1.75))
DEFAULT_DENSITY = float(os.environ.get("DEFAULT_DENSITY", 1.24))
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")

# Bambuddy configurations (Optional but required for auto-assign)
BAMBUDDY_URL = os.environ.get("BAMBUDDY_URL") 
BAMBUDDY_API_KEY = os.environ.get("BAMBUDDY_API_KEY")
PRINTER_ID = os.environ.get("PRINTER_ID")

def get_or_create_vendor(name="Bambu Lab"):
    resp = requests.get(f"{SPOOLMAN_URL}/vendor").json()
    for v in resp:
        if v.get("name") == name:
            return v["id"]
    return requests.post(f"{SPOOLMAN_URL}/vendor", json={"name": name, "empty_weight": DEFAULT_EMPTY_WEIGHT}).json()["id"]

def get_or_create_filament(material_name, color_hex, density, vendor_id):
    # Extract standard material type (e.g. "PLA" from "PLA Basic")
    known_materials = ["PLA", "PETG", "ABS", "ASA", "TPU", "PC", "PA", "PVA"]
    material_type = "Unknown"
    for m in known_materials:
        if m in material_name.upper():
            material_type = m
            break

    resp = requests.get(f"{SPOOLMAN_URL}/filament", params={"vendor_id": vendor_id}).json()
    for f in resp:
        if f.get("name") == material_name and f.get("color_hex") == color_hex:
            return f["id"]
    
    payload = {
        "name": material_name,
        "vendor_id": vendor_id,
        "material": material_type, 
        "color_hex": color_hex,
        "density": density,
        "diameter": DEFAULT_DIAMETER,
        "weight": DEFAULT_WEIGHT,
        "spool_weight": DEFAULT_EMPTY_WEIGHT 
    }
    return requests.post(f"{SPOOLMAN_URL}/filament", json=payload).json()["id"]

def assign_to_bambuddy(spool_id):
    if not BAMBUDDY_URL or not BAMBUDDY_API_KEY or not PRINTER_ID:
        return
    
    # Bambuddy authenticates via Bearer token
    headers = {"Authorization": f"Bearer {BAMBUDDY_API_KEY}", "Content-Type": "application/json"}
    
    # Target the external slot (Tray IDs are usually 0-3 for AMS, 'external' or '254' for external)
    bambuddy_endpoint = f"{BAMBUDDY_URL.rstrip('/')}/api/v1/printers/{PRINTER_ID}/slots/external/assign"
    
    try:
        # Pass the Spoolman ID so Bambuddy links it dynamically
        req = requests.post(bambuddy_endpoint, json={"spoolman_id": spool_id}, headers=headers)
        if req.status_code == 200:
            print(f"[+] Assigned Spool {spool_id} to Bambuddy External Slot")
        else:
            print(f"[-] Bambuddy assignment failed: {req.status_code} - {req.text}")
    except Exception as e:
        print(f"[-] Failed to reach Bambuddy: {e}")

@app.route('/process_spool', methods=['POST'])
def process_spool():
    if AUTH_TOKEN and request.headers.get("X-Auth-Token") != AUTH_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    uid = data.get("uid")
    material_name = data.get("material") 
    color_hex = data.get("color_hex")
    density = data.get("density", DEFAULT_DENSITY)

    try:
        vendor_id = get_or_create_vendor()
        filament_id = get_or_create_filament(material_name, color_hex, density, vendor_id)
        spools = requests.get(f"{SPOOLMAN_URL}/spool", params={"lot_nr": uid}).json()
        
        spool_id = None
        if spools:
            spool_id = spools[0]["id"]
            requests.patch(f"{SPOOLMAN_URL}/spool/{spool_id}", json={"location": "External Spool"})
            status_msg = "updated"
        else:
            new_spool = requests.post(f"{SPOOLMAN_URL}/spool", json={
                "filament_id": filament_id,
                "initial_weight": DEFAULT_WEIGHT,
                "lot_nr": uid,
                "location": "External Spool"
            }).json()
            spool_id = new_spool["id"]
            status_msg = "created"

        # Trigger Bambuddy assignment automatically
        assign_to_bambuddy(spool_id)

        return jsonify({"status": status_msg, "spool_id": spool_id}), 201 if status_msg == "created" else 200

    except Exception as e:
        print(f"Error processing spool: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host=BIND_HOST, port=BIND_PORT)
