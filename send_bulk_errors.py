"""send_bulk_errors.py
Sends a number of synthetic logs to the local API with a high percentage of ERROR level messages.
Usage:
    python send_bulk_errors.py --count 500 --error-rate 0.95 --delay-ms 5
"""
import argparse
import requests
import random
import time
import datetime

API_URL = "http://localhost:8000/logs"
SERVICES = ["auth-service","payments","orders"]
ENDPOINTS = ["/login","/checkout","/orders"]
STATUSES = [200,201,400,401,403,404,500]


def pick_level(error_rate):
    return "ERROR" if random.random() < error_rate else ("WARN" if random.random() < 0.5 else "INFO")


def send_one(i, error_rate):
    svc = random.choice(SERVICES)
    level = pick_level(error_rate)
    payload = {
        "service": svc,
        "level": level,
        "user_id": str(random.randint(1, 2000)),
        "endpoint": random.choice(ENDPOINTS),
        "status_code": random.choice(STATUSES),
        "latency_ms": random.randint(1, 2000),
        "message": f"Synthetic error-heavy log #{i} for {svc} ({level})",
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    try:
        resp = requests.post(API_URL, json=payload, timeout=5)
        return resp.status_code, resp.text
    except Exception as e:
        return None, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--error-rate", type=float, default=0.95, help="Fraction of messages set to ERROR (0.0-1.0)")
    parser.add_argument("--delay-ms", type=int, default=5)
    args = parser.parse_args()

    sent = 0
    errors = 0
    failures = 0

    start = time.time()
    for i in range(1, args.count + 1):
        status, body = send_one(i, args.error_rate)
        if status is None:
            failures += 1
            print(f"{i}: FAILED -> {body}")
        else:
            sent += 1
            if status >= 400:
                errors += 1
            print(f"{i}: {status} ({body.strip()})")

        time.sleep(args.delay_ms / 1000.0)

    elapsed = time.time() - start
    print("\nDone")
    print(f"Requested: {args.count}")
    print(f"Sent: {sent}, client-visible errors (>=400): {errors}, failures: {failures}")
    print(f"Elapsed: {elapsed:.2f}s, rate: {sent/elapsed:.1f} req/s")


if __name__ == '__main__':
    main()
