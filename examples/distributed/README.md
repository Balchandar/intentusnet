# IntentusNet Distributed Demo

This demo shows real distributed execution using:

- RemoteAgentProxy
- HTTPRemoteAgentTransport
- NodeExecutionGateway
- NodeIdentity + HMAC signing
- Optional EMCL encryption

## Architecture

Node A (Orchestrator)
|
|--- HMAC-signed HTTP request → /execute-agent
v
Node B (Worker) - Validates signature - Decrypts EMCL (optional) - Executes agent - Returns AgentResponse

## Run Locally
