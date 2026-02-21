LogSentinel
Real-Time Distributed Log Monitoring, Alerting & Email Notification Platform

LogSentinel is a distributed log ingestion and monitoring system built using FastAPI, PostgreSQL, and Kafka. It enables real-time log streaming, automated error rate monitoring, alert tracking, email notifications, and dashboard visualization — fully containerized using Docker.

Overview

LogSentinel simulates a production-grade observability pipeline:

Applications send logs via REST API

Logs are streamed through Kafka

A consumer processes and stores logs in PostgreSQL

A monitoring engine evaluates error rates

Alerts are triggered automatically when thresholds are exceeded

Email notifications are sent for critical alerts

A dashboard visualizes logs and alert data

This project demonstrates event-driven architecture, distributed systems, and automated alerting workflows.

Architecture
Client → FastAPI → Kafka → Consumer → PostgreSQL
↓
Monitoring Engine
↓
Alerts
↓
Email Notifications
Core Components

API Service – Log ingestion & dashboard endpoints

Kafka Broker – Message streaming backbone

Consumer Service – Processes and stores logs

PostgreSQL – Persistent storage

Monitoring Engine – Automated alert generation

Email Notification Service – Sends alert emails

Dashboard UI – Visualizes logs and alerts

Docker Compose – Multi-container orchestration

Features

Real-time log ingestion

Kafka-based streaming pipeline

Automated error rate monitoring

Active and historical alert tracking

Email notifications for critical alerts

Dashboard APIs

Background monitoring thread

Fully containerized environment

Email Alert System

When error rates exceed configured thresholds:

An alert is created and stored in the database

The monitoring engine triggers an email notification

Email includes:

Service name

Error rate percentage

Time window analyzed

Alert timestamp

Required Environment Variables for Email
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
ALERT_RECEIVER=admin@example.com

Use app-specific passwords instead of your real email password for security.

Project Structure
LogSentinel/
│
├── app/
│ ├── main.py
│ ├── database.py
│ ├── models.py
│ ├── schemas.py
│ ├── kafka_producer.py
│ ├── consumer.py
│ ├── monitoring.py
│ ├── email_service.py
│ ├── dashboard_logic.py
│ └── static/dashboard.html
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env
└── send_bulk_errors.py
Setup & Installation

1. Clone Repository
   git clone https://github.com/yourusername/LogSentinel.git
   cd LogSentinel
2. Create .env File

Create a .env file in the project root:

POSTGRES_DB=logs_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DATABASE_URL=postgresql://postgres:postgres@db:5432/logs_db
KAFKA_BOOTSTRAP_SERVERS=kafka:9092

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
ALERT_RECEIVER=admin@example.com 3. Run with Docker
docker compose up --build

Access:

API → http://localhost:8000

Swagger Docs → http://localhost:8000/docs

Dashboard → http://localhost:8000/

To stop:

docker compose down
API Endpoints
Log Ingestion
POST /logs
Alerts
GET /alerts/check
GET /api/alerts/active
GET /api/alerts/history
Dashboard Data
GET /api/logs/recent
GET /api/stats/error-rates
Testing Alert System

To simulate high error rates:

python send_bulk_errors.py

This will trigger alert generation and email notifications.

Tech Stack

Python 3.11+

FastAPI

SQLAlchemy

PostgreSQL

Apache Kafka

SMTP (Email Notifications)

Docker & Docker Compose

Uvicorn

Development Without Docker

Create virtual environment:

python -m venv venv
venv\Scripts\activate

Install dependencies:

pip install -r requirements.txt

Run application:

uvicorn app.main:app --reload
Future Improvements

Prometheus integration

Grafana dashboard

JWT authentication

Rate limiting

Structured logging (JSON logs)

Kubernetes deployment

Horizontal scaling

CI/CD integration

Slack / Webhook alert support

What This Project Demonstrates

Event-driven architecture

Distributed system design

Stream processing with Kafka

Automated monitoring & alerting

Email notification pipelines

Containerized microservices

Observability principles

Author

Your Name
Backend / Distributed Systems Engineer
