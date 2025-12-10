# examples/advanced/web_server.py

from fastapi import FastAPI
from pydantic import BaseModel
from intentusnet.core.runtime import IntentusRuntime
from intentusnet.transport.inprocess import InProcessTransport
from intentusnet.core.client import IntentusClient
from examples.advanced.demo_advanced_research import register_all

app = FastAPI()

runtime = IntentusRuntime()
register_all(runtime)
client = IntentusClient(InProcessTransport(runtime.router))


class ResearchRequest(BaseModel):
    topic: str


@app.post("/run_research")
def run_research(req: ResearchRequest):
    resp = client.send_intent("ResearchIntent", {"topic": req.topic})
    if resp.error:
        return {"error": resp.error.message}
    return resp.payload
