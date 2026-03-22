HypoSensePredict: ML Integration 🧠

This repository contains the source code for Phase 2 of HypoSensePredict, a smart hydroponic system for cultivating radish microgreens. This phase focuses on the integration of machine learning models to provide predictive analytics and automated control.

This project was developed locally to train, test, and integrate the machine learning models with the Flask backend. Unlike Phase 1, this version was not deployed.

📜 Project Overview

Building upon the data collection and monitoring framework established in Phase 1, this phase introduces advanced predictive capabilities. By processing the real-time sensor data, the machine learning models can predict final yield by estimating the final crop yield in grams based on environmental data, forecast harvest time by predicting the optimal number of days remaining until harvest, and automate pump control by intelligently deciding when to turn the water pump on or off, moving beyond simple thresholds to a data-driven approach.

The core of this phase is a Random Forest algorithm, which was trained on data from three full growth cycles of radish microgreens. This approach allows the system to learn from past conditions to make accurate and adaptive decisions.

👥 Team Members

This project was a collaborative effort by a team of dedicated students:

Tejasgiri Gosavi (Project Lead, Backend & ESP32 Developer)
Chaitanya Dusane (Frontend Developer & Hardware/IoT & Backend)
Valmik Patil (Research, Plant Management & Hardware/IoT)

🛠️ Technology Stack

This phase expands the technology stack to include machine learning libraries:

Backend: Flask, Python
Machine Learning: Scikit-learn, Pandas
Frontend: HTML, CSS, JavaScript
Database: MongoDB
IoT: Utilized data from hardware in Phase 1

🚀 Project Phases

The project was developed in two phases:

Phase 1: IoT & Dashboard
Repository: https://github.com/Tejasgiri29/HSP
Focus: This phase involved setting up the IoT hardware, collecting data from the sensors, and displaying it on a real-time dashboard. The application was previously deployed on Render for live monitoring.

Phase 2: Machine Learning Integration
Repository: https://github.com/Tejasgiri29/HSP-ML-integration-
Focus: This phase was dedicated to implementing and integrating Random Forest models to predict crop yield, estimate harvest time, and automate pump control based on the collected data.

🧠 Machine Learning Models

The models directory contains the serialized machine learning models trained for specific tasks:

rf_yield_model.pkl: Predicts the final crop yield.
rf_harvest_model.pkl: Forecasts the remaining days until harvest.
rf_pump_model.pkl: Determines the pump's on/off state.
rf_anomaly_model.pkl: A rule-based tool for manual anomaly logging.
label_encoder.pkl: Used for encoding categorical features.

These models achieved high accuracy during testing, with the pump control model reaching 98% accuracy and the yield prediction model achieving an R-squared value of 0.95.

🔮 Future Work

Future enhancements for this project include deploying the integrated ML application to a cloud platform, adding pH and EC sensors to automate nutrient dispensing controlled by a new ML model, developing a mobile app for remote monitoring and to display ML predictions, experimenting with deep learning or reinforcement learning models for more complex decision-making, and incorporating a camera to visually monitor plant health and detect diseases.

📄 License

Distributed under the MIT License. See LICENSE for more information.
