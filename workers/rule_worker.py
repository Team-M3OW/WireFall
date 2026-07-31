import pika
import json
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis
from inference.rule_generator import generate_rule_from_payload

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

def callback(ch, method, properties, body):
    data = json.loads(body)
    payload = data.get("payload")
    tenant_id = data.get("tenant_id", "default")
    
    logging.info(f"Processing rule generation for tenant {tenant_id}")
    try:
        new_rule = generate_rule_from_payload(payload)
        if new_rule:
            r = redis.Redis.from_url(REDIS_URL)
            rule_key = f"waf:{tenant_id}:rules:regex"
            r.sadd(rule_key, new_rule)
            logging.info(f"Successfully generated rule: {new_rule}")
    except Exception as e:
        logging.error(f"Error during rule generation: {e}")
    finally:
        ch.basic_ack(delivery_tag=method.delivery_tag)

def start_worker():
    logging.info("Starting Rule Generation Worker...")
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue='rule_generation', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='rule_generation', on_message_callback=callback)
    channel.start_consuming()

if __name__ == "__main__":
    start_worker()
