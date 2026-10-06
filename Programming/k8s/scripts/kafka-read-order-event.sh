#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <order-id>" >&2
  exit 2
fi

order_id=$1
namespace=${NAMESPACE:-production}
pod=$(kubectl -n "$namespace" get pod \
  -l app.kubernetes.io/name=inventory-service \
  -o jsonpath='{.items[0].metadata.name}')

kubectl -n "$namespace" exec -i "$pod" -- \
  env ORDER_ID="$order_id" python3 - <<'PY'
import asyncio
import json
import os
import ssl
import sys
import time

from aiokafka import AIOKafkaConsumer
from aiokafka.structs import TopicPartition

topic = "aims.business.order.created.v1"
order_id = os.environ["ORDER_ID"]


async def main():
    tls = ssl.create_default_context(
        cafile=os.getenv("KAFKA_TLS_CA", "/var/run/aims-kafka-ca/ca.crt")
    )
    tls.load_cert_chain(
        os.getenv("KAFKA_TLS_CERT", "/var/run/aims-kafka/user.crt"),
        os.getenv("KAFKA_TLS_KEY", "/var/run/aims-kafka/user.key"),
    )
    consumer = AIOKafkaConsumer(
        bootstrap_servers=os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "aims-kafka-kafka-bootstrap:9093"
        ),
        security_protocol="SSL",
        ssl_context=tls,
        enable_auto_commit=False,
    )
    started = False
    try:
        await consumer.start()
        started = True
        partitions = consumer.partitions_for_topic(topic)
        assigned = [TopicPartition(topic, p) for p in partitions]
        consumer.assign(assigned)
        await consumer.seek_to_beginning(*assigned)

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            batches = await consumer.getmany(timeout_ms=1000, max_records=1000)
            for tp, messages in batches.items():
                for message in messages:
                    event = json.loads(message.value)
                    if event.get("aggregateId") == order_id:
                        print(f"topic={message.topic}")
                        print(f"partition={tp.partition} offset={message.offset}")
                        print(f"key={message.key.decode() if message.key else None}")
                        print("value_json=")
                        print(json.dumps(event, ensure_ascii=False, indent=2))
                        return
        print(f"No retained OrderCreated record for orderId={order_id}", file=sys.stderr)
        sys.exit(1)
    finally:
        if started:
            try:
                await consumer.stop()
            except asyncio.CancelledError:
                pass


asyncio.run(main())
PY
