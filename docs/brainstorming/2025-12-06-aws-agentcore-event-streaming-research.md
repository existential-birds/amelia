# AWS AgentCore Event Streaming and Observability Patterns

**Date:** 2025-12-06
**Purpose:** Deep dive research into AWS AgentCore event streaming, real-time observability, and WebSocket patterns for building real-time dashboards

---

## Executive Summary

AWS AgentCore provides comprehensive event streaming and observability through **three primary mechanisms**:

1. **Runtime Event Streaming** - `InvokeAgentRuntime` API with `text/event-stream` responses and WebSocket bidirectional streaming
2. **Observability Data Streaming** - OpenTelemetry-compatible spans/traces/logs exported to CloudWatch
3. **CloudWatch Subscription Filters** - Real-time log streaming to Lambda, Kinesis, or Firehose

**Key Finding:** AgentCore does NOT have built-in webhook/callback mechanisms for Runtime state changes. Instead, it uses a **pull-based streaming model** where clients consume events via streaming HTTP responses or WebSocket connections, and observability data flows through CloudWatch with optional real-time subscription filters.

---

## Table of Contents

1. [Runtime Event Streaming](#runtime-event-streaming)
2. [WebSocket Streaming Patterns](#websocket-streaming-patterns)
3. [Observability Data Flow](#observability-data-flow)
4. [Real-Time Progress Updates](#real-time-progress-updates)
5. [Building WebSocket Hubs](#building-websocket-hubs)
6. [Real-Time Dashboard Patterns](#real-time-dashboard-patterns)
7. [Event Types and Schemas](#event-types-and-schemas)
8. [Integration Examples](#integration-examples)
9. [Limitations and Workarounds](#limitations-and-workarounds)

---

## Runtime Event Streaming

### InvokeAgentRuntime API

**Core API Pattern:**
```python
import boto3

client = boto3.client("bedrock-agentcore", region="us-west-2")

response = client.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:us-west-2:111122223333:runtime/test_agent",
    runtimeSessionId="12345678-1234-5678-9abc-123456789012",
    payload='{"query": "Plan a weekend in Seattle"}'
)

# Response structure
{
    'runtimeSessionId': 'string',
    'mcpSessionId': 'string',
    'mcpProtocolVersion': 'string',
    'traceId': 'string',
    'traceParent': 'string',
    'traceState': 'string',
    'baggage': 'string',
    'contentType': 'text/event-stream' | 'application/json',
    'response': StreamingBody(),
    'statusCode': 123
}
```

### Streaming Response Handling

**Event Stream Processing:**
```python
if "text/event-stream" in response.get("contentType", ""):
    content = []
    for line in response["response"].iter_lines(chunk_size=10):
        if line:
            line = line.decode("utf-8")
            if line.startswith("data: "):
                line = line[6:]  # Strip "data: " prefix
                print(line)
                content.append(line)
```

**Event Format:**
```
Content-Type: text/event-stream

data: {"event": "partial response 1"}
data: {"event": "partial response 2"}
data: {"event": "final response"}
```

### Key Characteristics

- **Payload Size:** Up to 100 MB
- **Response Type:** Streaming (real-time chunks) or standard JSON
- **Session Management:** Use `runtimeSessionId` for conversation continuity
- **Retry Behavior:** Exponential backoff for `ThrottlingException`

**Sources:**
- [Invoke an AgentCore Runtime agent](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)
- [Stream agent responses](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/response-streaming.html)

---

## WebSocket Streaming Patterns

### Overview

AgentCore Runtime supports **bidirectional WebSocket streaming** via the `InvokeAgentRuntimeWithWebSocketStream` operation, enabling real-time conversations with interruption handling.

**Announced:** December 2025 - [Bi-directional streaming announcement](https://aws.amazon.com/about-aws/whats-new/2025/12/bedrock-agentcore-runtime-bi-directional-streaming/)

### Connection Endpoint

```
wss://bedrock-agentcore.<region>.amazonaws.com/runtimes/<agentRuntimeArn>/ws
```

### Authentication Methods

**1. AWS SigV4 Headers:**
```python
from bedrock_agentcore.runtime import AgentCoreRuntimeClient
import websockets
import asyncio
import json
import os

async def main():
    runtime_arn = os.getenv('AGENT_ARN')
    client = AgentCoreRuntimeClient(region="us-west-2")

    ws_url, headers = client.generate_ws_connection(runtime_arn=runtime_arn)

    async with websockets.connect(ws_url, additional_headers=headers) as ws:
        await ws.send(json.dumps({"inputText": "Hello!"}))
        response = await ws.recv()
        print(f"Received: {response}")
```

**2. SigV4 Pre-signed URL:**
```python
sigv4_url = client.generate_presigned_url(
    runtime_arn=runtime_arn,
    expires=300  # 5 minutes
)

async with websockets.connect(sigv4_url) as ws:
    await ws.send(json.dumps({"inputText": "Hello!"}))
    response = await ws.recv()
```

**3. OAuth 2.0 Bearer Token:**
```python
ws_url, headers = client.generate_ws_connection_oauth(
    runtime_arn=runtime_arn,
    bearer_token=bearer_token
)

async with websockets.connect(ws_url, additional_headers=headers) as ws:
    await ws.send(json.dumps({"inputText": "Hello!"}))
    response = await ws.recv()
```

### Session Management with WebSocket

```python
session_id = "user-123-conversation-456"

ws_url, headers = client.generate_ws_connection(
    runtime_arn=runtime_arn,
    session_id=session_id
)

async with websockets.connect(ws_url, additional_headers=headers) as ws:
    # Send multiple messages in same session
    await ws.send(json.dumps({"inputText": "First message"}))
    response1 = await ws.recv()

    await ws.send(json.dumps({"inputText": "Follow-up message"}))
    response2 = await ws.recv()
```

**Session Header:** `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`

### Message Format

**Request:**
```json
{
  "inputText": "message content"
}
```

**Response:**
```json
{
  "echo": {
    "inputText": "message content"
  }
}
```

### Agent Implementation

**Container Requirements:**
- WebSocket endpoint on **port 8080** at path **`/ws`**
- Health check endpoint `/ping` (HTTP)

**Example Agent Handler:**
```python
from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.websocket
async def websocket_handler(websocket, context):
    """Bidirectional streaming WebSocket handler."""
    await websocket.accept()  # Accept connection

    try:
        data = await websocket.receive_json()  # Receive message
        await websocket.send_json({"echo": data})  # Send response
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await websocket.close()  # Close connection

if __name__ == "__main__":
    app.run(log_level="info")
```

### Bidirectional Features

- **Real-time bidirectional communication** - Simultaneous send/receive
- **Low-latency** - Optimized for real-time applications
- **Interrupt handling** - Clients can interrupt agent responses mid-stream
- **Persistent connections** - Maintains connection state
- **Session isolation** - Separate contexts per session

### WebSocket Close Codes

| Code | Meaning |
|------|---------|
| 1000 | Normal closure |
| 1001 | Going away |
| 1008 | Policy violated (limit exceeded) |
| 1009 | Message too big (frame size limit exceeded) |
| 1011 | Server error |

**Sources:**
- [Get started with WebSocket streaming](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-websocket.html)
- [How it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)

---

## Observability Data Flow

### Architecture

```
┌─────────────────────────────────────────────┐
│         AgentCore Runtime                   │
│  ┌───────────────────────────────────────┐  │
│  │  Agent Code (emits OTEL spans/logs)   │  │
│  └────────────┬──────────────────────────┘  │
│               │                             │
│               ▼                             │
│  ┌───────────────────────────────────────┐  │
│  │  AWS Distro for OpenTelemetry (ADOT) │  │
│  └────────────┬──────────────────────────┘  │
└───────────────┼─────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────┐
│         Amazon CloudWatch                     │
│  ┌─────────────────┬────────────────────────┐ │
│  │ CloudWatch Logs │ CloudWatch X-Ray       │ │
│  │ (Spans/Traces)  │ (Distributed Tracing)  │ │
│  └────────┬────────┴────────────┬───────────┘ │
└───────────┼─────────────────────┼─────────────┘
            │                     │
            ▼                     ▼
┌───────────────────────┐  ┌──────────────────┐
│ Subscription Filters  │  │ Transaction      │
│ (Real-time streaming) │  │ Search (Spans)   │
└───────────┬───────────┘  └──────────────────┘
            │
            ▼
┌─────────────────────────────────────┐
│ External Consumers                  │
│ - Lambda Functions                  │
│ - Kinesis Data Streams              │
│ - Kinesis Data Firehose             │
│ - OpenSearch Service                │
└─────────────────────────────────────┘
```

### OpenTelemetry (OTEL) Integration

**Automatic Instrumentation:**
AgentCore emits telemetry in **OpenTelemetry-compatible format**, capturing:
- Framework operations
- LLM calls
- Tool invocations
- Execution flows
- Resource utilization

**No code changes required** for basic instrumentation.

### Data Model

**1. Sessions:**
- Complete interaction context between user and agent
- Unique identifier per session
- Captures full lifecycle of user engagement
- Maintains state across multiple exchanges

**2. Traces:**
- Detailed record of single request-response cycle
- Begins with agent invocation
- May include calls to other agents
- Captures complete execution path

**3. Spans:**
- Discrete, measurable unit of work within execution flow
- Fine-grained operations during request processing
- Defined start and end time
- Precise timeline of agent activities

### CloudWatch Storage

**Automatic Storage:**
- All metrics, spans, and logs stored in Amazon CloudWatch
- Viewable via CloudWatch console
- Downloadable using AWS CLI/SDKs

**Log Group Naming:**
- Memory/Gateway: `/aws/vendedlogs/bedrock-agentcore/{resource-type}/APPLICATION_LOGS/{resource-id}`
- Runtime agents: Auto-created CloudWatch log group
- Traces: `aws/spans` log group

### Environment Configuration

**OTEL Environment Variables (for non-Runtime agents):**
```bash
# AWS credentials
export AWS_ACCOUNT_ID=<account-id>
export AWS_DEFAULT_REGION=<region>
export AWS_REGION=<region>
export AWS_ACCESS_KEY_ID=<access-key-id>
export AWS_SECRET_ACCESS_KEY=<secret-key>

# OTEL configuration
export AGENT_OBSERVABILITY_ENABLED=true
export OTEL_PYTHON_DISTRO=aws_distro
export OTEL_PYTHON_CONFIGURATOR=aws_configurator

# Resource attributes
export OTEL_RESOURCE_ATTRIBUTES=\
service.name=<agent-name>,\
aws.log.group.names=/aws/bedrock-agentcore/runtimes/<agent-id>,\
cloud.resource_id=<AgentEndpointArn>

# Export configuration
export OTEL_EXPORTER_OTLP_LOGS_HEADERS=\
x-aws-log-group=/aws/bedrock-agentcore/runtimes/<agent-id>,\
x-aws-log-stream=runtime-logs,\
x-aws-metric-namespace=bedrock-agentcore

export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_TRACES_EXPORTER=otlp
```

**For AgentCore Runtime:**
Observability is **automatically enabled** with no additional configuration.

### Custom Headers for Tracing

**Supported Trace Headers:**
| Header | Purpose | Example |
|--------|---------|---------|
| **X-Amzn-Trace-Id** | X-Ray format trace ID | `Root=1-5759e988-bd862e3fe1be46a994272793;Parent=53995c3f42cd8ad8;Sampled=1` |
| **traceparent** | W3C tracing standard | `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01` |
| **X-Amzn-Bedrock-AgentCore-Runtime-Session-Id** | Session identifier | `a1b2c3d4-5678-90ab-cdef-EXAMPLEaaaaa` |
| **mcp-session-id** | MCP session identifier | `mcp-a1b2c3d4-5678-90ab-cdef-EXAMPLEaaaaa` |
| **tracestate** | Vendor-specific tracing info | `congo=t61rcWkgMzE,rojo=00f067aa0ba902b7` |
| **baggage** | Context propagation | `userId=alice,serverRegion=us-east-1` |

**Sources:**
- [Add observability to resources](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)
- [Observe agent applications](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)

---

## Real-Time Progress Updates

### Question 1: Does AgentCore have built-in event streaming to external consumers?

**Answer:** **No direct event streaming to external consumers.**

AgentCore provides:
- **Streaming responses** to the invoking client via `InvokeAgentRuntime` (HTTP streaming or WebSocket)
- **Observability data** flows to CloudWatch (not direct external consumers)

**External streaming requires CloudWatch Subscription Filters** (see below).

### Question 2: How do you get real-time progress updates from a running Runtime?

**Answer:** **Three patterns:**

**Pattern 1: HTTP Streaming (Pull-based)**
```python
response = client.invoke_agent_runtime(...)

for line in response["response"].iter_lines():
    if line.startswith("data: "):
        event = json.loads(line[6:])
        print(f"Progress: {event}")
```

**Pattern 2: WebSocket Streaming (Bidirectional)**
```python
async with websockets.connect(ws_url, additional_headers=headers) as ws:
    await ws.send(json.dumps({"inputText": "Task"}))

    # Receive streaming updates
    while True:
        try:
            update = await ws.recv()
            print(f"Progress: {update}")
        except websockets.exceptions.ConnectionClosed:
            break
```

**Pattern 3: CloudWatch Logs (Near Real-time)**
```python
logs_client = boto3.client('logs')

# Stream logs from log group
response = logs_client.tail(
    logGroupName='/aws/bedrock-agentcore/runtimes/my-agent',
    filterPattern='[timestamp, request_id, event_type, ...]'
)

for event in response['events']:
    print(event['message'])
```

### Question 3: Is there a webhook/callback mechanism for Runtime state changes?

**Answer:** **No built-in webhook/callback mechanism.**

AgentCore does NOT provide:
- Webhooks for state changes
- Callback URLs for completion notifications
- Push-based event delivery

**Workarounds:**
1. **Client polling** - Check session status periodically
2. **CloudWatch Subscription Filters** - Stream logs to Lambda for custom webhooks
3. **EventBridge integration** - Use CloudWatch alarms to trigger EventBridge events

### Question 4: How does Observability data flow? Can you subscribe to OTEL spans in real-time?

**Answer:** **OTEL spans flow to CloudWatch; real-time subscription via CloudWatch Subscription Filters.**

**Flow:**
```
Agent → ADOT SDK → CloudWatch Logs → Subscription Filter → External Consumer
```

**Real-time Span Subscription:**
```python
import boto3

logs_client = boto3.client('logs')

# Create subscription filter to stream spans to Kinesis
logs_client.put_subscription_filter(
    logGroupName='aws/spans',
    filterName='span-stream',
    filterPattern='',  # All spans
    destinationArn='arn:aws:kinesis:us-west-2:123456789012:stream/span-stream'
)
```

**CloudWatch Transaction Search Setup:**
```bash
# Enable Transaction Search for spans
aws logs put-resource-policy --policy-name MyResourcePolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Sid": "TransactionSearchXRayAccess",
      "Effect": "Allow",
      "Principal": {"Service": "xray.amazonaws.com"},
      "Action": "logs:PutLogEvents",
      "Resource": [
        "arn:aws:logs:region:account-id:log-group:aws/spans:*"
      ]
    }]
  }'

# Update trace segment destination to CloudWatch
aws xray update-trace-segment-destination --destination CloudWatchLogs
```

**Sources:**
- [Build trustworthy AI agents with observability](https://aws.amazon.com/blogs/machine-learning/build-trustworthy-ai-agents-with-amazon-bedrock-agentcore-observability/)
- [CloudWatch Transaction Search setup](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)

---

## Building WebSocket Hubs

### Question 5: What's the pattern for building a WebSocket hub that streams Runtime progress?

**Pattern: Hub-and-Spoke WebSocket Architecture**

```
┌─────────────────────────────────────────────┐
│         Web Browser Clients                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Client 1 │  │ Client 2 │  │ Client N │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
└───────┼─────────────┼─────────────┼─────────┘
        │             │             │
        │ WebSocket   │ WebSocket   │ WebSocket
        │             │             │
        ▼             ▼             ▼
┌─────────────────────────────────────────────┐
│        WebSocket Hub (API Gateway WS)       │
│  ┌───────────────────────────────────────┐  │
│  │  Connection Manager (DynamoDB)        │  │
│  │  - connectionId → sessionId mapping   │  │
│  │  - sessionId → [connectionIds]        │  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │  Lambda: $connect, $disconnect        │  │
│  │  Lambda: sendMessage, broadcast       │  │
│  └───────────────────────────────────────┘  │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│        AgentCore Runtime (Backend)          │
│  ┌───────────────────────────────────────┐  │
│  │  Lambda: InvokeAgentRuntime           │  │
│  │  - Receives task requests             │  │
│  │  - Streams responses to hub           │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  ┌───────────────────────────────────────┐  │
│  │  CloudWatch Logs Subscription Filter  │  │
│  │  → Lambda → Broadcast to clients      │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### Implementation Steps

**Step 1: API Gateway WebSocket API**
```bash
# Create WebSocket API
aws apigatewayv2 create-api \
  --name AgentProgressHub \
  --protocol-type WEBSOCKET \
  --route-selection-expression '$request.body.action'
```

**Step 2: Connection Manager (DynamoDB)**
```python
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('WebSocketConnections')

def on_connect(event):
    """Store connection when client connects."""
    connection_id = event['requestContext']['connectionId']
    session_id = event['queryStringParameters'].get('sessionId')

    table.put_item(Item={
        'connectionId': connection_id,
        'sessionId': session_id,
        'timestamp': int(time.time())
    })

    return {'statusCode': 200, 'body': 'Connected'}

def on_disconnect(event):
    """Remove connection when client disconnects."""
    connection_id = event['requestContext']['connectionId']

    table.delete_item(Key={'connectionId': connection_id})

    return {'statusCode': 200, 'body': 'Disconnected'}
```

**Step 3: AgentCore Streaming Handler**
```python
import boto3
import json

agentcore_client = boto3.client('bedrock-agentcore')
apigw_client = boto3.client('apigatewaymanagementapi',
                             endpoint_url='https://your-api-id.execute-api.region.amazonaws.com/prod')

def invoke_agent_and_stream(session_id, prompt):
    """Invoke AgentCore Runtime and stream progress to connected clients."""

    # Get all connections for this session
    response = table.query(
        IndexName='sessionId-index',
        KeyConditionExpression=Key('sessionId').eq(session_id)
    )
    connections = response['Items']

    # Invoke AgentCore Runtime with streaming
    response = agentcore_client.invoke_agent_runtime(
        agentRuntimeArn='arn:aws:bedrock-agentcore:...',
        runtimeSessionId=session_id,
        payload=json.dumps({'prompt': prompt})
    )

    # Stream response events to all connected clients
    for line in response['response'].iter_lines():
        if line.startswith(b'data: '):
            event_data = line[6:].decode('utf-8')

            # Broadcast to all connections for this session
            for conn in connections:
                try:
                    apigw_client.post_to_connection(
                        ConnectionId=conn['connectionId'],
                        Data=event_data.encode('utf-8')
                    )
                except apigw_client.exceptions.GoneException:
                    # Connection no longer exists, clean up
                    table.delete_item(Key={'connectionId': conn['connectionId']})
```

**Step 4: CloudWatch Subscription Filter (Optional - for detailed logs)**
```python
def cloudwatch_logs_handler(event):
    """Lambda triggered by CloudWatch Logs Subscription Filter."""

    # Decode CloudWatch Logs data
    import gzip
    import base64

    data = json.loads(gzip.decompress(base64.b64decode(event['awslogs']['data'])))

    for log_event in data['logEvents']:
        message = json.loads(log_event['message'])
        session_id = message.get('sessionId')

        if session_id:
            # Get connections for this session
            response = table.query(
                IndexName='sessionId-index',
                KeyConditionExpression=Key('sessionId').eq(session_id)
            )

            # Broadcast log event to connected clients
            for conn in response['Items']:
                apigw_client.post_to_connection(
                    ConnectionId=conn['connectionId'],
                    Data=json.dumps({
                        'type': 'log',
                        'data': message
                    }).encode('utf-8')
                )
```

**Step 5: Client-Side WebSocket**
```javascript
const ws = new WebSocket('wss://your-api-id.execute-api.region.amazonaws.com/prod?sessionId=user-123');

ws.onopen = () => {
  console.log('Connected to progress hub');

  // Request agent invocation
  ws.send(JSON.stringify({
    action: 'invokeAgent',
    prompt: 'Analyze this codebase'
  }));
};

ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log('Progress update:', update);

  // Update UI with streaming progress
  updateProgressUI(update);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected from progress hub');
};
```

### Alternative: Direct WebSocket to AgentCore

**For simpler scenarios, connect directly to AgentCore WebSocket:**
```javascript
// Client connects directly to AgentCore Runtime WebSocket
const runtime_arn = 'arn:aws:bedrock-agentcore:...';
const ws_url = await getPresignedWebSocketUrl(runtime_arn);

const ws = new WebSocket(ws_url);

ws.onopen = () => {
  ws.send(JSON.stringify({inputText: 'Start task'}));
};

ws.onmessage = (event) => {
  const progress = JSON.parse(event.data);
  console.log('Agent progress:', progress);
};
```

**Limitation:** Direct connection requires client-side AWS credentials or pre-signed URLs.

---

## Real-Time Dashboard Patterns

### Question 6: Are there any examples of building real-time dashboards for AgentCore agents?

**Answer:** **Yes, three primary patterns:**

### Pattern 1: CloudWatch Native Dashboard

**Built-in AgentCore Observability Dashboard:**
- Trace visualizations
- Custom span metric graphs
- Error breakdowns
- Token usage, latency, session duration
- Error rates

**Access:**
```
CloudWatch Console → Application Signals (APM) → Transaction search
```

**Metrics Available:**
- Session count
- Latency & duration
- Token usage
- Error rates
- Custom runtime metrics

**Sources:**
- [Amazon Bedrock AgentCore - Amazon CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AgentCore-Agents.html)

### Pattern 2: Grafana Cloud Integration

**Setup:**
1. Configure CloudWatch metric streams
2. Create Firehose stream to Grafana Cloud
3. Use pre-built AgentCore dashboards

**Code Example:**
```bash
# Go to Amazon Data Firehose
# Create Firehose stream
aws firehose create-delivery-stream \
  --delivery-stream-name grafana-agentcore-metrics \
  --http-endpoint-destination-configuration '{
    "EndpointConfiguration": {
      "Url": "https://your-grafana-endpoint",
      "Name": "Grafana Cloud"
    },
    "S3Configuration": {...}
  }'
```

**Dashboard Features:**
- End-to-end latency
- LLM call details (model, tokens, latency, cost)
- Agent workflow information
- Error traces with exact step and error message
- Token usage and cost tracking
- Tool execution reliability

**Sources:**
- [Monitor AI agent infrastructure in Grafana Cloud](https://grafana.com/blog/2025/11/28/how-to-monitor-amazon-bedrock-agentcore-ai-agent-infrastructure-in-grafana-cloud/)
- [Monitor AI agent applications in Grafana Cloud](https://grafana.com/blog/2025/11/26/how-to-monitor-ai-agent-applications-on-amazon-bedrock-agentcore-with-grafana-cloud/)

### Pattern 3: Custom Real-Time Dashboard with WebSocket

**Architecture:**
```
┌─────────────────────────────────────────────┐
│       Real-Time Dashboard (Web App)         │
│  ┌───────────────────────────────────────┐  │
│  │  React/Vue Dashboard Components       │  │
│  │  - Agent status cards                 │  │
│  │  - Live trace visualization           │  │
│  │  - Token usage meters                 │  │
│  │  - Error rate graphs                  │  │
│  └────────────┬──────────────────────────┘  │
└───────────────┼─────────────────────────────┘
                │ WebSocket
                ▼
┌─────────────────────────────────────────────┐
│     API Gateway WebSocket API + Lambda      │
│  ┌───────────────────────────────────────┐  │
│  │  Aggregates data from:                │  │
│  │  1. CloudWatch Logs (Subscription)    │  │
│  │  2. CloudWatch Metrics API            │  │
│  │  3. AgentCore Runtime status          │  │
│  └───────────────────────────────────────┘  │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│         Data Sources                        │
│  ┌─────────────────────────────────────┐   │
│  │ CloudWatch Logs (Spans/Traces)      │   │
│  │ CloudWatch Metrics (Sessions/Tokens)│   │
│  │ AgentCore Runtime (Active Sessions) │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

**Implementation:**

**Backend Lambda (Data Aggregator):**
```python
import boto3
import json

logs_client = boto3.client('logs')
cloudwatch_client = boto3.client('cloudwatch')

def get_realtime_metrics():
    """Aggregate real-time metrics from CloudWatch."""

    # Get recent metrics
    metrics = cloudwatch_client.get_metric_statistics(
        Namespace='AWS/BedrockAgentCore',
        MetricName='SessionCount',
        Dimensions=[{'Name': 'AgentId', 'Value': 'my-agent'}],
        StartTime=datetime.utcnow() - timedelta(minutes=5),
        EndTime=datetime.utcnow(),
        Period=60,
        Statistics=['Sum']
    )

    # Get recent logs
    logs = logs_client.filter_log_events(
        logGroupName='/aws/bedrock-agentcore/runtimes/my-agent',
        startTime=int((datetime.utcnow() - timedelta(minutes=5)).timestamp() * 1000),
        filterPattern='[timestamp, level=ERROR, ...]'
    )

    return {
        'sessions': metrics['Datapoints'],
        'errors': logs['events']
    }

def broadcast_metrics(apigw_client, connections):
    """Broadcast metrics to all connected dashboard clients."""

    metrics = get_realtime_metrics()

    for conn in connections:
        apigw_client.post_to_connection(
            ConnectionId=conn['connectionId'],
            Data=json.dumps({
                'type': 'metrics_update',
                'data': metrics
            }).encode('utf-8')
        )
```

**Frontend Dashboard (React):**
```javascript
import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis } from 'recharts';

function AgentCoreDashboard() {
  const [metrics, setMetrics] = useState({ sessions: [], errors: [] });
  const [ws, setWs] = useState(null);

  useEffect(() => {
    // Connect to WebSocket hub
    const websocket = new WebSocket('wss://your-api.execute-api.region.amazonaws.com/prod');

    websocket.onmessage = (event) => {
      const update = JSON.parse(event.data);

      if (update.type === 'metrics_update') {
        setMetrics(update.data);
      }
    };

    setWs(websocket);

    return () => websocket.close();
  }, []);

  return (
    <div className="dashboard">
      <h1>AgentCore Real-Time Dashboard</h1>

      <div className="metric-card">
        <h2>Active Sessions</h2>
        <LineChart width={600} height={300} data={metrics.sessions}>
          <XAxis dataKey="Timestamp" />
          <YAxis />
          <Line type="monotone" dataKey="Sum" stroke="#8884d8" />
        </LineChart>
      </div>

      <div className="metric-card">
        <h2>Recent Errors</h2>
        <ul>
          {metrics.errors.map((error, i) => (
            <li key={i}>{error.message}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
```

**Polling Alternative (if WebSocket not needed):**
```javascript
useEffect(() => {
  const interval = setInterval(async () => {
    const response = await fetch('/api/agentcore-metrics');
    const metrics = await response.json();
    setMetrics(metrics);
  }, 5000); // Poll every 5 seconds

  return () => clearInterval(interval);
}, []);
```

### Pattern 4: Elastic Observability Integration

**Setup:**
```bash
# Configure Elastic integration
# Automatically collects metrics and logs from CloudWatch
```

**Features:**
- Amazon Bedrock AgentCore integration
- End-to-end observability of agents and LLM interactions
- Combines platform-level insights from AgentCore
- Deep application-level visibility from OTEL traces

**Source:**
- [Troubleshooting with Elastic Observability](https://www.elastic.co/observability-labs/blog/llm-agentic-ai-observability-amazon-bedrock-agentcore)

---

## Event Types and Schemas

### Runtime Event Types

**Streaming Response Events:**
```
data: {"event": "partial response"}
```

**Event Structure (inferred from documentation):**
- May contain `"data"` field for data chunks
- May contain `"message"` field for message parts
- Supports JSON-RPC based request/response format

**Note:** AWS documentation does not provide explicit event schemas. Event structure is framework-specific (e.g., Strands, LangGraph).

### Observability Event Types

**CloudWatch Log Events:**
```json
{
  "timestamp": "2025-12-06T10:30:00.000Z",
  "level": "INFO",
  "sessionId": "user-123-session-456",
  "traceId": "1-5759e988-bd862e3fe1be46a994272793",
  "spanId": "53995c3f42cd8ad8",
  "message": "Tool invocation completed",
  "attributes": {
    "tool": "github_api",
    "duration_ms": 150,
    "tokens_used": 245
  }
}
```

**CloudWatch Metrics:**
| Metric Name | Dimensions | Unit | Description |
|-------------|-----------|------|-------------|
| `SessionCount` | AgentId, Endpoint | Count | Number of active sessions |
| `Latency` | AgentId, Endpoint | Milliseconds | Request latency |
| `TokenUsage` | AgentId, Model | Count | Tokens consumed |
| `ErrorRate` | AgentId, ErrorType | Count | Errors per minute |

**X-Ray Traces:**
- Distributed tracing format
- Traces span multiple services
- Subsegments for individual operations

---

## Integration Examples

### Example 1: Real-Time Agent Monitoring Dashboard

**Use Case:** Monitor multiple agents in production with live updates

**Stack:**
- API Gateway WebSocket API
- Lambda (Python)
- DynamoDB (connection management)
- CloudWatch Logs Subscription Filters
- React frontend

**Flow:**
1. Dashboard connects to API Gateway WebSocket
2. Lambda subscribes to CloudWatch Logs for agent log group
3. CloudWatch Subscription Filter streams logs to Lambda
4. Lambda aggregates metrics and broadcasts to dashboard clients
5. Dashboard displays real-time trace visualizations, error rates, token usage

### Example 2: Slack Bot with Agent Progress Updates

**Use Case:** Run long-running agent tasks and stream progress to Slack

**Implementation:**
```python
import boto3
import json
from slack_sdk import WebClient

agentcore = boto3.client('bedrock-agentcore')
slack_client = WebClient(token=os.environ['SLACK_TOKEN'])

def invoke_agent_with_slack_updates(channel_id, prompt):
    """Invoke agent and stream progress to Slack."""

    # Send initial message
    response = slack_client.chat_postMessage(
        channel=channel_id,
        text="Starting agent task...",
        thread_ts=None
    )
    thread_ts = response['ts']

    # Invoke agent with streaming
    agent_response = agentcore.invoke_agent_runtime(
        agentRuntimeArn='arn:aws:bedrock-agentcore:...',
        runtimeSessionId=f'slack-{channel_id}-{thread_ts}',
        payload=json.dumps({'prompt': prompt})
    )

    # Stream progress updates to Slack thread
    buffer = []
    for line in agent_response['response'].iter_lines():
        if line.startswith(b'data: '):
            event = line[6:].decode('utf-8')
            buffer.append(event)

            # Update Slack message every 5 events
            if len(buffer) >= 5:
                slack_client.chat_postMessage(
                    channel=channel_id,
                    text='\n'.join(buffer),
                    thread_ts=thread_ts
                )
                buffer = []

    # Final update
    if buffer:
        slack_client.chat_postMessage(
            channel=channel_id,
            text='\n'.join(buffer),
            thread_ts=thread_ts
        )
```

### Example 3: CloudWatch Alarms for Agent Failures

**Use Case:** Trigger alerts when agent error rate exceeds threshold

```python
import boto3

cloudwatch = boto3.client('cloudwatch')

# Create alarm for high error rate
cloudwatch.put_metric_alarm(
    AlarmName='AgentCore-HighErrorRate',
    ComparisonOperator='GreaterThanThreshold',
    EvaluationPeriods=2,
    MetricName='ErrorRate',
    Namespace='AWS/BedrockAgentCore',
    Period=300,
    Statistic='Sum',
    Threshold=10.0,
    ActionsEnabled=True,
    AlarmActions=[
        'arn:aws:sns:us-west-2:123456789012:agent-alerts'
    ],
    Dimensions=[
        {'Name': 'AgentId', 'Value': 'my-agent'}
    ]
)
```

---

## Limitations and Workarounds

### Limitation 1: No Built-in Webhooks

**Problem:** AgentCore does not support webhook callbacks for Runtime state changes.

**Workarounds:**
1. **CloudWatch Subscription Filters** - Stream logs to Lambda, implement custom webhook logic
2. **EventBridge Rules** - Trigger on CloudWatch alarms or metric thresholds
3. **Client Polling** - Periodically check session status via API

**Example (CloudWatch → Lambda → Webhook):**
```python
def cloudwatch_to_webhook(event):
    """Lambda triggered by CloudWatch Logs, sends webhook."""

    import requests

    # Parse CloudWatch Logs event
    log_data = json.loads(gzip.decompress(base64.b64decode(event['awslogs']['data'])))

    for log_event in log_data['logEvents']:
        message = json.loads(log_event['message'])

        if message.get('event_type') == 'session_complete':
            # Send webhook
            requests.post('https://my-app.com/webhooks/agent-complete', json={
                'sessionId': message['sessionId'],
                'status': 'completed',
                'timestamp': message['timestamp']
            })
```

### Limitation 2: No Direct OTEL Span Subscription

**Problem:** Cannot subscribe directly to OTEL spans; must go through CloudWatch.

**Workaround:**
1. Enable CloudWatch Transaction Search
2. Use CloudWatch Logs Subscription Filters on `aws/spans` log group
3. Stream to Kinesis or Lambda for processing

**Example:**
```bash
aws logs put-subscription-filter \
  --log-group-name aws/spans \
  --filter-name span-processor \
  --filter-pattern '' \
  --destination-arn arn:aws:kinesis:us-west-2:123456789012:stream/otel-spans
```

### Limitation 3: Event Schema Not Documented

**Problem:** AWS does not provide detailed event schemas for streaming responses.

**Workaround:**
- Event structure is framework-specific (Strands, LangGraph, etc.)
- Inspect events empirically during development
- Use agent framework's documentation for event schemas

### Limitation 4: CloudWatch Logs Lag

**Problem:** CloudWatch Logs may have 1-5 second lag for real-time use cases.

**Workarounds:**
1. Use **WebSocket streaming** for true real-time progress (no CloudWatch lag)
2. Use **HTTP streaming** from `InvokeAgentRuntime` for immediate client updates
3. CloudWatch Subscription Filters are suitable for **near real-time** (not sub-second)

### Limitation 5: Account-Level Subscription Filter Limit

**Problem:** Each AWS account can create **only one account-level subscription filter**.

**Workaround:**
- Use log group-level subscription filters (up to 2 per log group)
- Fan out from single Kinesis stream to multiple consumers
- Use Firehose for multiple destinations

**Source:**
- [Real-time processing with subscriptions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Subscriptions.html)

---

## Summary Table

| Question | Answer | Pattern |
|----------|--------|---------|
| **Built-in event streaming to external consumers?** | No | Use CloudWatch Subscription Filters |
| **Real-time progress updates from Runtime?** | Yes | HTTP streaming or WebSocket |
| **Webhook/callback for state changes?** | No | Implement via CloudWatch → Lambda → Webhook |
| **Subscribe to OTEL spans in real-time?** | Via CloudWatch | CloudWatch Transaction Search + Subscription Filters |
| **WebSocket hub for Runtime progress?** | Custom implementation | API Gateway WS + Lambda + DynamoDB |
| **Real-time dashboard examples?** | Yes | CloudWatch native, Grafana Cloud, custom WebSocket |

---

## Key Takeaways

1. **No Direct Webhooks** - AgentCore uses pull-based streaming (HTTP/WebSocket), not push-based webhooks
2. **CloudWatch as Hub** - All observability data flows through CloudWatch; use Subscription Filters for external streaming
3. **WebSocket for Real-Time** - Use `InvokeAgentRuntimeWithWebSocketStream` for true bidirectional real-time communication
4. **OTEL Compatibility** - Full OpenTelemetry support enables integration with existing observability stacks
5. **Dashboard Options** - Native CloudWatch, Grafana Cloud integration, or custom WebSocket-based dashboards

---

## Sources

- [Invoke an AgentCore Runtime agent](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)
- [Stream agent responses](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/response-streaming.html)
- [Get started with WebSocket streaming](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-websocket.html)
- [Amazon Bedrock AgentCore Runtime bi-directional streaming](https://aws.amazon.com/about-aws/whats-new/2025/12/bedrock-agentcore-runtime-bi-directional-streaming/)
- [Add observability to resources](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)
- [Observe agent applications](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)
- [Build trustworthy AI agents with observability](https://aws.amazon.com/blogs/machine-learning/build-trustworthy-ai-agents-with-amazon-bedrock-agentcore-observability/)
- [Monitor AI agent infrastructure in Grafana Cloud](https://grafana.com/blog/2025/11/28/how-to-monitor-amazon-bedrock-agentcore-ai-agent-infrastructure-in-grafana-cloud/)
- [Monitor AI agent applications in Grafana Cloud](https://grafana.com/blog/2025/11/26/how-to-monitor-ai-agent-applications-on-amazon-bedrock-agentcore-with-grafana-cloud/)
- [Troubleshooting with Elastic Observability](https://www.elastic.co/observability-labs/blog/llm-agentic-ai-observability-amazon-bedrock-agentcore)
- [Real-time processing with CloudWatch Logs subscriptions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Subscriptions.html)
- [Amazon Bedrock AgentCore - Amazon CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AgentCore-Agents.html)
- [How it works - Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
- [boto3 invoke_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore/client/invoke_agent_runtime.html)
