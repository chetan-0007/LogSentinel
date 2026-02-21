# LogSentinel

**Real-Time Distributed Log Monitoring, Alerting & Email Notification Platform**

LogSentinel is a distributed log ingestion and monitoring system built using FastAPI, PostgreSQL, and Kafka. It enables real-time log streaming, automated error rate monitoring, alert tracking, email notifications, and dashboard visualization — fully containerized with Docker.

---

## 📖 Overview

LogSentinel simulates a production-grade observability pipeline:

1. Applications send logs via REST API
2. Logs are streamed through Kafka
3. A consumer processes and stores logs in PostgreSQL
4. A monitoring engine evaluates error rates
5. Alerts are triggered automatically when thresholds are exceeded
6. Email notifications are sent for critical alerts
7. A dashboard visualizes logs and alert data

This project demonstrates event-driven architecture, distributed systems, and automated alerting workflows.

---

## 🏗 Architecture

```mermaid
flowchart LR
    A[Client] --> B[FastAPI API]
    B --> C[Kafka Broker]
    C --> D[Kafka Consumer]
    D --> E[PostgreSQL]

    E --> F[Monitoring Engine]
    F --> G[Alert System]
    G --> H[Email Notifications]

    E --> I[Dashboard APIs]
```

### Components

- **API Service** – Log ingestion & dashboard endpoints
- **Kafka Broker** – Message streaming backbone
- **Consumer Service** – Processes and stores logs
- **PostgreSQL** – Persistent storage
- **Monitoring Engine** – Automated alert generation
- **Email Notification Service** – Sends alert emails
- **Dashboard UI** – Visualizes logs and alerts
- **Docker Compose** – Multi-container orchestration

---

## 🚀 Features

- Real-time log ingestion
- Kafka-based streaming pipeline
- Automated error rate monitoring
- Active and historical alert tracking
- Email notifications for critical alerts
- Dashboard APIs
- Background monitoring thread
- Fully containerized environment

---

## 📧 Email Alerts

When error rates exceed configured thresholds:

- An alert is created and stored in the database
- The system sends an automated email notification
- Email contains:
  - Service name
  - Error rate percentage
  - Time window analyzed
  - Alert timestamp

### Example Use Cases

- Service crash detection
- Error spike detection
- Production incident notification
- Automated operational monitoring

### Example Environment Variables for Email

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com

SMTP_PASSWORD=your_app_password
ALERT_RECEIVER=admin@example.com

> ⚠️ Use app-specific passwords for production environments.

---

## ⚙️ Setup & Installation

### 1️⃣ Clone Repository

```bash
git clone https://github.com/yourusername/LogSentinel.git
cd LogSentinel
```

### 1️⃣ Create Environment File

```bash
POSTGRES_DB=logs_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DATABASE_URL=postgresql://postgres:postgres@db:5432/logs_db
KAFKA_BOOTSTRAP_SERVERS=kafka:9092

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
ALERT_RECEIVER=admin@example.com
```

### 3️⃣ Run with Docker

```bash
docker compose up --build
```

### Access:

```
API → http://localhost:8000
Swagger Docs → http://localhost:8000/docs
Dashboard → http://localhost:8000/
```

### To stop services:

```bash
docker compose down
```

## 📡 API Endpoints

### Log Ingestion

```bash
POST /logs
```

### Monitoring & Alerts

```bash
GET /alerts/check
GET /api/alerts/active
GET /api/alerts/history
```

### Dashboard Data

```bash
GET /api/logs/recent
GET /api/stats/error-rates
```

## 🔍 Automated Monitoring

- Runs every 10 minutes (configurable)
- Calculates error rates per service
- Triggers alerts when thresholds are exceeded
- Stores alert history
- Tracks active alerts

### 🧪 Testing Alert System

- To simulate error spikes:

```bash
python send_bulk_errors.py
```

### 🛠 Tech Stack

- Python 3.11+
- FastAPI
- SQLAlchemy
- PostgreSQL
- Apache Kafka
- Docker & Docker Compose
- Uvicorn

### 👤 Author

- Chetan Mittal
