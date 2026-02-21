from kafka import KafkaProducer, errors
import json
import time

producer = None

def _json_default(o):
    # Convert Enum-like objects to their value when possible
    return getattr(o, "value", str(o))

def get_producer():
    global producer
    if producer is None:
        while True:
            try:
                producer = KafkaProducer(
                    bootstrap_servers="kafka:9092",
                    value_serializer=lambda v: json.dumps(v, default=_json_default).encode("utf-8")
                )
                print("Kafka producer connected")
                break
            except errors.NoBrokersAvailable:
                print("Kafka not ready, retrying in 3 seconds...")
                time.sleep(3)
    return producer

def send_log(log_data: dict):
    p = get_producer()
    service = log_data.get("service", "unknown")
    try:
        p.send("logs", key=service.encode("utf-8"), value=log_data)
        p.flush()
    except Exception as e:
        # Log to stdout so container logs capture it
        print("Failed to send log to Kafka:", e)