# app.py (nel progetto email_tracker_server)
from flask import Flask, send_from_directory, request, abort, jsonify, redirect
import json
import os
import time
import re
from urllib.parse import unquote_plus

app = Flask(__name__)

TRACKING_DB_FILE = "email_tracking_log.json"


def _load_tracking_data():
    if os.path.exists(TRACKING_DB_FILE):
        with open(TRACKING_DB_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(
                    f"[{time.strftime('%H:%M:%S')}] WARNING: {TRACKING_DB_FILE} is empty or corrupted. Initializing as empty.")
                return {}
    return {}


def _save_tracking_data(data):
    with open(TRACKING_DB_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def record_email_open(tracking_id):
    data = _load_tracking_data()
    # Se l'email è già in uno stato più avanzato (risposta, rimbalzo), non retrocediamo
    if tracking_id in data and data[tracking_id]["status"] not in ["replied", "bounced", "opened"]:
        data[tracking_id]["opened_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
        data[tracking_id]["status"] = "opened"
        _save_tracking_data(data)
        print(f"[{time.strftime('%H:%M:%S')}] Email with ID '{tracking_id}' opened.")
        return True
    elif tracking_id in data:
        print(
            f"[{time.strftime('%H:%M:%S')}] Email with ID '{tracking_id}' already opened or in a final state. Ignoring duplicate open.")
    else:
        print(
            f"[{time.strftime('%H:%M:%S')}] Tracking ID '{tracking_id}' not found in log. Possible invalid pixel request.")
    return False


def record_email_click(tracking_id, original_url):
    data = _load_tracking_data()
    # Se l'email è già in uno stato più avanzato (risposta, rimbalzo), non retrocediamo
    if tracking_id in data and data[tracking_id]["status"] not in ["replied", "bounced"]:
        if "clicked_at" not in data[tracking_id] or data[tracking_id]["clicked_at"] is None:
            data[tracking_id]["clicked_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
            data[tracking_id]["status"] = "opened"  # Il click è considerato un'apertura significativa
            if data[tracking_id]["opened_at"] is None:  # Assicurati che opened_at sia impostato se non lo è già
                data[tracking_id]["opened_at"] = data[tracking_id]["clicked_at"]
            _save_tracking_data(data)
            print(
                f"[{time.strftime('%H:%M:%S')}] Email with ID '{tracking_id}' clicked. Status set to 'opened'. Redirecting to {original_url}")
            return True
        else:
            print(
                f"[{time.strftime('%H:%M:%S')}] Email with ID '{tracking_id}' already clicked. Ignoring duplicate.")
    elif tracking_id in data:
        print(
            f"[{time.strftime('%H:%M:%S')}] Email with ID '{tracking_id}' already replied or bounced. Ignoring click.")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] Tracking ID '{tracking_id}' not found for click. Possible invalid link.")
    return False


@app.route('/register_email', methods=['POST'])
def register_email():
    if not request.is_json:
        abort(400, description="Request must be JSON")

    email_data = request.get_json()

    required_fields = ["tracking_id", "recipient_email", "company_name", "sent_at"]
    if not all(field in email_data for field in required_fields):
        abort(400, description=f"Missing required fields: {required_fields}")

    tracking_id = email_data["tracking_id"]

    data = _load_tracking_data()
    if tracking_id in data:
        print(f"[{time.strftime('%H:%M:%S')}] Tracking ID '{tracking_id}' already registered. No action taken.")
    else:
        data[tracking_id] = {
            "email_id": email_data.get("email_id", tracking_id),  # Potrebbe essere il Message-ID originale di Gmail
            "recipient_email": email_data["recipient_email"],
            "company_name": email_data["company_name"],
            "opened_at": None,
            "clicked_at": None,
            "replied_at": None,  # Nuovo campo per la risposta
            "bounced_at": None,  # Nuovo campo per il rimbalzo
            "bounce_type": None,  # Nuovo campo per il tipo di rimbalzo
            "bounce_reason": None,  # Nuovo campo per la ragione del rimbalzo
            "status": "sent",
            "sent_at": email_data["sent_at"]
        }
        _save_tracking_data(data)
        print(f"[{time.strftime('%H:%M:%S')}] Registered new email for tracking: {tracking_id}")

    return jsonify({"message": "Email registered for tracking", "tracking_id": tracking_id}), 200


@app.route('/pixel/<tracking_id>.gif')
def track_pixel(tracking_id):
    print(f"[{time.strftime('%H:%M:%S')}] Received request for tracking ID: {tracking_id}")
    record_email_open(tracking_id)

    response = app.make_response(
        b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x4c\x01\x00\x3b')
    response.headers['Content-Type'] = 'image/gif'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/click/<tracking_id>/<path:target_url_encoded>')
def track_click(tracking_id, target_url_encoded):
    original_url = unquote_plus(target_url_encoded)
    print(f"[{time.strftime('%H:%M:%S')}] Received click for tracking ID: {tracking_id} to {original_url}")

    record_email_click(tracking_id, original_url)

    return redirect(original_url)


@app.route('/record_reply', methods=['POST'])
def record_reply_route():
    if not request.is_json:
        abort(400, description="Request must be JSON")

    data_in = request.get_json()
    tracking_id = data_in.get("tracking_id")
    reply_time = data_in.get("reply_time")

    if not tracking_id:
        abort(400, description="Missing tracking_id")

    data = _load_tracking_data()
    # Aggiorna solo se l'email non è già in uno stato più avanzato (bounced) o non è già replied.
    if tracking_id in data and data[tracking_id]["status"] not in ["bounced", "replied"]:
        data[tracking_id]["replied_at"] = reply_time if reply_time else time.strftime('%Y-%m-%d %H:%M:%S')
        data[tracking_id]["status"] = "replied"
        _save_tracking_data(data)
        print(f"[{time.strftime('%H:%M:%S')}] Email with ID '{tracking_id}' replied.")
        return jsonify({"message": "Reply recorded", "tracking_id": tracking_id}), 200
    elif tracking_id in data:
        print(
            f"[{time.strftime('%H:%M:%S')}] Email with ID '{tracking_id}' already replied or bounced. Ignoring duplicate.")
        return jsonify({"message": "Reply already recorded or bounced", "tracking_id": tracking_id}), 200
    else:
        print(f"[{time.strftime('%H:%M:%S')}] Tracking ID '{tracking_id}' not found for reply.")
        return jsonify({"message": "Tracking ID not found", "tracking_id": tracking_id}), 404


@app.route('/record_bounce', methods=['POST'])
def record_bounce_route():
    if not request.is_json:
        abort(400, description="Request must be JSON")

    data_in = request.get_json()
    tracking_id = data_in.get("tracking_id")
    bounce_type = data_in.get("bounce_type", "unknown")
    bounce_reason = data_in.get("bounce_reason", "N/A")
    bounce_time = data_in.get("bounce_time")

    if not tracking_id:
        abort(400, description="Missing tracking_id")

    data = _load_tracking_data()
    # Aggiorna solo se l'email non è già in stato di rimbalzo
    if tracking_id in data and data[tracking_id]["status"] != "bounced":
        data[tracking_id]["bounced_at"] = bounce_time if bounce_time else time.strftime('%Y-%m-%d %H:%M:%S')
        data[tracking_id]["bounce_type"] = bounce_type
        data[tracking_id]["bounce_reason"] = bounce_reason
        data[tracking_id]["status"] = "bounced"
        _save_tracking_data(data)
        print(f"[{time.strftime('%H:%M:%S')}] Email with ID '{tracking_id}' bounced ({bounce_type}: {bounce_reason}).")
        return jsonify({"message": "Bounce recorded", "tracking_id": tracking_id}), 200
    elif tracking_id in data:
        print(f"[{time.strftime('%H:%M:%S')}] Email with ID '{tracking_id}' already bounced. Ignoring duplicate.")
        return jsonify({"message": "Bounce already recorded", "tracking_id": tracking_id}), 200
    else:
        print(f"[{time.strftime('%H:%M:%S')}] Tracking ID '{tracking_id}' not found for bounce.")
        return jsonify({"message": "Tracking ID not found", "tracking_id": tracking_id}), 404


@app.route('/status')
def status():
    data = _load_tracking_data()
    return jsonify(data), 200


@app.route('/')
def home():
    return "Server di tracciamento email Flask attivo!"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)