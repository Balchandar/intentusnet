# Basic MCP Server + IntentusNet Gateway

A 5-minute example showing how to wrap any MCP server with the IntentusNet Deterministic MCP Gateway.

## What This Demonstrates

1. Run a simple MCP server with a deterministic `add(a, b)` tool
2. Wrap it with the IntentusNet Gateway (zero server changes)
3. Send a request through the gateway
4. See the execution recorded with deterministic seed
5. Replay the execution from WAL (no re-execution)

## Prerequisites

```bash
pip install intentusnet
```

## Step 1: Start the MCP Server

```bash
python server.py
```

Output:
```
Basic MCP server running on http://localhost:5123
Tools available: add(a, b)
```

## Step 2: Start the IntentusNet Gateway

In a second terminal:

```bash
intentusnet gateway --http http://localhost:5123
```

The gateway wraps the MCP server transparently. No changes to the server.

## Step 3: Send a Request

In a third terminal, send a tool call through the gateway:

```bash
curl -s http://localhost:8765 -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "add",
      "arguments": {"a": 17, "b": 25}
    }
  }' | python -m json.tool
```

You should see:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "17 + 25 = 42"
      }
    ]
  }
}
```

The response is identical to calling the server directly — the gateway is transparent.

## Step 4: List Recorded Executions

```bash
intentusnet executions
```

Output:
```
EXECUTION ID                             STATUS       METHOD          TOOL                 DURATION     STARTED
------------------------------------------------------------------------------------------------------------------------
a1b2c3d4-e5f6-7890-abcd-ef1234567890     completed    tools/call      add                  12ms         2024-01-15T10:30
```

## Step 5: Replay the Execution

Copy the execution ID from step 4 and replay:

```bash
intentusnet replay <execution-id>
```

Output:
```
Replay Result (WAL Playback)
==================================================
Execution ID:       a1b2c3d4-e5f6-7890-abcd-ef1234567890
Status:             completed
Method:             tools/call
Tool:               add
Request hash:       7f83b1657ff1fc...
Response hash:      3a7bd3e2360a3d...
Started:            2024-01-15T10:30:00.123456+00:00
Completed:          2024-01-15T10:30:00.135789+00:00
Duration:           12.3ms
WAL entries:        2

Deterministic Seed:
  Sequence:         1
  Timestamp:        2024-01-15T10:30:00.123456+00:00
  Random seed:      a3f7c2b1e4d6...
  Process ID:       12345

Response:
  {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "17 + 25 = 42"}]}}

WARNING: This is the RECORDED response from execution time. No MCP tool was re-executed.
```

## Step 6: Check Gateway Status

```bash
intentusnet status
```

Output:
```
IntentusNet MCP Gateway v1.5.1
========================================
WAL directory:      .intentusnet/gateway/wal
WAL integrity:      OK
WAL entries:        2

Executions:
  Total:            1
  Completed:        1
  Failed:           0
```

## What You Should See

After completing all steps:

- Gateway active: Requests pass through transparently
- Execution recorded: Every tool call captured with hashes and timing
- Replay works: Stored response returned from WAL without re-execution
- Deterministic seed captured: Prepares for future deterministic replay

## How It Works

```
MCP Client (curl)
       |
       v
IntentusNet Gateway (port 8765)
  - Intercepts tool calls
  - Records to WAL
  - Captures deterministic seed
  - Indexes execution
       |
       v
MCP Server (port 5123)
  - Runs add(17, 25)
  - Returns result
```

The gateway adds no protocol changes. The MCP server and client are unmodified.
