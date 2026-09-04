import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Configuration via Environment Variables
SPOOLMAN_URL = os.environ.get("SPOOLMAN_URL", "http://192.168.1.100:7912/api/v1")
BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("BIND_PORT", 5000))
DEFAULT_WEIGHT = float(os.environ.get("DEFAULT_WEIGHT", 1000.0))
DEFAULT_DIAMETER = float(os.environ.get("DEFAULT_DIAMETER", 1.75))
DEFAULT_DENSITY = float(os.environ.get("DEFAULT_DENSITY", 1.24))

def get_or_create_vendor(name="Bambu Lab"):
    resp = requests.get(f"{SPOOLMAN_URL}/vendor").json()
    for v in resp:
        if v.get("name") == name:
            return v["id"]
    return requests.post(f"{SPOOLMAN_URL}/vendor", json={"name": name}).json()["id"]

def get_or_create_filament(material, color_hex, density, vendor_id):
    resp = requests.get(f"{SPOOLMAN_URL}/filament", params={"vendor_id": vendor_id}).json()
    for f in resp:
        if f.get("name") == material and f.get("color_hex") == color_hex:
            return f["id"]
    
    payload = {
        "name": material,
        "vendor_id": vendor_id,
        "color_hex": color_hex,
        "density": density,
        "diameter": DEFAULT_DIAMETER
    }
    return requests.post(f"{SPOOLMAN_URL}/filament", json=payload).json()["id"]

@app.route('/process_spool', methods=['POST'])
def process_spool():
    data = request.json
    uid = data.get("uid")
    material = data.get("material")
    color_hex = data.get("color_hex")
    density = data.get("density", DEFAULT_DENSITY)

    try:
        vendor_id = get_or_create_vendor()
        filament_id = get_or_create_filament(material, color_hex, density, vendor_id)
        spools = requests.get(f"{SPOOLMAN_URL}/spool", params={"lot_nr": uid}).json()
        
        if spools:
            spool_id = spools[0]["id"]
            requests.patch(f"{SPOOLMAN_URL}/spool/{spool_id}", json={"location": "External Spool"})
            return jsonify({"status": "updated", "spool_id": spool_id, "msg": "Set to active"}), 200
        else:
            new_spool = requests.post(f"{SPOOLMAN_URL}/spool", json={
                "filament_id": filament_id,
                "initial_weight": DEFAULT_WEIGHT,
                "lot_nr": uid,
                "location": "External Spool"
            }).json()
            return jsonify({"status": "created", "spool_id": new_spool["id"]}), 201

    except Exception as e:
        print(f"Error processing spool: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host=BIND_HOST, port=BIND_PORT)
