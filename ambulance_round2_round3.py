from flask import Flask, request, jsonify
from threading import Thread
from queue import Queue

app = Flask(__name__)

# Demo in-memory storage. Use PostgreSQL/PostGIS for production.
ambulances = {
    501: {
        "ambulance_id": 501,
        "vehicle_number": "TN38AB1234",
        "driver_name": "Driver A",
        "latitude": 11.0200,
        "longitude": 76.9600,
        "status": "AVAILABLE"
    }
}
emergencies = {}
next_request_id = 1001

# Round 3 demo: background event queue
events = Queue()


def event_worker():
    while True:
        event = events.get()
        try:
            print("Processing event:", event)
        finally:
            events.task_done()


Thread(target=event_worker, daemon=True).start()


def publish_event(event_type, data):
    events.put({"event": event_type, "data": data})


# ---------------- ROUND 2 APIs ----------------

# 1. Request an ambulance
@app.route("/ambulances/request", methods=["POST"])
def request_ambulance():
    global next_request_id
    data = request.get_json(silent=True) or {}

    required = ["user_id", "latitude", "longitude", "emergency_type"]
    if any(key not in data for key in required):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        user_id = int(data["user_id"])
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid input"}), 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"error": "Invalid coordinates"}), 400

    ambulance = next(
        (item for item in ambulances.values()
         if item["status"] == "AVAILABLE"),
        None
    )
    if ambulance is None:
        return jsonify({"error": "No ambulance available"}), 409

    request_id = next_request_id
    next_request_id += 1
    ambulance["status"] = "ASSIGNED"

    emergencies[request_id] = {
        "request_id": request_id,
        "user_id": user_id,
        "ambulance_id": ambulance["ambulance_id"],
        "latitude": latitude,
        "longitude": longitude,
        "emergency_type": str(data["emergency_type"]),
        "status": "ASSIGNED"
    }

    publish_event("AmbulanceAssigned", emergencies[request_id])
    return jsonify({
        "request_id": request_id,
        "ambulance_id": ambulance["ambulance_id"],
        "status": "ASSIGNED",
        "message": "Ambulance assigned successfully"
    }), 201


# 2. Get ambulance details
@app.route("/ambulances/<int:ambulance_id>", methods=["GET"])
def get_ambulance(ambulance_id):
    ambulance = ambulances.get(ambulance_id)
    if ambulance is None:
        return jsonify({"error": "Ambulance not found"}), 404

    return jsonify({
        "ambulance_id": ambulance["ambulance_id"],
        "vehicle_number": ambulance["vehicle_number"],
        "driver_name": ambulance["driver_name"],
        "status": ambulance["status"]
    }), 200


# 3. Get ambulance location
@app.route("/ambulances/<int:ambulance_id>/location", methods=["GET"])
def get_location(ambulance_id):
    ambulance = ambulances.get(ambulance_id)
    if ambulance is None:
        return jsonify({"error": "Ambulance not found"}), 404

    return jsonify({
        "ambulance_id": ambulance_id,
        "latitude": ambulance["latitude"],
        "longitude": ambulance["longitude"]
    }), 200


# 4. Get emergency status
@app.route("/emergencies/<int:request_id>/status", methods=["GET"])
def get_status(request_id):
    emergency = emergencies.get(request_id)
    if emergency is None:
        return jsonify({"error": "Request not found"}), 404

    return jsonify({
        "request_id": request_id,
        "status": emergency["status"]
    }), 200


# 5. Get emergency request details
@app.route("/emergencies/<int:request_id>", methods=["GET"])
def get_emergency(request_id):
    emergency = emergencies.get(request_id)
    if emergency is None:
        return jsonify({"error": "Request not found"}), 404

    return jsonify(emergency), 200


# 6. Cancel emergency request
@app.route("/emergencies/<int:request_id>", methods=["DELETE"])
def cancel_emergency(request_id):
    emergency = emergencies.get(request_id)
    if emergency is None:
        return jsonify({"error": "Request not found"}), 404

    if emergency["status"] in ("COMPLETED", "CANCELLED"):
        return jsonify({"error": "Cancellation not permitted"}), 409

    emergency["status"] = "CANCELLED"
    ambulance = ambulances.get(emergency["ambulance_id"])
    if ambulance is not None:
        ambulance["status"] = "AVAILABLE"

    publish_event("EmergencyCancelled", {"request_id": request_id})
    return jsonify({
        "request_id": request_id,
        "status": "CANCELLED",
        "message": "Request cancelled successfully"
    }), 200


# ---------------- ROUND 3 API ----------------

# Update ambulance location and publish an asynchronous event
@app.route("/api/v1/ambulances/<int:ambulance_id>/location",
           methods=["PUT"])
def update_location(ambulance_id):
    ambulance = ambulances.get(ambulance_id)
    if ambulance is None:
        return jsonify({"error": "Ambulance not found"}), 404

    data = request.get_json(silent=True) or {}
    try:
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Invalid location"}), 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"error": "Invalid coordinates"}), 400

    ambulance["latitude"] = latitude
    ambulance["longitude"] = longitude

    publish_event("AmbulanceLocationUpdated", {
        "ambulance_id": ambulance_id,
        "latitude": latitude,
        "longitude": longitude
    })

    return jsonify({
        "message": "Location updated",
        "ambulance_id": ambulance_id,
        "latitude": latitude,
        "longitude": longitude
    }), 200


# Round 3-style API paths for creating and checking emergencies
@app.route("/api/v1/emergencies", methods=["POST"])
def create_emergency_v3():
    # Reuse the same validation and assignment logic as Round 2.
    # The demonstration uses a direct helper-style implementation here.
    global next_request_id
    data = request.get_json(silent=True) or {}

    if "user_id" not in data:
        return jsonify({"error": "Missing user_id"}), 400

    try:
        user_id = int(data["user_id"])
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user_id"}), 400

    ambulance = next(
        (item for item in ambulances.values()
         if item["status"] == "AVAILABLE"),
        None
    )
    if ambulance is None:
        return jsonify({"error": "No ambulance available"}), 409

    request_id = next_request_id
    next_request_id += 1
    ambulance["status"] = "ASSIGNED"

    emergencies[request_id] = {
        "request_id": request_id,
        "user_id": user_id,
        "ambulance_id": ambulance["ambulance_id"],
        "status": "ASSIGNED"
    }
    publish_event("AmbulanceAssigned", emergencies[request_id])
    return jsonify(emergencies[request_id]), 201


@app.route("/api/v1/emergencies/<int:request_id>", methods=["GET"])
def get_emergency_v3(request_id):
    emergency = emergencies.get(request_id)
    if emergency is None:
        return jsonify({"error": "Emergency not found"}), 404
    return jsonify(emergency), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
