SensorStream API

SensorStream is a full-stack telemetry demo that simulates a device streaming sensor readings into a backend API and visualizes those readings in real time on a web dashboard. The project is designed to demonstrate end-to-end system design, including API development, data persistence, frontend state management, and documentation-driven engineering.

Overview

SensorStream models a simplified real-world telemetry pipeline:
A simulated device sends sensor readings to a backend API
The backend validates, authenticates, and persists telemetry data
A frontend dashboard polls for updates and renders live charts, latest values, and history
Users can start and stop the demo, switch sensors, and inspect recent readings
The project emphasizes clarity, correctness, and debuggability over raw complexity.

Tech Stack

Frontend:

Next.js (App Router)
React
Tailwind CSS
Client-side polling and state management
Chart rendering for live telemetry

Backend:

Flask (Python REST API)
SQLAlchemy
SQLite (time-series–style persistence)
Header-based device authentication

System Architecture

At a high level:

The frontend initializes by checking API health and fetching demo credentials
A simulated device posts readings to /api/ingest
The frontend polls /api/readings once per second while the demo is active

Data is validated, stored, filtered, and returned with structured metadata
Detailed architecture and data-flow diagrams are included on the documentation page of the live site.

API Summary
POST /api/ingest

Accepts telemetry readings from a device.
Authenticated via X-Device-Id and X-API-Key
Validates sensor type, timestamps, and numeric values
Persists valid readings
Returns per-item error details for invalid entries

GET /api/readings

Returns recent telemetry readings for a device.
Supports:
Sensor filtering
Time-window filtering
Ascending or descending order
Result limits (default max: 200)
Returns structured metadata alongside readings to support frontend state updates.

GET /health
Simple health check used by the frontend on initial load.

Local Setup Prerequisites:

Python 3.10+
Node.js 18+
npm

Roadmap

Planned enhancements include:

Improve demo mode to avoid repeated dataset replication
Optional WebSocket support to replace polling
Expanded test coverage across frontend and backend
Rate limiting and improved authentication UX
Export/download functionality for telemetry data
Production database migration (PostgreSQL)

Purpose of This Project

SensorStream is part of a broader portfolio demonstrating:

API design and backend validation
Frontend state management for live data
Clear documentation and system reasoning
Debug-first engineering practices
End-to-end ownership of a full-stack system