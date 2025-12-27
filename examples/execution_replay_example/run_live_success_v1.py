from runtime_v1 import create_runtime_v1

runtime = create_runtime_v1()
client = runtime.client()

response = client.send_intent(
    intent_name="support.ticket.analyze",
    payload={"text": "Payment failed with error 402"},
)

print("Live success (v1):", response.payload)
