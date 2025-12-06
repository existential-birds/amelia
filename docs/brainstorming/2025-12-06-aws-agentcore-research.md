# AWS Bedrock AgentCore - Comprehensive Research

**Date:** 2025-12-06
**Purpose:** Deep dive research into AWS AgentCore capabilities, architecture, and integration patterns

## Executive Summary

Amazon Bedrock AgentCore is an enterprise-grade agentic platform for building, deploying, and operating AI agents securely at scale with zero infrastructure management. It's framework-agnostic (supports LangGraph, Strands, CrewAI, OpenAI SDK, Google ADK, etc.) and model-agnostic (works with Bedrock models, OpenAI, Gemini, Claude, etc.). The platform has been downloaded over 1 million times and is used by organizations including National Australia Bank, Sony, Thomson Reuters, and Experian.

**Key Differentiator:** AgentCore is designed specifically for production deployment with built-in security, observability, memory, tool integration, and quality evaluations - solving the "last mile" problem of moving agents from prototypes to production.

---

## Table of Contents

1. [Core Architecture](#core-architecture)
2. [AgentCore Runtime](#agentcore-runtime)
3. [AgentCore Gateway](#agentcore-gateway)
4. [AgentCore Memory](#agentcore-memory)
5. [AgentCore Code Interpreter](#agentcore-code-interpreter)
6. [AgentCore Browser](#agentcore-browser)
7. [AgentCore Identity](#agentcore-identity)
8. [AgentCore Observability](#agentcore-observability)
9. [AgentCore Evaluations](#agentcore-evaluations)
10. [Protocol Support (MCP & A2A)](#protocol-support-mcp--a2a)
11. [Deployment & Developer Experience](#deployment--developer-experience)
12. [Pricing & Availability](#pricing--availability)
13. [Integration Patterns](#integration-patterns)

---

## Core Architecture

### Framework-Agnostic Platform

AgentCore's most significant feature is its framework-agnostic approach. Organizations can choose which AgentCore services they need while using their preferred frameworks and models:

**Supported Frameworks:**
- LangGraph
- LangChain
- Strands Agents SDK
- CrewAI
- LlamaIndex
- OpenAI Agents SDK
- Google Agent Development Kit (ADK)
- Claude Agents SDK

**Supported Models:**
- Amazon Bedrock models (Nova, Claude, Llama, Mistral, etc.)
- OpenAI models
- Google Gemini
- Anthropic Claude (direct)
- Custom models

### Modular Service Architecture

AgentCore services are modular and composable - they can be used together or independently:

```
┌─────────────────────────────────────────────────┐
│           AgentCore Platform                    │
├─────────────────────────────────────────────────┤
│  Runtime       │ Serverless execution engine    │
│  Gateway       │ Tool & API integration         │
│  Memory        │ Short/long-term state          │
│  Code Interp.  │ Secure code execution          │
│  Browser       │ Web interaction automation     │
│  Identity      │ Auth & credential management   │
│  Observability │ Monitoring & tracing           │
│  Evaluations   │ Quality & safety metrics       │
└─────────────────────────────────────────────────┘
```

---

## AgentCore Runtime

### Overview

AgentCore Runtime is a secure, serverless execution environment specifically designed for AI agents - similar to AWS Lambda but optimized for the dynamic, long-running nature of agentic workloads.

### Key Capabilities

**Execution Model:**
- Serverless, fully managed compute
- Supports workloads up to 8 hours (longest in the industry)
- Complete session isolation for security
- Auto-scaling based on demand
- Container and direct code deployment options

**Protocol Support:**
- MCP (Model Context Protocol) servers
- A2A (Agent-to-Agent) protocol
- Standard HTTP/REST APIs

**Deployment Options:**
- Direct code upload (Python packages up to 100MB)
- Container images (via Amazon ECR)
- Infrastructure as Code (Terraform or CDK)

### Container Deployment

```bash
# Auto-creates IAM execution roles
# Auto-creates ECR repositories
# Consolidates Python code into zip/container
# Configures CloudWatch logging
agentcore deploy
```

### Invocation

**API/SDK:**
```bash
# AWS SDK InvokeAgentRuntime operation
agentcore invoke '{"prompt": "tell me a joke"}'
```

**Request Parameters:**
- Agent Runtime ARN (unique identifier)
- Qualifier (version number or endpoint name)
- MIME type (e.g., application/json)
- Payload (up to 100 MB)
- Optional bearer token for OAuth

**Response:**
- Streaming response delivering chunks in real-time
- Ideal for interactive applications
- Supports partial results immediately

### Permissions

Required IAM permissions:
- `bedrock-agentcore:InvokeAgentRuntime`
- `bedrock-agentcore:InvokeAgentRuntimeForUser` (if invoking on behalf of user)

### Error Handling

- `ResourceNotFoundException` - Agent ARN not found
- `AccessDeniedException` - Missing permissions
- `ThrottlingException` - Rate limit exceeded (implement exponential backoff)

---

## AgentCore Gateway

### Overview

AgentCore Gateway provides a secure, managed service for building, deploying, and connecting AI agent tools at scale. It transforms existing APIs, Lambda functions, and services into agent-ready tools with a unified MCP endpoint.

### Key Features

**Tool Integration:**
- Converts OpenAPI specs to agent tools (zero-code)
- Wraps AWS Lambda functions as tools
- Supports Smithy definitions
- Pre-integrated tools: Salesforce, Slack, Jira, Asana, Zendesk (1-click)
- Connects to existing MCP servers

**Security:**
- Security Guard manages OAuth authorization
- Verifies agent and user identity (ingress authentication)
- Connects to tools with different auth (egress authentication)
- OAuth flows, token refresh, secure credential storage
- Secure credential exchange/injection

**Protocol Translation:**
- Converts agent requests (MCP protocol) to API requests
- Converts to Lambda invocations
- Composition: combines multiple APIs/functions into single MCP endpoint

**Tool Discovery:**
- Semantic tool selection
- Agents search and discover appropriate tools based on task context
- Handles thousands of tools while minimizing prompt size and latency

### Framework Compatibility

Works with any framework:
- CrewAI
- LangGraph
- LlamaIndex
- Strands Agents
- Any model

### Infrastructure

- Fully serverless and auto-scaling
- Built-in observability (monitoring, auditing, troubleshooting)
- Unified access through single secure endpoint
- Eliminates weeks of custom development
- No complex protocol integration or version management needed

### MCP Inspector

Developer tool for testing and debugging MCP servers through an interactive interface. Connect your AgentCore gateway to the MCP inspector to debug gateway targets.

### Pricing

$0.005 per 1,000 tool API invocations

---

## AgentCore Memory

### Overview

AgentCore Memory is a fully managed service that enables AI agents to remember past interactions, providing context-aware and personalized conversations without requiring agents to build or manage complex infrastructure.

### Memory Types

**1. Short-Term Memory**
- Captures turn-by-turn interactions within a single session
- Maintains immediate context without requiring users to repeat information
- Example: Understanding "tomorrow" refers back to previously mentioned "Seattle" in weather context
- **Pricing:** $0.25 per 1,000 raw events created

**2. Long-Term Memory**
- Automatically extracts and stores key insights across multiple sessions
- Retains user preferences, important facts, and session summaries
- Enables persistent knowledge retention
- Example: Remembering customer preference for window seats across future booking sessions
- **Pricing:** Based on memories processed/stored per month + retrieval calls

### Key Benefits

1. **Natural Conversations** - Understands context and resolves ambiguous statements
2. **Personalized Experiences** - Retains user preferences and historical data across sessions
3. **Reduced Complexity** - Offloads state management, allowing focus on core business logic

### Common Use Cases

- **Conversational agents:** Customer support with interaction history
- **Task-oriented agents:** Multi-step workflows (e.g., invoice approval tracking)
- **Multi-agent systems:** Shared memory for supply chain coordination
- **Autonomous agents:** Route planning and learning from past experiences

### Storage & Integration

- Stored in managed AWS infrastructure
- OpenTelemetry-compatible for spans and log data (when enabled)
- SDK support across various agent frameworks

---

## AgentCore Code Interpreter

### Overview

AgentCore Code Interpreter enables AI agents to write, execute, and debug code securely in isolated sandbox environments. It bridges natural language understanding with computational execution.

### Security & Isolation

- Runs in containerized environments within Amazon Bedrock AgentCore
- Complete isolation from other workloads and AWS infrastructure
- CloudTrail logging for audit and compliance
- Customizable security properties and network modes

### Supported Languages

- Python
- JavaScript
- TypeScript
- Pre-built runtimes with common libraries pre-installed

### File Operations & Size Limits

| Operation | File Size Limit |
|-----------|-----------------|
| Inline Upload | Up to 100 MB |
| Amazon S3 Upload (via terminal) | Up to 5 GB |
| Large Dataset Processing | Gigabyte-scale data |

### Network Modes

**Sandbox Mode (Most Secure):**
- Isolated environment with no external network access
- No access to AWS services or external APIs
- Best for sensitive computations

**Public Network Mode:**
- Allows access to public internet resources
- Can connect to external APIs
- Advanced use cases

### Execution Parameters

- **Default Duration:** 15 minutes
- **Maximum Duration:** 8 hours
- **Supported Data Formats:** CSV, Excel, JSON, structured data
- **Pricing:** Per second, based on CPU and memory usage

### Active Resource Consumption Pricing

**Cost Optimization:**
- I/O wait and idle time is FREE (if no background process running)
- Only charged for actual CPU consumption
- Memory charged for peak consumed per second
- Delivers 30-70% cost savings (agents spend this much time in I/O wait)

### Best Practices

```python
# Use context managers for proper cleanup
with code_session:
    # Keep snippets concise and focused
    result = perform_specific_task()

    # Save intermediate results
    save_checkpoint(result)

# Include error handling
try:
    execute_operation()
except Exception as e:
    handle_error(e)

# Clean up resources
close_session()
```

### Development Guidelines

- Write concise, focused code snippets
- Use comments for documentation
- Optimize for performance with large datasets
- Include try/except blocks
- Stream code execution results
- Clean temporary files
- Close sessions when complete

---

## AgentCore Browser

### Overview

AgentCore Browser is a secure, cloud-based browser environment that enables AI agents to interact with websites in isolated, containerized environments.

### Core Capabilities

**Web Interaction:**
- Navigate websites
- Fill forms and click buttons
- Parse dynamic web content
- Take screenshots for visual understanding
- Automate form submissions and data entry
- Extract data from websites
- Perform e-commerce transactions

**Infrastructure:**
- Serverless and automatically scales
- Isolated sessions (containerized per tool)
- Multiple active sessions support
- Session timeouts (default 15 min, max 8 hours)

### API Endpoints

**1. Automation Endpoint (WebSocket-based):**
- Agent-driven actions
- Navigate, click, fill forms, take screenshots

**2. Live View Endpoint (WebSocket-based):**
- Real-time human monitoring
- Direct user interaction capabilities

### Supported Libraries

- Strands
- Nova Act
- Playwright

### Security Features

| Feature | Details |
|---------|---------|
| Isolation | Containerized environment, separate from local system |
| Ephemeral Sessions | Temporary sessions that reset after use |
| Session Timeouts | Automatic termination (default 15 min, max 8 hours) |
| CloudTrail Logging | Audit trail of activities |
| Session Recording | Optional recording for custom browsers, stored in S3 |

### Browser Types

**AWS Managed Browser:**
- Quick setup: `aws.browser.v1`
- Pre-configured with security defaults

**Custom Browser:**
- Session recording enabled
- Custom network settings
- Specific IAM execution roles

### Observability & Monitoring

- **Live Viewing:** Real-time session monitoring
- **Session Replay:** Comprehensive interaction history playback
- **CloudWatch Metrics:** Performance tracking per tool
- **Detailed Logging:** DOM changes, user actions, console logs, network events

### Common Use Cases

- Test web applications securely
- Automate web workflows
- Monitor website changes
- Build AI agents for web navigation
- Perform e-commerce transactions
- Extract and process online information

### Pricing

Per second, based on CPU and memory usage

---

## AgentCore Identity

### Overview

AgentCore Identity is an identity and credential management service designed specifically for AI agents and automated workloads. It provides secure authentication, authorization, and credential management for agents accessing AWS resources and third-party services.

### Workload Identity Approach

Agent identities are implemented as **workload identities** - making agents first-class citizens in your security architecture. Each agent receives a unique identity with associated metadata:
- Name
- Amazon Resource Name (ARN)
- OAuth return URLs
- Created time
- Last updated time

### Key Components

**1. Agent Identity Directory**
- Create, manage, and organize agent and workload identities
- Unified directory service
- Single source of truth for agent identities within organization
- Centrally managed across all agents

**2. Agent Authorizer**
- Validates whether a user or service is allowed to invoke an agent
- Explicit verification for each access attempt
- Zero-trust security model

**3. Token Vault**
- Secure storage for OAuth 2.0 tokens
- OAuth client credentials
- API keys
- Comprehensive encryption at rest and in transit

### Workload Access Tokens

**Security Features:**
- Runtime-managed agent identities cannot retrieve tokens directly
- Prevents token extraction and misuse
- Tokens contain both user identity AND agent identity information
- Secure credential access patterns
- Auto-created when creating a runtime

### OAuth 2.0 Support

**Built-in Providers:**
- Google
- GitHub
- Slack
- Salesforce
- Atlassian (Jira)

**Pre-filled Configuration:**
- Authorization server endpoints
- Provider-specific parameters
- Reduces development effort

**Standard OAuth 2.0 Flows:**
- Sigv4 support
- API key management
- Seamless integration with AWS and third-party services

### Authentication Modes

**Inbound Auth:**
- Verifies agent identity when invoked
- User authentication via bearer tokens
- Cannot use AWS SDK if integrating OAuth (must use HTTPS)

**Outbound Auth:**
- Connects agents to tools with different auth requirements
- Secure credential injection
- Token refresh management

### Enterprise Security Features

- Complete session isolation
- Amazon VPC connectivity
- AWS PrivateLink support
- Comprehensive access controls
- Enterprise-grade reliability and security at scale

### Pricing

Billing is calculated per successful OAuth token or API key requested to perform a task requiring authorization for a non-AWS resource. No additional charges when using AgentCore Identity through AgentCore Runtime or AgentCore Gateway.

---

## AgentCore Observability

### Overview

AgentCore Observability provides comprehensive tracing, debugging, and monitoring capabilities for AI agents in production environments with real-time visibility into operational performance.

### Core Observability Capabilities

**1. Trace & Debug**
- Detailed visualizations of each step in agent workflow
- Execution path inspection
- Audit intermediate outputs and execution flow
- Debug bottlenecks and failures in real-time

**2. Metrics & Telemetry**
Built-in metrics (enabled by default):
- Session count
- Latency & duration
- Token usage
- Error rates
- Custom runtime metrics

**3. OpenTelemetry (OTEL) Integration**
- Standardized OTEL-compatible format
- Enables integration with existing monitoring stacks
- Spans and log data for memory resources (when enabled)
- Support for custom instrumentation

### Data Model

**Sessions:**
- Represents complete interaction context between user and agent
- Encapsulates entire conversation/interaction flow
- Maintains state and context across multiple exchanges
- Unique identifier per session
- Captures full lifecycle of user engagement

**Traces:**
- Detailed record of single request-response cycle
- Begins with agent invocation
- May include additional calls to other agents
- Captures complete execution path
- Internal processing steps, external service calls, decision points
- Resource utilization tracking

**Spans:**
- Discrete, measurable unit of work within execution flow
- Fine-grained operations during request processing
- Defined start and end time
- Precise timeline of agent activities and durations

### CloudWatch Integration

**Automatic Storage:**
- All metrics, spans, and logs stored in Amazon CloudWatch
- Viewable via CloudWatch console
- Downloadable using AWS CLI/SDKs

**Observability Dashboard:**
- Trace visualizations
- Custom span metric graphs
- Error breakdowns
- Runtime data analysis

### Monitoring Capabilities

- Rich metadata tagging and filtering
- Simplifies issue investigation at scale
- Large-scale quality assurance support
- Custom metrics for domain-specific monitoring

### Implementation

**AWS Distro for Open Telemetry (ADOT):**
- Instrument code using ADOT SDK
- Framework-specific configuration (e.g., Strands tracer object)
- Emit Open Telemetry logs and traces

### Third-Party Integrations

**Grafana Cloud:**
- Full integration with Grafana Cloud dashboards
- Monitor AI agent infrastructure
- Monitor AI agent applications
- Industry-standard observability framework

### Real-World Results

**Grupo Elfa (Brazilian distributor/retailer):**
- Complete audit traceability
- Real-time metrics of agents
- Transformed reactive to proactive operations
- 100% traceability of agent decisions and interactions
- 50% reduction in problem resolution time
- Handles thousands of daily price quotes

---

## AgentCore Evaluations

### Overview

AgentCore Evaluations is a fully managed service that helps continuously monitor and analyze agent performance based on real-world behavior, improving quality and catching issues before they cause widespread customer impact.

### Key Capabilities

**Pre-Deployment Testing:**
- Check agents against baseline before deployment
- Stop faulty versions from reaching users
- CI/CD pipeline integration

**Production Monitoring:**
- Continuous improvement of agents
- Real-world behavior analysis
- Catch issues before customer impact

### Evaluation Modes

**1. Online Evaluations:**
- Continuous production monitoring
- Real-time quality assessment
- Automatic evaluation as sessions complete

**2. On-Demand Evaluations:**
- CI/CD pipeline integration
- Pre-deployment quality gates
- Baseline comparisons

### Built-in Quality Metrics (13 Total)

**Correctness & Accuracy:**
- **Correctness:** Factual accuracy of information in response
- **Faithfulness:** Information supported by provided context/sources
- **Context Relevance:** Retrieved context matches user query
- **Tool Selection Accuracy:** Appropriate tool selection for task

**Helpfulness & Quality:**
- **Helpfulness:** Usefulness and value from user's perspective
- **Goal Success Rate:** Task completion effectiveness

**Safety & Ethics:**
- **Harmfulness:** Detection of harmful content
- **Stereotyping:** Generalizations about individuals/groups
- Other safety dimensions

### Custom Evaluators

**Business-Specific Metrics:**
- Define custom quality metrics for unique requirements
- Provide model to use as judge
- Configure inference parameters (temperature, max output tokens)
- Tailored prompt with judging instructions

**Evaluation Scope:**
- Single traces
- Full sessions
- Per tool call

**Scale Configuration:**
- Numeric values
- Custom text labels

### LLM-as-a-Judge Technique

Traces from agents converted to unified format and scored using LLM-as-a-Judge for both built-in and custom evaluators.

### Framework Integration

**Supported Frameworks:**
- Strands
- LangGraph
- OpenTelemetry instrumentation libraries
- OpenInference instrumentation libraries

### Monitoring Dashboard

**CloudWatch Integration:**
- Key operational metrics (token usage, latency, session duration, error rates)
- Continuous quality evaluation
- Critical criteria dashboards (correctness, helpfulness, safety, goal success)

### Automatic Evaluation

Every time you invoke an agent deployed on AgentCore Runtime:
1. Seamlessly transmits traces to AgentCore Observability
2. AgentCore Evaluations reads traces as session completes
3. Evaluates session, trace, or span with chosen metric
4. No manual intervention required

### Availability

Available in preview in four AWS Regions:
- US East (N. Virginia)
- US West (Oregon)
- Asia Pacific (Sydney)
- Europe (Frankfurt)

---

## Protocol Support (MCP & A2A)

### Model Context Protocol (MCP)

**Overview:**
MCP provides a standardized way for agents to discover and invoke tools. AgentCore Gateway implements MCP, making it compatible with MCP clients.

**MCP Server Deployment:**
- Deploy and run MCP servers in AgentCore Runtime
- Create, test, and deploy MCP servers
- AgentCore Runtime supports MCP server hosting

**MCP Tools:**
- Zero-code MCP tool creation from APIs and AWS Lambda functions
- Intelligent tool discovery through semantic search
- Built-in inbound and outbound authorization
- Serverless infrastructure for MCP servers

**MCP vs A2A:**
- **MCP:** Connects a single agent to its tools and data (agent-to-resource)
- **A2A:** Lets multiple agents coordinate with each other (agent-to-agent)

**Example:** A retail inventory agent uses MCP to query product databases, then uses A2A to communicate with external supplier agents to place orders.

### Agent-to-Agent (A2A) Protocol

**Overview:**
A2A enables multiple agents to discover peers, share capabilities, and coordinate actions across platforms using standardized communication.

**Framework Interoperability:**
Agents built using different frameworks can share context:
- Strands Agents
- OpenAI Agents SDK
- LangGraph
- Google ADK
- Claude Agents SDK

**Key Features:**
- Loose coupling and modularity
- Each agent operates as independent unit
- Develop, test, deploy, upgrade individual agents independently
- No disruption to broader system
- New specialized agents can join existing deployments
- Agent failures isolated within well-defined boundaries

**Technical Implementation:**

When configured for A2A, AgentCore expects:
- Stateless, streamable HTTP servers on port 9000
- Root path: 0.0.0.0:9000/
- Aligns with default A2A server configuration

**Standard A2A Features:**
- Built-in agent discovery via Agent Cards at `/.well-known/agent-card.json`
- JSON-RPC communication
- Enterprise authentication (SigV4/OAuth 2.0)
- Auto-scaling and serverless deployment

**A2A Ecosystem:**
- Backed by 50+ technology companies
- Google, Atlassian, Confluent, Salesforce, SAP, MongoDB

**Real-World Example:**
AWS monitoring and incident response:
- Google ADK-based orchestrator
- Coordinates with Strands and OpenAI SDK agents
- All deployed on AgentCore Runtime
- Working together to detect issues, search solutions, recommend fixes

### Amazon Bedrock AgentCore MCP Server

**Purpose:**
Transform, deploy, and test AgentCore-compatible agents directly from development environment.

**Features:**
- Built-in support for runtime integration
- Gateway connectivity
- Agent lifecycle management
- Simplifies local development to production deployment

**Compatible MCP Clients:**
- Kiro
- Cursor
- Claude Code
- Amazon Q CLI

**Installation:**
```json
{
  "mcpServers": {
    "bedrock-agentcore-mcp-server": {
      "command": "uvx",
      "args": ["awslabs.amazon-bedrock-agentcore-mcp-server@latest"],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

**Capabilities:**
- Conversational commands to automate complex agent workflows
- Access to comprehensive AgentCore documentation
- Coverage of Runtime, Memory, Code Interpreter, Browser, Gateway, Observability, Identity

**Availability:**
Open-source MCP server available globally via GitHub

---

## Deployment & Developer Experience

### AgentCore Starter Toolkit

**Installation:**
```bash
# Install via pip
pip install bedrock-agentcore-starter-toolkit

# Or via uv (recommended)
uv pip install bedrock-agentcore-starter-toolkit

# Requirements
# Python 3.10 or newer
python3 --version
```

**Latest Version:** v0.1.32

### Workflow Commands

**Step 0: Install CLI**
```bash
pip install bedrock-agentcore-starter-toolkit
```

**Step 1: Create Agent**
```bash
agentcore create
```

**Interactive Bootstrapping:**
- Choose framework: Strands Agents, LangGraph, OpenAI Agents SDK, Google ADK
- Choose model provider: Amazon Bedrock, OpenAI, Google Gemini, Anthropic Claude, Amazon Nova, Meta Llama, Mistral
- Choose output: Python project folder, or Infrastructure as Code (Terraform or CDK)

**Auto-configuration:**
- Gateway integration
- Memory setup
- Observability enabled
- IAM role configuration
- Entrypoint definition
- Requirements specification
- Auth model configuration

**Step 2: Local Development (Optional)**
```bash
agentcore dev
agentcore invoke --dev "Hello!"
```

**Step 3: Deploy Agent**
```bash
agentcore deploy
```

**Deployment Process:**
- Consolidates Python code into zip file or container
- Deploys to AgentCore Runtime
- Configures CloudWatch logging
- Auto-creates IAM execution roles
- Auto-creates ECR repositories (for containers)

**Step 4: Invoke Agent**
```bash
agentcore invoke '{"prompt": "tell me a joke"}'
```

### CLI Features

**Core Capabilities:**
- **Deployment:** Direct code deploy or containerization for complex scenarios
- **Import Agent:** Migrate existing Bedrock Agents to AgentCore with framework conversion
- **Gateway Integration:** Transform existing APIs into agent tools
- **Configuration Management:** Profile-based configuration
- **Observability:** Built-in monitoring setup

### Import Agent Capability

**Seamless Migration:**
- Migrate existing Amazon Bedrock Agents to LangChain/LangGraph or Strands frameworks
- Automatically integrates AgentCore primitives (Memory, Code Interpreter, Gateway)
- Migration in minutes with full feature parity
- Deploy directly to AgentCore Runtime for serverless operation

### Deployment Options

**Direct Code Upload:**
- Python packages up to 100 MB
- Automatic zip file creation
- Quick deployment for simple agents

**Container Deployment:**
- Complex scenarios requiring custom dependencies
- Docker/ECR integration
- Full control over runtime environment
- Swisscom example: containerized agents with AgentCore Runtime for scalable hosting

**Infrastructure as Code:**
- Terraform templates
- CDK (Cloud Development Kit) templates
- Version control friendly
- Reproducible deployments

### Framework Templates

**Strands Agents:**
- AWS-native framework
- Built-in observability support
- Tracer object configuration for OTEL logs

**LangGraph:**
- StateGraph abstraction
- Graph-based orchestration
- Define nodes representing reasoning steps
- Multi-agent systems support

**OpenAI Agents SDK:**
- OpenAI-native framework
- Direct integration with OpenAI models
- A2A protocol support

**Google ADK:**
- Google Agent Development Kit
- Gemini model optimization
- A2A protocol support

---

## Pricing & Availability

### Pricing Model

**Consumption-Based Pricing:**
- No upfront costs
- No minimum fees
- No upfront commitments
- Pay only for what you use

### Service-Specific Pricing

**Runtime, Browser, Code Interpreter:**
- Per second billing
- Based on CPU and memory usage
- Active resource consumption model
- I/O wait and idle time FREE (if no background process)
- 30-70% cost savings for typical agentic workloads

**Gateway:**
- $0.005 per 1,000 tool API invocations
- Predictable costs for tool usage

**Memory:**
- Short-term memory: $0.25 per 1,000 raw events created
- Long-term memory: Based on memories processed/stored per month + retrieval calls

**Identity:**
- Per successful OAuth token or API key requested
- Only for non-AWS resource authorization
- No additional charges when used through Runtime or Gateway

### Storage Costs (Separate Billing)

**Container Deployment:**
- ECR storage costs (standard ECR rates)

**Direct Code Deployment:**
- S3 Standard storage rates (starting February 27, 2026)

**Network Transfer:**
- Standard EC2 data transfer rates

### Free Trial

You can try AgentCore services at no charge until September 16, 2025. Starting September 17, 2025, AWS will bill for AgentCore service usage.

### Cost Optimization Tips

**1. Tool Use Management:**
- Unbounded tool use per turn can triple per-request cost
- Enforce a step budget to limit tool calls

**2. Caching:**
- Cache the agent plan when possible
- Cache retrieval results
- Avoid repeated expensive steps

**3. Resource Optimization:**
- Optimize code execution to minimize CPU time
- Clean up sessions promptly
- Use appropriate memory allocation

### Regional Availability

**Generally Available:**
- US East (N. Virginia)
- US East (Ohio)
- US West (Oregon)
- Asia Pacific (Mumbai)
- Asia Pacific (Singapore)
- Asia Pacific (Sydney)
- Asia Pacific (Tokyo)
- Europe (Frankfurt)
- Europe (Ireland)

**Preview (Evaluations & Policy):**
- US East (N. Virginia)
- US West (Oregon)
- Asia Pacific (Sydney)
- Europe (Frankfurt)

---

## Integration Patterns

### Multi-Agent Orchestration

**Pattern: Coordinator-Worker**
```
┌─────────────┐
│ Orchestrator│ (Google ADK)
└──────┬──────┘
       │ A2A Protocol
       ├────────────┬────────────┐
       │            │            │
   ┌───▼───┐   ┌───▼───┐   ┌───▼───┐
   │Strands│   │OpenAI │   │Claude │
   │ Agent │   │ Agent │   │ Agent │
   └───────┘   └───────┘   └───────┘
```

**Use Case:** AWS monitoring and incident response
- Orchestrator coordinates detection, search, recommendation
- Each agent uses different framework
- All deployed on AgentCore Runtime
- Communication via A2A protocol

### Tool Integration via Gateway

**Pattern: API-to-Tool**
```
┌──────────┐
│  Agent   │
└────┬─────┘
     │ MCP
┌────▼─────────────┐
│ AgentCore Gateway│
└────┬─────────────┘
     │
     ├─ OpenAPI Specs → Tools
     ├─ Lambda Functions → Tools
     ├─ Pre-integrated (Slack, Jira, etc.)
     └─ Custom MCP Servers
```

**Benefits:**
- Zero-code tool creation
- Semantic tool discovery
- Unified security model
- Handles thousands of tools efficiently

### Memory-Enhanced Agents

**Pattern: Stateful Conversation**
```
┌──────────┐
│  Agent   │
└────┬─────┘
     │
┌────▼──────────────┐
│ AgentCore Memory  │
├───────────────────┤
│ Short-term Memory │ (Session context)
│ Long-term Memory  │ (User preferences)
└───────────────────┘
```

**Use Case:** Customer support agent
- Maintains conversation context within session
- Remembers customer preferences across sessions
- No infrastructure management required

### Code Execution Pattern

**Pattern: Agentic Data Analysis**
```
┌──────────┐
│  Agent   │
└────┬─────┘
     │
┌────▼──────────────────┐
│ Code Interpreter      │
├───────────────────────┤
│ • Python/JS/TS        │
│ • Sandbox isolation   │
│ • S3 integration (5GB)│
│ • Network modes       │
└───────────────────────┘
```

**Use Case:** Data analysis agent
- Agent generates Python code for analysis
- Executes in isolated sandbox
- Processes large datasets from S3
- Returns results to agent for interpretation

### Web Automation Pattern

**Pattern: Browser-Based Tasks**
```
┌──────────┐
│  Agent   │
└────┬─────┘
     │
┌────▼──────────────────┐
│ AgentCore Browser     │
├───────────────────────┤
│ • WebSocket endpoints │
│ • Playwright support  │
│ • Session recording   │
│ • Live viewing        │
└───────────────────────┘
```

**Use Case:** E-commerce automation
- Navigate product pages
- Fill order forms
- Complete transactions
- Extract confirmation data

### Full-Stack Agentic Application

**Pattern: Production-Grade Deployment**
```
┌────────────────────────────────────┐
│         User Application           │
└────────────┬───────────────────────┘
             │
┌────────────▼───────────────────────┐
│      AgentCore Runtime             │
│  ┌──────────────────────────────┐  │
│  │         Agent Code           │  │
│  │  (LangGraph/Strands/etc)     │  │
│  └───┬──────────────────────┬───┘  │
│      │                      │      │
│  ┌───▼────┐            ┌────▼───┐  │
│  │Gateway │            │ Memory │  │
│  └───┬────┘            └────┬───┘  │
│      │                      │      │
│  ┌───▼──────────────────────▼───┐  │
│  │    Identity (OAuth/Tokens)   │  │
│  └───┬──────────────────────────┘  │
│      │                             │
│  ┌───▼──────────────────────────┐  │
│  │  Observability (OTEL/CW)     │  │
│  └──────────────────────────────┘  │
└────────────────────────────────────┘
```

**Includes:**
- Serverless runtime (up to 8 hours)
- Gateway for tool integration
- Memory for state management
- Identity for secure auth
- Observability for monitoring
- Evaluations for quality assurance

### Enterprise Integration Pattern

**Pattern: VPC-Isolated Deployment**
```
┌─────────────────────────────────┐
│     Amazon VPC                  │
│  ┌───────────────────────────┐  │
│  │   AgentCore Runtime       │  │
│  │   (PrivateLink enabled)   │  │
│  └────────┬──────────────────┘  │
│           │                     │
│  ┌────────▼──────────────────┐  │
│  │  Internal APIs/Databases  │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

**Enterprise Features:**
- Complete session isolation
- VPC connectivity
- AWS PrivateLink support
- Comprehensive access controls
- CloudTrail audit logging

---

## Key Differentiators vs. Other Platforms

### vs. Self-Hosting

**AgentCore Advantages:**
- Zero infrastructure management
- Auto-scaling and serverless
- Built-in security and compliance
- Managed observability
- Pay-per-use pricing
- 8-hour max session (industry longest)

**When Self-Hosting Wins:**
- Complete control over environment
- Specific compliance requirements
- Unlimited session duration needs
- Cost optimization at massive scale

### vs. LangSmith/LangChain Cloud

**AgentCore Advantages:**
- Framework-agnostic (not just LangChain)
- Integrated runtime + tools + memory + identity
- AWS-native integration (Bedrock, S3, Lambda)
- Enterprise security features (VPC, PrivateLink)
- A2A protocol support for multi-agent

**LangSmith Advantages:**
- Deep LangChain integration
- Advanced debugging UI
- Prompt engineering tools

### vs. Custom AWS Lambda Deployment

**AgentCore Advantages:**
- Optimized for long-running agents (8 hours vs. 15 min)
- Built-in memory management
- Tool integration via Gateway
- Quality evaluations built-in
- Agent-specific observability
- Workload identity management

**Lambda Advantages:**
- More flexible compute options
- Lower cost for short executions
- Broader language support

---

## Adoption & Case Studies

### Downloads & Users

- **1+ million downloads** of AgentCore SDK
- Customers across multiple industries and sizes

### Notable Adopters

**Financial Services:**
- Clearwater Analytics (CWAN)
- National Australia Bank

**Technology:**
- Sony
- Ericsson
- Heroku
- Thomson Reuters

**Enterprise:**
- Cox Automotive
- Druva
- Experian

**Telecommunications:**
- Swisscom (Switzerland's leading telecoms provider)
  - Selected AgentCore for containerized agents
  - AgentCore Runtime for scalable hosting

**Retail/Distribution:**
- Grupo Elfa (Brazilian distributor and retailer)
  - Complete audit traceability
  - Real-time agent metrics
  - 100% traceability of agent decisions
  - 50% reduction in problem resolution time
  - Handles thousands of daily price quotes

### Partner Ecosystem

**Consulting Partners:**
- Accenture
- Deloitte

**Technology Partners:**
- Cisco
- Salesforce

**A2A Ecosystem (50+ companies):**
- Google
- Atlassian
- Confluent
- SAP
- MongoDB

---

## API Reference Summary

### Primary APIs

**InvokeAgentRuntime:**
- Sends request to agent/tool in AgentCore Runtime
- Returns streaming response
- Supports up to 100 MB payload
- Real-time chunk delivery

**GetWorkloadAccessToken:**
- Retrieves workload access tokens
- For JWT-based authentication
- For user-specific tokens

**Bedrock Model Invocation:**
- InvokeModel
- InvokeModelWithResponseStream
- Access to foundation models

### CLI Commands

```bash
# Agent lifecycle
agentcore create              # Bootstrap new agent
agentcore dev                 # Local development server
agentcore deploy              # Deploy to AgentCore Runtime
agentcore invoke              # Invoke deployed agent

# Import existing agents
agentcore import-agent        # Migrate Bedrock Agents

# Configuration
agentcore config              # Manage configuration
```

### IAM Permissions Summary

**User Permissions:**
- `bedrock-agentcore:InvokeAgentRuntime`
- `bedrock-agentcore:InvokeAgentRuntimeForUser`
- `bedrock-agentcore:GetWorkloadAccessToken`
- IAM role management
- CodeBuild project access
- S3 access for artifacts
- ECR repository access
- CloudWatch Logs access

**Execution Role:**
- ECR image access
- CloudWatch Logs (create/write)
- X-Ray tracing
- Bedrock model invocation
- Workload identity token access

---

## Future Considerations for Amelia Integration

### Potential Integration Points

**1. Runtime as Alternative to Local Execution**
- Deploy Amelia agents to AgentCore Runtime
- Leverage 8-hour session support for long-running tasks
- Benefit from auto-scaling for concurrent reviews

**2. Gateway for Tool Integration**
- Use Gateway to expose GitHub API, Jira API, Git operations as agent tools
- Semantic tool discovery for dynamic tool selection
- OAuth integration for secure API access

**3. Memory for State Management**
- Replace custom ExecutionState with AgentCore Memory
- Long-term memory for learning from past PR reviews
- Short-term memory for multi-turn review conversations

**4. Observability Integration**
- Emit OpenTelemetry traces from Amelia agents
- Integrate with AgentCore Observability for unified monitoring
- CloudWatch dashboards for Amelia performance metrics

**5. Evaluations for Quality Assurance**
- Custom evaluators for code review quality
- Monitor architect planning accuracy
- Track developer implementation success rates
- Measure reviewer feedback quality

**6. Identity for Multi-User Support**
- Workload identity per Amelia agent (Architect, Developer, Reviewer)
- OAuth integration for GitHub/Jira user authentication
- Secure credential management

### Architecture Pattern

```
┌────────────────────────────────────┐
│         Amelia CLI                 │
└────────────┬───────────────────────┘
             │
┌────────────▼───────────────────────┐
│      AgentCore Runtime             │
│  ┌──────────────────────────────┐  │
│  │   LangGraph State Machine    │  │
│  │   (Amelia Orchestrator)      │  │
│  └───┬──────────────────────┬───┘  │
│      │                      │      │
│  ┌───▼────┐            ┌────▼───┐  │
│  │Gateway │────────────│ Memory │  │
│  │(GitHub │            │(TaskDAG│  │
│  │ Jira) │            │  State)│  │
│  └───┬────┘            └────┬───┘  │
│      │                      │      │
│  ┌───▼──────────────────────▼───┐  │
│  │    Identity (User Auth)      │  │
│  └───┬──────────────────────────┘  │
│      │                             │
│  ┌───▼──────────────────────────┐  │
│  │  Observability + Evaluations │  │
│  │  (Quality Metrics)           │  │
│  └──────────────────────────────┘  │
└────────────────────────────────────┘
```

### Migration Path

**Phase 1: Observability**
- Emit OTEL traces from current Amelia agents
- Integrate with CloudWatch for monitoring
- No architectural changes required

**Phase 2: Gateway Integration**
- Move GitHub/Jira API calls to Gateway tools
- OAuth authentication via AgentCore Identity
- Maintain existing agent logic

**Phase 3: Memory Migration**
- Migrate ExecutionState to AgentCore Memory
- Use short-term memory for orchestrator state
- Use long-term memory for learned patterns

**Phase 4: Runtime Deployment**
- Deploy agents to AgentCore Runtime
- Leverage auto-scaling and session isolation
- Maintain CLI for local development

**Phase 5: Evaluations**
- Define custom evaluators for code review quality
- Continuous quality monitoring in production
- Feedback loop for agent improvement

### Risks & Considerations

**Vendor Lock-in:**
- AWS-specific platform
- Migration effort if switching providers

**Cost:**
- Consumption-based pricing may be higher than self-hosting at scale
- Need to monitor costs carefully

**Framework Constraints:**
- LangGraph well-supported, but need to verify compatibility
- Pydantic-AI driver may need adaptation

**Regional Availability:**
- Limited to specific AWS regions
- Latency considerations for global usage

**Learning Curve:**
- New platform concepts (workload identity, etc.)
- Team training required

---

## Resources & Documentation

### Official Documentation
- [AgentCore Getting Started](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-get-started-toolkit.html)
- [AgentCore Runtime Permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)
- [AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)
- [AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- [AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html)
- [AgentCore Code Interpreter](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html)
- [AgentCore Browser](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool.html)
- [AgentCore Identity](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity.html)
- [AgentCore Evaluations](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html)
- [Deploy A2A Servers](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-a2a.html)
- [Deploy MCP Servers](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)

### Blog Posts
- [Introducing Amazon Bedrock AgentCore](https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/)
- [AgentCore is Now Generally Available](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-is-now-generally-available/)
- [Build Trustworthy AI Agents with AgentCore Observability](https://aws.amazon.com/blogs/machine-learning/build-trustworthy-ai-agents-with-amazon-bedrock-agentcore-observability/)
- [Introducing AgentCore Code Interpreter](https://aws.amazon.com/blogs/machine-learning/introducing-the-amazon-bedrock-agentcore-code-interpreter/)
- [Introducing Agent-to-Agent Protocol Support](https://aws.amazon.com/blogs/machine-learning/introducing-agent-to-agent-protocol-support-in-amazon-bedrock-agentcore-runtime/)
- [AgentCore Gateway: Transforming Enterprise AI Agent Tool Development](https://aws.amazon.com/blogs/machine-learning/introducing-amazon-bedrock-agentcore-gateway-transforming-enterprise-ai-agent-tool-development/)
- [Securing AI Agents with AgentCore Identity](https://aws.amazon.com/blogs/security/securing-ai-agents-with-amazon-bedrock-agentcore-identity/)
- [AgentCore Adds Quality Evaluations and Policy Controls](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/)
- [Accelerate Development with AgentCore MCP Server](https://aws.amazon.com/blogs/machine-learning/accelerate-development-with-the-amazon-bedrock-agentcore-mcpserver/)
- [Building Production-Ready AI Agents with LangGraph and AgentCore](https://dev.to/aws/building-production-ready-ai-agents-with-langgraph-and-amazon-bedrock-agentcore-4h5k)
- [Strands Agents SDK: Technical Deep Dive](https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/)

### GitHub Resources
- [AgentCore Starter Toolkit](https://github.com/aws/bedrock-agentcore-starter-toolkit)
- [AgentCore Samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
- [AgentCore MCP Server](https://awslabs.github.io/mcp/servers/amazon-bedrock-agentcore-mcp-server)

### Third-Party Integration Guides
- [Monitor AgentCore AI Agent Infrastructure in Grafana Cloud](https://grafana.com/blog/2025/11/28/how-to-monitor-amazon-bedrock-agentcore-ai-agent-infrastructure-in-grafana-cloud/)
- [Monitor AI Agent Applications in Grafana Cloud](https://grafana.com/blog/2025/11/26/how-to-monitor-ai-agent-applications-on-amazon-bedrock-agentcore-with-grafana-cloud/)

### API References
- [InvokeAgentRuntime API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html)
- [AWS CLI Reference](https://docs.aws.amazon.com/cli/latest/reference/bedrock-agentcore/)
- [AgentCore CLI Documentation](https://aws.github.io/bedrock-agentcore-starter-toolkit/api-reference/cli.html)

### Pricing
- [AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- [AgentCore Pricing vs Self-Hosting Analysis](https://scalevise.com/resources/agentcore-bedrock-pricing-self-hosting/)

---

## Conclusion

AWS Bedrock AgentCore represents a comprehensive, enterprise-grade platform for production AI agents. Its framework-agnostic and model-agnostic approach, combined with modular services (Runtime, Gateway, Memory, Code Interpreter, Browser, Identity, Observability, Evaluations), makes it a compelling option for organizations looking to move beyond agent prototypes.

**Key Strengths:**
- Zero infrastructure management
- Production-ready security and compliance
- Framework flexibility (LangGraph, Strands, etc.)
- 8-hour session support (industry longest)
- Comprehensive observability and quality evaluations
- Protocol support (MCP, A2A) for interoperability

**Key Considerations:**
- AWS vendor lock-in
- Consumption-based pricing may be costly at scale
- Limited regional availability
- Learning curve for platform-specific concepts

For the Amelia project, AgentCore offers potential integration points across observability, memory management, tool integration, and runtime deployment - though careful evaluation of costs, vendor lock-in, and migration effort is warranted.
