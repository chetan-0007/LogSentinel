from kafka import KafkaConsumer
import json
from app.database import SessionLocal
from app.models import Log
import time
from kafka import errors

def start_consumer():
    while True:
        try:
            consumer = KafkaConsumer(
                "logs",
                bootstrap_servers="kafka:9092",
                auto_offset_reset="earliest",
                group_id="log-consumer-group",
                value_deserializer=lambda m: json.loads(m.decode("utf-8"))
            )
            print("Kafka consumer connected")
            break
        except errors.NoBrokersAvailable:
            print("Kafka not ready, retrying in 3 seconds...")
            time.sleep(3)

    for message in consumer:
        data = message.value
        db = SessionLocal()
        try:
            log = Log(**data)
            db.add(log)
            db.commit()
        except Exception as e:
            print("Error saving log:", e)
            db.rollback()
        finally:
            db.close()

if __name__ == "__main__":
    start_consumer()