# Smart Environment Monitoring System

This project is a real-time environmental monitoring system developed using Flask, SQLite, and the Sense HAT Emulator. It simulates an IoT-based monitoring pipeline, including data collection, storage, analysis, and visualisation.

## Features

- Real-time sensor data collection (temperature, humidity, pressure)
- Data storage using SQLite
- Interactive dashboard with charts (Chart.js)
- Warning detection based on threshold values
- Basic data analysis (spike detection, trend analysis, prediction)
- LED matrix display simulation using Sense HAT Emulator

## Technologies Used

- Python (Flask)
- SQLite
- HTML / CSS / JavaScript
- Chart.js
- Sense HAT Emulator

## How to Run

1. Install dependencies:pip install -r requirements.txt

2. Run the application:
python app.py

3. Open in browser:http://localhost:5000

## Notes

- The system uses a background thread for continuous data collection.
- Make sure the Sense HAT Emulator is running to generate sensor data.
- The database file (sensor.db) is located in the `instance/` directory.




