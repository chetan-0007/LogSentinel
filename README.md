# log_anal

Simple FastAPI service that sends logs to Kafka; a consumer persists them to Postgres and a monitoring module checks error rates.

Quick start (using Docker Compose):

```bash
docker-compose up --build
```

Notes:

- API endpoint: `POST /logs` — request body follows `app.schemas.LogCreate`.
- The app will create tables from models at startup via `Base.metadata.create_all(bind=engine)`; if you prefer explicit migrations run the SQL in `migrations/001_create_alert_tables.sql`.
- The consumer is launched by the `consumer` service in `docker-compose.yml` and expects Kafka at `kafka:9092`.
