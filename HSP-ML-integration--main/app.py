import os
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import joblib
import pandas as pd
import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from pymongo import MongoClient

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24) # Secret key for Flask sessions

# --- MongoDB Configuration ---
MONGO_DB_URI = os.getenv("MONGO_DB_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "hydroponics_db")

try:
    client = MongoClient(MONGO_DB_URI)
    db = client[MONGO_DB_NAME]
    users_collection = db["users"]
    sensor_data_collection = db["sensor_data"]
    pump_log_collection = db["pump_log"]
    print("MongoDB Connected Successfully!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    # In a production environment, you might want to log this error and gracefully degrade.
    # For now, we'll let it proceed but note the issue.

# --- MQTT Configuration ---
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 8883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID")

SENSOR_TOPIC = "home/sensors"
PUMP_CONTROL_TOPIC = "home/pump/control"
PUMP_LOG_TOPIC = "home/pump/log"

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=MQTT_CLIENT_ID)

# Global variable to track system online/offline status and last data timestamp
system_status = {"online": False, "last_data_timestamp": None}
# Global variable to store the latest pump state
latest_pump_state = {"state": 0} # 0 for OFF, 1 for ON

# IST timezone object for consistent time handling
ist_timezone = timezone(timedelta(hours=5, minutes=30))

# --- Machine Learning Model Loading ---
try:
    rf_yield = joblib.load("models/rf_yield_model.pkl")
    rf_pump = joblib.load("models/rf_pump_model.pkl")
    rf_anomaly = joblib.load("models/rf_anomaly_model.pkl")
    rf_harvest = joblib.load("models/rf_harvest_model.pkl")
    label_encoder = joblib.load("models/label_encoder.pkl")
    print("ML Models Loaded Successfully!")
except Exception as e:
    print(f"Error loading ML models: {e}")
    print("Creating dummy models for development. Please ensure your actual models are in the 'models/' directory and are correctly named.")
    
    # Dummy models for testing if actual models are not present or fail to load
    class DummyModel:
        def predict(self, df):
            if "pump_reason_encoded" in df.columns: # Anomaly input shape
                return [0] # Default to no anomaly
            elif "water_level_raw" in df.columns and "hour_of_day" in df.columns: # Pump input shape (subset)
                return [0] # Default to pump off
            elif "cycle_number" in df.columns: # Yield/Harvest input shape (subset)
                return [100.0] # Default to yield
            return [0.0] # General numeric default for other cases


    class DummyLabelEncoder:
        def transform(self, data):
            mapping = {
                "Pump turned ON": 0,
                "Pump turned OFF - Max water level reached": 1,
                "Pump turned OFF - Safety timeout": 2,
                "N/A": 3
            }
            if isinstance(data, str):
                return [mapping.get(data, mapping["N/A"])]
            return [mapping.get(reason, mapping["N/A"]) for reason in data]

        def fit(self, data):
            # Crucial: ensure these classes match the expected inputs
            self.classes_ = ["Pump turned ON", "Pump turned OFF - Max water level reached", "Pump turned OFF - Safety timeout", "N/A"]
            self.mapping_ = {label: i for i, label in enumerate(self.classes_)}

    rf_yield = DummyModel()
    rf_pump = DummyModel()
    rf_anomaly = DummyModel()
    rf_harvest = DummyModel()
    label_encoder = DummyLabelEncoder()
    # Explicitly fit the dummy label encoder during initialization
    label_encoder.fit(["Pump turned ON", "Pump turned OFF - Max water level reached", "Pump turned OFF - Safety timeout", "N/A"])
    print("Dummy ML models initialized.")


# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc):
    """Callback for when the MQTT client connects to the broker."""
    if rc == 0:
        print("Connected to MQTT Broker!")
        client.subscribe(SENSOR_TOPIC)
        client.subscribe(PUMP_LOG_TOPIC)
        print(f"Subscribed to topics: {SENSOR_TOPIC}, {PUMP_LOG_TOPIC}")
    else:
        print(f"Failed to connect to MQTT, return code {rc}\n")

def on_message(client, userdata, msg):
    """Callback for when a message is received from the MQTT broker."""
    try:
        payload = msg.payload.decode()
        topic = msg.topic
        data = json.loads(payload)
        print(f"MQTT Message Received - Topic: {topic}, Data: {data}")

        current_time_ist = datetime.now(ist_timezone)

        if topic == SENSOR_TOPIC:
            # Store sensor data in MongoDB
            data["received_at"] = current_time_ist # Add server-side timestamp for accurate sorting/filtering
            sensor_data_collection.insert_one(data)
            print("Sensor data stored in MongoDB.")
            # Update system status
            system_status["online"] = True
            system_status["last_data_timestamp"] = current_time_ist

        elif topic == PUMP_LOG_TOPIC:
            # Store pump log in MongoDB
            data["received_at"] = current_time_ist # Add server-side timestamp
            pump_log_collection.insert_one(data)
            print("Pump log stored in MongoDB.")
            # Update latest pump state from the log
            try:
                # Ensure pump_state is an integer (0 or 1)
                latest_pump_state["state"] = int(data.get("pump_state", 0)) 
            except (ValueError, TypeError):
                print(f"Warning: Could not interpret pump_state '{data.get('pump_state')}' from pump log.")
                latest_pump_state["state"] = 0 # Default to OFF if invalid


    except json.JSONDecodeError as e:
        print(f"Error decoding JSON payload: {e} from topic {msg.topic}, payload: {msg.payload}")
    except Exception as e:
        print(f"An error occurred in on_message: {e}")

# Assign MQTT callbacks
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# Set MQTT username and password
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# --- MQTT Connection and Loop in a separate thread ---
def mqtt_thread_function():
    """Function to run the MQTT client loop in a separate thread."""
    try:
        # Enable TLS for port 8883
        mqtt_client.tls_set()
        mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
        mqtt_client.loop_forever() # This blocks, so it must be in a thread
    except Exception as e:
        print(f"MQTT thread encountered an error: {e}")

# Start the MQTT client in a new thread
mqtt_thread = threading.Thread(target=mqtt_thread_function)
mqtt_thread.daemon = True # Allow the main program to exit even if the thread is running
mqtt_thread.start()

# --- System Status Checker Thread ---
def system_status_checker():
    """Periodically checks if sensor data has been received recently."""
    while True:
        if system_status["last_data_timestamp"]:
            time_since_last_data = datetime.now(ist_timezone) - system_status["last_data_timestamp"]
            # If no data for more than 16 minutes, mark as offline
            if time_since_last_data.total_seconds() > (16 * 60):
                system_status["online"] = False
            else:
                system_status["online"] = True
        else:
            # If no data has ever been received, assume offline
            system_status["online"] = False
        time.sleep(60) # Check every minute

status_checker_thread = threading.Thread(target=system_status_checker)
status_checker_thread.daemon = True
status_checker_thread.start()

# --- Utility Function to Fetch Dhule Weather Data (with humidity) ---
def get_dhule_weather():
    """
    Fetches live temperature and humidity for Dhule city from Open-Meteo hourly forecast.
    """
    DHULE_LAT = 20.9042
    DHULE_LON = 74.7749
    # Request hourly temperature and relative humidity
    url = f"https://api.open-meteo.com/v1/forecast?latitude={DHULE_LAT}&longitude={DHULE_LON}&hourly=temperature_2m,relative_humidity_2m&timezone=Asia%2FKolkata&forecast_days=1"
    try:
        response = requests.get(url)
        response.raise_for_status() # Raise an exception for HTTP errors
        data = response.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temperatures = hourly.get("temperature_2m", [])
        humidities = hourly.get("relative_humidity_2m", [])

        current_time_utc = datetime.now(timezone.utc) # Compare with UTC times from API

        if not times or not temperatures or not humidities:
            print("No hourly weather data found in Open-Meteo response.")
            return {"temperature_C": None, "humidity_perc": None}

        # Find the index of the closest time point in the past or current hour
        closest_index = -1
        min_time_diff = timedelta(days=999) # Arbitrarily large

        for i, t_str in enumerate(times):
            # Parse API time string, assuming it's in ISO 8601 format and UTC
            api_time = datetime.fromisoformat(t_str).replace(tzinfo=timezone.utc)
            time_diff = abs(current_time_utc - api_time) # Use absolute difference to find closest
            if time_diff < min_time_diff:
                min_time_diff = time_diff
                closest_index = i

        if closest_index != -1:
            temp_c = temperatures[closest_index]
            humidity_perc = humidities[closest_index]
            print(f"Fetched Dhule Weather: Temp={temp_c}°C, Humidity={humidity_perc}% (from hourly data)")
            return {"temperature_C": temp_c, "humidity_perc": humidity_perc}
        else:
            print("Could not find current hour's weather data in Open-Meteo response.")
            return {"temperature_C": None, "humidity_perc": None}

    except requests.exceptions.RequestException as e:
        print(f"Error fetching Dhule weather: {e}")
        return {"temperature_C": None, "humidity_perc": None}
    except Exception as e:
        print(f"An unexpected error occurred while fetching weather: {e}")
        return {"temperature_C": None, "humidity_perc": None}


# --- Flask Routes ---

@app.route("/")
def landing_page():
    """Renders the landing page."""
    return render_template("landingpage.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Handles user login."""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"] # In a real app, hash and compare passwords
        user = users_collection.find_one({"username": username, "password": password}) # Simple check for demo

        if user:
            session["username"] = username
            return jsonify({"success": True, "message": "Login successful!"})
        else:
            return jsonify({"success": False, "message": "Invalid credentials."})
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Handles new user registration."""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"] # In a real app, hash password before storing

        if users_collection.find_one({"username": username}):
            return jsonify({"success": False, "message": "Username already exists."})
        else:
            users_collection.insert_one({"username": username, "password": password})
            return jsonify({"success": True, "message": "Registration successful! Please login."})
    return render_template("register.html")

@app.route("/logout")
def logout():
    """Logs out the current user."""
    session.pop("username", None)
    return redirect(url_for("landing_page"))

@app.route("/dashboard")
def dashboard():
    """Renders the dashboard page, requiring login."""
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", username=session["username"])


# --- API Endpoints for Dashboard Data ---

@app.route("/api/latest_sensor_data")
def get_latest_sensor_data():
    """
    Returns the latest sensor reading from MongoDB,
    current Dhule weather, and the latest pump state.
    """
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Fetch the latest sensor data, sorted by timestamp descending
    latest_sensor_data = sensor_data_collection.find_one(
        sort=[("received_at", -1)]
    )

    # Get current Dhule weather
    dhule_weather = get_dhule_weather()
    
    response_data = {
        "timestamp": latest_sensor_data["timestamp"] if latest_sensor_data else "N/A",
        "water_level": latest_sensor_data["water_level"] if latest_sensor_data else "N/A",
        "ldr_value": latest_sensor_data["ldr_value"] if latest_sensor_data else "N/A",
        "dhule_temperature_C": dhule_weather.get("temperature_C", "N/A"),
        "dhule_humidity_perc": dhule_weather.get("humidity_perc", "N/A"),
        "system_online": system_status["online"],
        "current_pump_state": latest_pump_state["state"] # 0 or 1
    }
    return jsonify(response_data)

@app.route("/api/sensor_data_history")
def get_sensor_data_history():
    """Returns historical sensor data for charts."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    period = request.args.get("period", "24h") # '12h', '24h', '7d'
    
    end_time = datetime.now(ist_timezone)
    if period == "12h":
        start_time = end_time - timedelta(hours=12)
    elif period == "7d":
        start_time = end_time - timedelta(days=7)
    else: # Default to 24 hours
        start_time = end_time - timedelta(hours=24)

    # Fetch data within the time range, ordered by 'received_at'
    history_data = list(sensor_data_collection.find(
        {"received_at": {"$gte": start_time, "$lte": end_time}},
        {"_id": 0, "water_level": 1, "ldr_value": 1, "received_at": 1}
    ).sort("received_at", 1)) # Sort ascending by MongoDB's timestamp

    # Format timestamps for JavaScript (ISO string for Chart.js time scale)
    for entry in history_data:
        entry['timestamp_js'] = entry['received_at'].isoformat()


    return jsonify(history_data)

@app.route("/api/pump_logs")
def get_pump_logs():
    """Returns pump log history from MongoDB."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    # Fetch last 50 pump logs, sorted by 'received_at' descending
    logs = list(pump_log_collection.find(
        {},
        {"_id": 0, "timestamp": 1, "pump_state": 1, "reason": 1, "duration": 1, "received_at": 1}
    ).sort("received_at", -1).limit(50)) # Sort by MongoDB's timestamp for consistency
    return jsonify(logs)

# --- ML Prediction Endpoints ---

@app.route("/api/predict_yield", methods=["POST"])
def predict_yield_route():
    """Endpoint for yield prediction."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.json
        
        # Automatically get latest sensor data and weather
        latest_sensor = sensor_data_collection.find_one(sort=[("received_at", -1)])
        dhule_weather = get_dhule_weather()

        # Construct payload using model's expected labels (from Colab.pdf X_yield features)
        # Ensure correct feature names as seen during model training
        payload = {
            "cycle_number": data.get("cycle_number"),
            "temperature_C": dhule_weather.get("temperature_C"),
            "humidity_perc": dhule_weather.get("humidity_perc"),
            "water_level_raw": latest_sensor.get("water_level") if latest_sensor else None,
            "ldr_raw": latest_sensor.get("ldr_value") if latest_sensor else None,
            "day_of_cycle": data.get("day_of_cycle_mean"), # Using 'day_of_cycle' as per X_yield features
            "hour_of_day": data.get("hour_of_day_mean")     # Using 'hour_of_day' as per X_yield features
        }

        # Define the exact order of features as expected by the model
        yield_features_order = ["temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "cycle_number", "day_of_cycle", "hour_of_day"]
        
        # Create a list of values in the correct order
        input_values = [payload.get(feature) for feature in yield_features_order]

        # Create DataFrame with explicit columns to match training
        input_df = pd.DataFrame([input_values], columns=yield_features_order)
        
        # Fill missing values with a sensible default (e.g., 0 for raw readings, 1 for cycle/day, 0 for hour)
        # Ensure dtypes match what the model expects (e.g., int for cycle_number, float for temp/humidity)
        input_df["cycle_number"] = input_df["cycle_number"].fillna(1).astype(int)
        input_df["temperature_C"] = input_df["temperature_C"].fillna(25.0).astype(float) # Default temp
        input_df["humidity_perc"] = input_df["humidity_perc"].fillna(60.0).astype(float) # Default humidity
        input_df["water_level_raw"] = input_df["water_level_raw"].fillna(0).astype(int)
        input_df["ldr_raw"] = input_df["ldr_raw"].fillna(0).astype(int)
        input_df["day_of_cycle"] = input_df["day_of_cycle"].fillna(1).astype(int)
        input_df["hour_of_day"] = input_df["hour_of_day"].fillna(0).astype(int)
        
        prediction = rf_yield.predict(input_df)[0]
        return jsonify({"yield_grams": float(prediction)})
    except Exception as e:
        print(f"Error during yield prediction: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/predict_pump", methods=["POST"])
def predict_pump_route():
    """Endpoint for pump action prediction."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        # Automatically get latest sensor data and weather
        latest_sensor = sensor_data_collection.find_one(sort=[("received_at", -1)])
        dhule_weather = get_dhule_weather()

        # Get current hour for hour_of_day
        current_hour_ist = datetime.now(ist_timezone).hour

        # Construct payload using model's expected labels (from Colab.pdf X_pump features)
        pump_features_order = ["temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "hour_of_day"]
        payload = {
            "temperature_C": dhule_weather.get("temperature_C"),
            "humidity_perc": dhule_weather.get("humidity_perc"),
            "water_level_raw": latest_sensor.get("water_level") if latest_sensor else None,
            "ldr_raw": latest_sensor.get("ldr_value") if latest_sensor else None,
            "hour_of_day": current_hour_ist
        }
        
        input_values = [payload.get(feature) for feature in pump_features_order]
        input_df = pd.DataFrame([input_values], columns=pump_features_order)
        
        # Fill missing values with sensible defaults and ensure types
        input_df["temperature_C"] = input_df["temperature_C"].fillna(25.0).astype(float)
        input_df["humidity_perc"] = input_df["humidity_perc"].fillna(60.0).astype(float)
        input_df["water_level_raw"] = input_df["water_level_raw"].fillna(0).astype(int)
        input_df["ldr_raw"] = input_df["ldr_raw"].fillna(0).astype(int)
        input_df["hour_of_day"] = input_df["hour_of_day"].fillna(0).astype(int)

        prediction = rf_pump.predict(input_df)[0]

        # If pump prediction is 'ON' (1), send MQTT message to ESP32
        if int(prediction) == 1:
            print("ML model predicted PUMP ON. Sending MQTT command to ESP32...")
            try:
                mqtt_client.publish(PUMP_CONTROL_TOPIC, "ON")
                print("MQTT command 'ON' sent successfully.")
            except Exception as mqtt_err:
                print(f"Error publishing MQTT command: {mqtt_err}")
            
        return jsonify({"pump_action": int(prediction)})
    except Exception as e:
        print(f"Error during pump prediction: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/predict_anomaly", methods=["POST"])
def predict_anomaly_route():
    """Endpoint for anomaly detection prediction."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.json # User provides pump_state, pump_reason
        
        # Automatically get latest sensor data and weather
        latest_sensor = sensor_data_collection.find_one(sort=[("received_at", -1)])
        dhule_weather = get_dhule_weather()
        
        current_hour_ist = datetime.now(ist_timezone).hour

        # Prepare pump_reason for encoding
        pump_reason_str = str(data.get("pump_reason", "N/A"))

        # Transform pump_reason string to encoded integer
        try:
            # Ensure the label_encoder is robust to single string inputs by wrapping in a list
            pump_reason_encoded_val = label_encoder.transform([pump_reason_str])[0]
        except ValueError as ve:
            print(f"LabelEncoder error for '{pump_reason_str}': {ve}. Using default 'N/A' encoding.")
            pump_reason_encoded_val = label_encoder.transform(["N/A"])[0] # Fallback to N/A's encoding


        # Construct payload using model's expected labels (from Colab.pdf X_anomaly features)
        anomaly_features_order = ["temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "pump_state", "pump_reason_encoded"]
        payload = {
            "temperature_C": dhule_weather.get("temperature_C"),
            "humidity_perc": dhule_weather.get("humidity_perc"),
            "water_level_raw": latest_sensor.get("water_level") if latest_sensor else None,
            "ldr_raw": latest_sensor.get("ldr_value") if latest_sensor else None,
            # "hour_of_day": current_hour_ist, # Removed as per X_anomaly definition in Colab PDF
            "pump_state": data.get("pump_state"), # User provided
            "pump_reason_encoded": pump_reason_encoded_val # Now encoded and correctly named
        }
        
        input_values = [payload.get(feature) for feature in anomaly_features_order]
        input_df = pd.DataFrame([input_values], columns=anomaly_features_order)
        
        # Fill missing values with sensible defaults and ensure types
        input_df["temperature_C"] = input_df["temperature_C"].fillna(25.0).astype(float)
        input_df["humidity_perc"] = input_df["humidity_perc"].fillna(60.0).astype(float)
        input_df["water_level_raw"] = input_df["water_level_raw"].fillna(0).astype(int)
        input_df["ldr_raw"] = input_df["ldr_raw"].fillna(0).astype(int)
        input_df["pump_state"] = input_df["pump_state"].fillna(0).astype(int)
        input_df["pump_reason_encoded"] = input_df["pump_reason_encoded"].fillna(label_encoder.transform(["N/A"])[0]).astype(int)

        prediction = rf_anomaly.predict(input_df)[0]
        return jsonify({"anomaly_flag": int(prediction)})
    except Exception as e:
        print(f"Error during anomaly prediction: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/predict_harvest", methods=["POST"])
def predict_harvest_route():
    """Endpoint for harvest time prediction."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.json
        
        # Automatically get latest sensor data and weather
        latest_sensor = sensor_data_collection.find_one(sort=[("received_at", -1)])
        dhule_weather = get_dhule_weather()

        # Construct payload using model's expected labels (from Colab.pdf X_harvest features)
        # X_harvest features: "temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "cycle_number", "day_of_cycle"
        harvest_features_order = ["temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "cycle_number", "day_of_cycle"]
        payload = {
            "cycle_number": data.get("cycle_number"),
            "temperature_C": dhule_weather.get("temperature_C"),
            "humidity_perc": dhule_weather.get("humidity_perc"),
            "water_level_raw": latest_sensor.get("water_level") if latest_sensor else None,
            "ldr_raw": latest_sensor.get("ldr_value") if latest_sensor else None,
            "day_of_cycle": data.get("day_of_cycle_mean"),
            # "hour_of_day": data.get("hour_of_day_mean") # Removed as per X_harvest definition in Colab PDF
        }
        
        input_values = [payload.get(feature) for feature in harvest_features_order]
        input_df = pd.DataFrame([input_values], columns=harvest_features_order)

        # Fill missing values with sensible defaults and ensure types
        input_df["cycle_number"] = input_df["cycle_number"].fillna(1).astype(int)
        input_df["temperature_C"] = input_df["temperature_C"].fillna(25.0).astype(float)
        input_df["humidity_perc"] = input_df["humidity_perc"].fillna(60.0).astype(float)
        input_df["water_level_raw"] = input_df["water_level_raw"].fillna(0).astype(int)
        input_df["ldr_raw"] = input_df["ldr_raw"].fillna(0).astype(int)
        input_df["day_of_cycle"] = input_df["day_of_cycle"].fillna(1).astype(int)
        # input_df["hour_of_day"] = input_df["hour_of_day"].fillna(0).astype(int) # Removed


        prediction = rf_harvest.predict(input_df)[0]
        return jsonify({"harvest_time_hours": float(prediction)})
    except Exception as e:
        print(f"Error during harvest prediction: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Ensure models directory exists
    os.makedirs("models", exist_ok=True)
    
    # Check and create dummy models if they don't exist
    # It is crucial that these dummy models are fitted with the EXACT same feature names and order
    # as your real models were trained with, as defined in your Colab PDF.
    
    # Initialize and fit dummy LabelEncoder first, as it's used by anomaly and others
    if not os.path.exists("models/label_encoder.pkl"):
        print("Creating dummy label_encoder.pkl for initial setup.")
        from sklearn.preprocessing import LabelEncoder
        dummy_label_encoder = LabelEncoder()
        # Fit on all possible reasons, including "N/A"
        dummy_label_encoder.fit(["Pump turned ON", "Pump turned OFF - Max water level reached", "Pump turned OFF - Safety timeout", "N/A"])
        joblib.dump(dummy_label_encoder, "models/label_encoder.pkl")
        print("Dummy label_encoder.pkl created.")
    else:
        # Load existing label encoder to ensure its mapping is consistent for dummy models
        label_encoder = joblib.load("models/label_encoder.pkl")


    # Dummy Yield Model
    if not os.path.exists("models/rf_yield_model.pkl"):
        print("Creating dummy rf_yield_model.pkl for initial setup.")
        from sklearn.ensemble import RandomForestRegressor
        dummy_yield_model = RandomForestRegressor(n_estimators=10, random_state=42)
        # Columns from Colab.pdf X_yield: "temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "cycle_number", "day_of_cycle", "hour_of_day"
        # Ensure data types match expected by model (e.g., float for temp/humidity, int for others)
        dummy_yield_model.fit(
            pd.DataFrame([[25.0, 60.0, 500, 300, 1, 10, 12]], # Correct order and example values
                         columns=["temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "cycle_number", "day_of_cycle", "hour_of_day"]),
            [100.0]
        )
        joblib.dump(dummy_yield_model, "models/rf_yield_model.pkl")
        print("Dummy rf_yield_model.pkl created.")


    # Dummy Pump Model
    if not os.path.exists("models/rf_pump_model.pkl"):
        print("Creating dummy rf_pump_model.pkl for initial setup.")
        from sklearn.ensemble import RandomForestRegressor
        dummy_pump_model = RandomForestRegressor(n_estimators=10, random_state=42)
        # Columns from Colab.pdf X_pump: "temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "hour_of_day"
        dummy_pump_model.fit(
            pd.DataFrame([[25.0, 60.0, 500, 300, 12]],
                         columns=["temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "hour_of_day"]),
            [0]
        )
        joblib.dump(dummy_pump_model, "models/rf_pump_model.pkl")
        print("Dummy rf_pump_model.pkl created.")


    # Dummy Anomaly Model
    if not os.path.exists("models/rf_anomaly_model.pkl"):
        print("Creating dummy rf_anomaly_model.pkl for initial setup.")
        from sklearn.ensemble import RandomForestClassifier
        dummy_anomaly_model = RandomForestClassifier(n_estimators=10, random_state=42, class_weight="balanced")
        # Columns from Colab.pdf X_anomaly: "temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "pump_state", "pump_reason_encoded"
        # Ensure to use the *encoded* value for pump_reason
        anomaly_example_data = [25.0, 60.0, 500, 300, 0, label_encoder.transform(["N/A"])[0]]
        dummy_anomaly_model.fit(
            pd.DataFrame([anomaly_example_data],
                         columns=["temperature_C", "humidity_perc", "water_level_raw", "ldr_raw",
                                  "pump_state", "pump_reason_encoded"]),
            [0] # No anomaly
        )
        joblib.dump(dummy_anomaly_model, "models/rf_anomaly_model.pkl")
        print("Dummy rf_anomaly_model.pkl created.")

    # Dummy Harvest Model
    if not os.path.exists("models/rf_harvest_model.pkl"):
        print("Creating dummy rf_harvest_model.pkl for initial setup.")
        from sklearn.ensemble import RandomForestRegressor
        dummy_harvest_model = RandomForestRegressor(n_estimators=10, random_state=42)
        # Columns from Colab.pdf X_harvest: "temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "cycle_number", "day_of_cycle"
        dummy_harvest_model.fit(
            pd.DataFrame([[25.0, 60.0, 500, 300, 1, 10]], # Correct order and example values, removed hour_of_day
                         columns=["temperature_C", "humidity_perc", "water_level_raw", "ldr_raw", "cycle_number", "day_of_cycle"]),
            [720.0]
        )
        joblib.dump(dummy_harvest_model, "models/rf_harvest_model.pkl")
        print("Dummy rf_harvest_model.pkl created.")
        
    app.run(debug=True, host="0.0.0.0", port=5000)
