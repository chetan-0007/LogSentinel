from typing import Dict
from sqlalchemy.orm import Session
from app.kafka_producer import send_log


def create_log_logic(log_data: Dict, db: Session = None) -> Dict:
    """Logic for handling incoming logs from API.

    Currently the API publishes logs to Kafka and returns a confirmation.
    The DB write is performed by the consumer, so the API does not persist here.
    """
    try:
        # Publish to Kafka (producer will retry until connected)
        send_log(log_data)
        return {"status": "sent to kafka"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
