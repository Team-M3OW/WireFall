import pika
import json
import logging
import os

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")

def publish_rule_generation_task(payload: str, tenant_id: str):
    """
    Publish a novel attack payload to a message queue for asynchronous rule generation.
    This prevents the FastAPI worker from blocking during LLM inference.
    """
    try:
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        channel.queue_declare(queue='rule_generation', durable=True)
        
        message = json.dumps({"payload": payload, "tenant_id": tenant_id})
        
        channel.basic_publish(
            exchange='',
            routing_key='rule_generation',
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent message
            )
        )
        connection.close()
    except Exception as e:
        logging.error(f"Failed to publish to RabbitMQ: {e}")
