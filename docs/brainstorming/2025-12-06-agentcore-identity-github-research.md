# AWS AgentCore Identity & GitHub Authentication Research

> **Status:** Research Complete
> **Date:** 2025-12-06
> **Purpose:** Understand AgentCore Identity's GitHub OAuth integration and git credential patterns

## Executive Summary

AWS AgentCore Identity supports **GitHub OAuth 2.0** for user authentication and API access, but the documentation **does not explicitly cover GitHub App installation tokens** or provide direct examples of git clone/push operations. The service focuses on API-level access (GitHub REST API) rather than git protocol operations.

### Key Findings

| Question | Answer |
|----------|--------|
| **GitHub OAuth support?** | ✅ Yes - Built-in `GithubOauth2` credential provider |
| **OAuth for git operations?** | ⚠️ Implicit - OAuth tokens work with HTTPS git URLs, but not documented |
| **GitHub App tokens?** | ❌ Not documented - Only OAuth apps (user delegation) are covered |
| **Token Vault retrieval?** | ✅ Yes - Via `@requires_access_token` decorator (automatic) |
| **CLI user auth flow?** | ✅ JWT bearer tokens (Cognito) → Workload Access Token → Resource OAuth |
| **Git credentials pattern?** | 🔍 Undocumented - Must infer from OAuth token + HTTPS git URLs |

---

## 1. How AgentCore Identity Handles GitHub OAuth

### OAuth 2.0 Credential Provider Setup

AgentCore supports GitHub as a **built-in credential provider vendor** (`GithubOauth2`):

```python
from bedrock_agentcore.services.identity import IdentityClient

identity_client = IdentityClient("us-east-1")

github_provider = identity_client.create_oauth2_credential_provider({
    "name": "github-provider",
    "credentialProviderVendor": "GithubOauth2",
    "oauth2ProviderConfigInput": {
        "githubOauth2ProviderConfig": {
            "clientId": "your-github-oauth-app-client-id",
            "clientSecret": "your-github-oauth-app-client-secret"
        }
    }
})
```

**Callback URL:** `https://bedrock-agentcore.<region>.amazonaws.com/identities/oauth2/callback`

### GitHub OAuth App Configuration

1. Navigate to GitHub Settings → Developer settings → OAuth Apps
2. Create New OAuth App
3. Set Authorization callback URL to AgentCore's regional callback endpoint
4. Generate client secret (shown only once)
5. Configure AgentCore Identity with client ID and secret

### OAuth Flow Type

AgentCore implements **3-legged OAuth (USER_FEDERATION)** for GitHub:

```python
@requires_access_token(
    provider_name="github-provider",
    scopes=["repo", "read:org"],  # Example scopes
    auth_flow="USER_FEDERATION",
    on_auth_url=lambda x: print(f"Authorize here: {x}"),
    force_authentication=False,
    callback_url='oauth2_callback_url_for_session_binding'
)
async def access_github_api(*, access_token: str):
    # Token is automatically provided by AgentCore Identity
    # Use for GitHub REST API calls
    headers = {"Authorization": f"Bearer {access_token}"}
    # Make authenticated requests...
```

**Process:**
1. Agent code decorated with `@requires_access_token` is invoked
2. Runtime checks Token Vault for existing token (scoped to user + agent)
3. If token missing/expired, generates OAuth authorization URL
4. User grants consent in browser → redirects to callback URL
5. AgentCore stores access token + refresh token in Token Vault
6. Subsequent calls reuse token until expiration

---

## 2. OAuth Tokens for Git Clone/Push Operations

### ⚠️ Documentation Gap

The official AgentCore documentation **does not provide explicit guidance** on using GitHub OAuth tokens for git operations (clone, push, pull). However, standard GitHub OAuth patterns apply:

**HTTPS Git URL Pattern:**
```bash
git clone https://x-access-token:<oauth-token>@github.com/org/repo.git
git push https://x-access-token:<oauth-token>@github.com/org/repo.git
```

**Inferred Agent Implementation:**
```python
@requires_access_token(
    provider_name="github-provider",
    scopes=["repo"],  # Required for private repo access
    auth_flow="USER_FEDERATION",
    on_auth_url=send_auth_url_to_user,
)
async def clone_and_push_code(*, access_token: str):
    repo_url = f"https://x-access-token:{access_token}@github.com/org/repo.git"

    # Use subprocess or git library
    subprocess.run(["git", "clone", repo_url, "/tmp/workspace"])
    # ... make changes ...
    subprocess.run(["git", "push", "origin", "main"], cwd="/tmp/workspace")
```

**Required GitHub OAuth Scopes:**

| Scope | Purpose |
|-------|---------|
| `repo` | Full control of private repositories (required for clone/push) |
| `public_repo` | Access to public repositories only |
| `read:org` | Read organization membership (for org repos) |
| `workflow` | Update GitHub Actions workflows |

### Additional Setup Needed

**Git credential helper** is likely required in AgentCore Runtime environment:

```bash
# Option 1: Configure git to use access token
git config --global credential.helper store
echo "https://x-access-token:${GITHUB_TOKEN}@github.com" > ~/.git-credentials

# Option 2: Set environment variables
export GIT_ASKPASS=/bin/echo
export GIT_USERNAME=x-access-token
export GIT_PASSWORD=${GITHUB_TOKEN}
```

**AgentCore Runtime worktree pattern** (from design doc):
- Runtime clones repo into isolated worktree
- Credentials must be available for initial clone
- Push operations require write permissions (`repo` scope)

---

## 3. GitHub App Installation Tokens

### ❌ Not Documented in AgentCore

The AgentCore Identity documentation **does not mention GitHub App installation tokens**, which are the recommended pattern for:
- Organization-wide access
- Repository-level permissions
- Time-limited tokens (1 hour expiration)
- Fine-grained access control

### GitHub App Token Pattern (External to AgentCore)

GitHub Apps use **JWT-based installation tokens** instead of OAuth:

```python
import jwt
import requests
from datetime import datetime, timedelta

# Generate JWT for GitHub App
def generate_app_jwt(app_id, private_key):
    payload = {
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(minutes=10)).timestamp()),
        "iss": app_id
    }
    return jwt.encode(payload, private_key, algorithm="RS256")

# Get installation access token
def get_installation_token(app_jwt, installation_id):
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json"
    }
    response = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers=headers
    )
    return response.json()["token"]  # Valid for 1 hour
```

**Git clone with installation token:**
```bash
git clone https://x-access-token:<installation-token>@github.com/org/repo.git
```

### Workaround for AgentCore

Since GitHub App tokens aren't built-in, two approaches:

**Option A: Store GitHub App credentials in Secrets Manager**
```python
# Retrieve from AWS Secrets Manager in agent code
import boto3

secrets_client = boto3.client("secretsmanager")
github_app_secret = secrets_client.get_secret_value(
    SecretId="github-app-private-key"
)["SecretString"]

# Generate installation token (valid 1 hour)
installation_token = get_installation_token(...)

# Use for git operations
repo_url = f"https://x-access-token:{installation_token}@github.com/org/repo.git"
```

**Option B: Use API Key Credential Provider**
```python
# Store installation token as API key (requires periodic refresh)
identity_client.create_api_key_credential_provider({
    "name": "github-app-installation",
    "apiKey": installation_token  # Must be refreshed every hour
})

@requires_api_key(provider_name="github-app-installation")
async def use_github_app(*, api_key: str):
    # api_key is the installation token
    pass
```

**⚠️ Limitation:** API key providers don't auto-refresh, so GitHub App token expiration (1 hour) requires manual rotation logic.

---

## 4. Token Vault - Programmatic Retrieval

### Automatic Token Provision (Recommended)

AgentCore Runtime **automatically provides tokens** via decorators:

```python
@requires_access_token(
    provider_name="github-provider",
    scopes=["repo", "read:org"],
    auth_flow="USER_FEDERATION",
)
async def my_github_tool(*, access_token: str):
    # Token is injected automatically
    # No manual Token Vault access needed
```

**What happens:**
1. Runtime validates inbound JWT (user authentication)
2. Creates workload access token (agent identity + user identity)
3. Calls `GetResourceOauth2Token` API with workload token
4. Token Vault returns cached token OR triggers OAuth flow
5. Access token injected into `access_token` parameter

### Manual Token Retrieval (Advanced)

For agents **not** hosted on AgentCore Runtime (e.g., external systems):

```python
from bedrock_agentcore.services.identity import IdentityClient

identity_client = IdentityClient("us-east-1")

# Step 1: Get workload access token
workload_access_token = identity_client.get_workload_access_token(
    workload_name="my-agent-name",
    user_token="user-jwt-token"  # Or user_id="user-identifier"
)

# Step 2: Use workload token to get OAuth token from Token Vault
oauth_token = identity_client.get_resource_oauth2_token(
    provider_name="github-provider",
    workload_access_token=workload_access_token,
    scopes=["repo"]
)

# Step 3: Use OAuth token for GitHub API/git operations
```

**IAM Permissions Required:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:GetWorkloadAccessToken",
        "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
        "bedrock-agentcore:GetResourceOauth2Token"
      ],
      "Resource": [
        "arn:aws:bedrock-agentcore:us-east-1:account:workload-identity-directory/*",
        "arn:aws:bedrock-agentcore:us-east-1:account:token-vault/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:us-east-1:account:secret:github-oauth-*"
    }
  ]
}
```

### Token Vault Security Model

**Storage:**
- OAuth access tokens + refresh tokens encrypted with AWS KMS
- Customer-managed keys (CMK) supported
- Token binding: `workload_identity_id + user_id` (from JWT `iss`/`sub` claims)

**Isolation:**
- User A's token CANNOT be accessed for User B's requests
- Agent X's token CANNOT be accessed by Agent Y
- Binding enforced by `GetResourceOauth2Token` API

**Refresh Token Management:**
- AgentCore **automatically** uses refresh tokens when access tokens expire
- No user re-consent required if refresh token valid
- Refresh token expiration → full OAuth flow required

**GitHub Refresh Token Configuration:**

GitHub requires enabling "User-to-server token expiration" in OAuth app settings:
```json
{
  "credentialProviderVendor": "GithubOauth2",
  "oauth2ProviderConfigInput": {
    "githubOauth2ProviderConfig": {
      "clientId": "...",
      "clientSecret": "...",
      "customParameters": {
        "access_type": "offline"  // Request refresh tokens
      }
    }
  }
}
```

---

## 5. CLI User Authentication Flow

### Complete End-to-End Flow

```
┌────────────┐         ┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│  CLI User  │         │   Cognito   │         │   Control    │         │  AgentCore  │
│            │         │ User Pool   │         │    Plane     │         │   Runtime   │
└─────┬──────┘         └──────┬──────┘         └──────┬───────┘         └──────┬──────┘
      │                       │                       │                        │
      │  1. amelia start --remote                     │                        │
      ├──────────────────────────────────────────────▶│                        │
      │                       │                       │                        │
      │  2. 401 Unauthorized (needs JWT)              │                        │
      │◀──────────────────────────────────────────────┤                        │
      │                       │                       │                        │
      │  3. amelia login      │                       │                        │
      ├──────────────────────▶│                       │                        │
      │                       │                       │                        │
      │  4. Browser OAuth (GitHub federated)          │                        │
      │◀─────────────────────▶│                       │                        │
      │                       │                       │                        │
      │  5. JWT access token  │                       │                        │
      │◀──────────────────────┤                       │                        │
      │                       │                       │                        │
      │  6. POST /workflows (Authorization: Bearer JWT)                        │
      ├──────────────────────────────────────────────▶│                        │
      │                       │                       │                        │
      │                       │      7. Validate JWT (OIDC discovery)          │
      │                       │◀──────────────────────┤                        │
      │                       │                       │                        │
      │                       │      8. Extract user_id (iss/sub claims)       │
      │                       │                       ├───────────────────────▶│
      │                       │                       │                        │
      │                       │                       │  9. GetWorkloadAccessTokenForJWT
      │                       │                       │        (agent_id + user_id)
      │                       │                       │◀───────────────────────┤
      │                       │                       │                        │
      │                       │                       │ 10. Workload Access Token
      │                       │                       │                        │
      │                       │                       │ 11. InvokeAgentRuntime │
      │                       │                       │   (includes workload token)
      │                       │                       ├───────────────────────▶│
      │                       │                       │                        │
      │                       │                       │                        │  Agent needs GitHub access
      │                       │                       │                        │  @requires_access_token triggered
      │                       │                       │                        │
      │                       │                       │ 12. GetResourceOauth2Token
      │                       │                       │   (workload_token, provider="github-provider")
      │                       │                       │◀───────────────────────┤
      │                       │                       │                        │
      │                       │                       │ 13. Check Token Vault  │
      │                       │                       │    (workload_id + user_id)
      │                       │                       │                        │
      │                       │  14. If no token: OAuth authorization URL      │
      │◀──────────────────────────────────────────────────────────────────────┤
      │                       │                       │                        │
      │  15. User opens URL, grants GitHub consent    │                        │
      ├──────────────────────▶│ GitHub OAuth         │                        │
      │                       │                       │                        │
      │  16. Callback with authorization code         │                        │
      │                       ├──────────────────────▶│                        │
      │                       │                       │                        │
      │                       │                       │ 17. Store token in Vault
      │                       │                       ├───────────────────────▶│
      │                       │                       │                        │
      │                       │                       │ 18. Return GitHub OAuth token
      │                       │                       │◀───────────────────────┤
      │                       │                       │                        │
      │                       │                       │ 19. Agent uses token for
      │                       │                       │     GitHub API / git operations
      │                       │                       │                        │
      │  20. WebSocket: workflow_completed            │                        │
      │◀──────────────────────────────────────────────────────────────────────┤
```

### Implementation Steps

**1. User Authentication (Cognito + GitHub)**

```bash
# CLI command triggers OAuth flow
$ amelia login --remote

# Output:
# Please visit: https://amelia-prod.auth.us-east-1.amazoncognito.com/oauth2/authorize?...
# Waiting for authentication...

# After GitHub OAuth consent:
# ✅ Authenticated as: octocat
# Token stored in: ~/.amelia/credentials
```

**Cognito Setup:**
```bash
# Create Cognito User Pool with GitHub federation
aws cognito-idp create-user-pool \
  --pool-name amelia-users \
  --auto-verified-attributes email

# Add GitHub identity provider
aws cognito-idp create-identity-provider \
  --user-pool-id $POOL_ID \
  --provider-name GitHub \
  --provider-type OIDC \
  --provider-details '{
    "client_id": "github-oauth-app-client-id",
    "client_secret": "...",
    "authorize_scopes": "openid email profile",
    "oidc_issuer": "https://token.actions.githubusercontent.com"
  }'
```

**2. CLI Client Sends JWT**

```python
# amelia/client/remote.py
import requests

class RemoteClient:
    def __init__(self, base_url: str, credentials_path: str = "~/.amelia/credentials"):
        self.base_url = base_url
        self.jwt_token = self._load_jwt(credentials_path)

    def start_workflow(self, issue_id: str, profile: str):
        headers = {
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json"
        }
        response = requests.post(
            f"{self.base_url}/api/v1/workflows",
            headers=headers,
            json={"issue_id": issue_id, "profile": profile}
        )
        return response.json()
```

**3. Control Plane Validates JWT**

```python
# amelia/cloud/control_plane/auth.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
import jwt
import requests

security = HTTPBearer()

async def validate_jwt_token(token: str = Depends(security)):
    # Fetch OIDC discovery document
    discovery_url = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_POOLID/.well-known/openid-configuration"
    discovery = requests.get(discovery_url).json()
    jwks_uri = discovery["jwks_uri"]

    # Decode and validate JWT
    try:
        payload = jwt.decode(
            token.credentials,
            key=fetch_jwks(jwks_uri),
            algorithms=["RS256"],
            audience="client-id",
            issuer=discovery["issuer"]
        )
        return {
            "user_id": payload["sub"],
            "username": payload.get("cognito:username"),
            "email": payload.get("email")
        }
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

**4. Runtime Receives Workload Access Token**

AgentCore Runtime **automatically** exchanges the inbound JWT for a workload access token:

```python
# Agent code (amelia/cloud/runtime_wrapper.py)
from bedrock_agentcore import BedrockAgentCoreApp
from bedrock_agentcore.identity.auth import requires_access_token

app = BedrockAgentCoreApp(name="amelia-orchestrator")

@app.agent()
async def orchestrate_workflow(event: dict, context):
    # Workload access token automatically available in context
    # Runtime called GetWorkloadAccessTokenForJWT using inbound JWT

    # When agent needs GitHub access:
    await clone_and_execute_code(event["issue_id"])

@requires_access_token(
    provider_name="github-provider",
    scopes=["repo", "read:org"],
    auth_flow="USER_FEDERATION",
    on_auth_url=lambda url: emit_oauth_url_to_client(url)
)
async def clone_and_execute_code(issue_id: str, *, access_token: str):
    # Token Vault lookup: workload_id + user_id (from JWT)
    # If token exists → return it
    # If missing → generate OAuth URL → user consents → store token

    repo_url = f"https://x-access-token:{access_token}@github.com/org/repo.git"
    subprocess.run(["git", "clone", repo_url, "/tmp/workspace"])
    # ... execute workflow ...
```

**5. OAuth URL Delivery to User**

```python
# Control Plane WebSocket event
def emit_oauth_url_to_client(authorization_url: str):
    websocket_hub.broadcast({
        "type": "authorization_required",
        "service": "github",
        "url": authorization_url,
        "message": "Please authorize Amelia to access your GitHub repositories"
    })

# CLI receives event and opens browser
def handle_auth_required_event(event: dict):
    import webbrowser
    print(f"🔐 GitHub authorization required: {event['url']}")
    webbrowser.open(event['url'])
    print("Waiting for authorization...")
```

---

## 6. Security & Best Practices

### Token Vault Security Controls

✅ **Encryption at Rest**
- All tokens encrypted with AWS KMS
- Support for customer-managed keys (CMK)
- Keys never leave AWS KMS

✅ **User-Agent Binding**
- Tokens scoped to `(workload_identity_id, user_id)` pair
- User A's token inaccessible for User B's workflows
- Prevents token extraction attacks

✅ **IAM Access Control**
- Token Vault access requires explicit IAM permissions
- Service-linked role: `AWSServiceRoleForBedrockAgentCoreRuntimeIdentity`
- Principle of least privilege enforced

✅ **Automatic Refresh**
- Refresh tokens stored securely alongside access tokens
- AgentCore handles token refresh transparently
- User re-consent only required when refresh token expires

### GitHub OAuth Scopes (Principle of Least Privilege)

**For Amelia's use case:**

| Scope | Needed? | Rationale |
|-------|---------|-----------|
| `repo` | ✅ **YES** | Clone private repos, push code changes, create PRs |
| `read:org` | ✅ **YES** | Access organization repositories, validate membership |
| `workflow` | ⚠️ **MAYBE** | Update GitHub Actions workflows (if Amelia modifies CI/CD) |
| `admin:repo_hook` | ❌ **NO** | Not needed - Amelia doesn't manage webhooks |
| `delete_repo` | ❌ **NO** | Never grant destructive permissions |

**Configuration:**
```python
@requires_access_token(
    provider_name="github-provider",
    scopes=["repo", "read:org"],  # Minimal required scopes
    auth_flow="USER_FEDERATION",
)
```

### Git Credentials in AgentCore Runtime

**Best Practice: Ephemeral Credentials**

```python
# Clone with token in URL (credentials not persisted)
async def clone_repo_ephemeral(repo: str, access_token: str):
    repo_url = f"https://x-access-token:{access_token}@github.com/{repo}.git"
    subprocess.run([
        "git", "clone",
        "--depth", "1",  # Shallow clone for speed
        "--single-branch",
        repo_url,
        "/tmp/workspace"
    ])

    # Configure git identity for commits
    subprocess.run(["git", "config", "user.name", "Amelia Bot"], cwd="/tmp/workspace")
    subprocess.run(["git", "config", "user.email", "bot@amelia.dev"], cwd="/tmp/workspace")

    # Push changes using same token
    subprocess.run(["git", "push"], cwd="/tmp/workspace", env={
        "GIT_ASKPASS": "/bin/echo",
        "GIT_USERNAME": "x-access-token",
        "GIT_PASSWORD": access_token
    })
```

**⚠️ Avoid:**
- Storing tokens in `~/.git-credentials` (persists across sessions)
- Hardcoding tokens in environment variables
- Logging git URLs with embedded tokens

### Token Expiration Handling

**Access Token Lifespan:** Typically 1-2 hours (GitHub default: 8 hours)

**Strategy 1: Retry with Force Authentication**
```python
@requires_access_token(
    provider_name="github-provider",
    scopes=["repo"],
    force_authentication=True  # Always get fresh token
)
```

**Strategy 2: Handle 401 Errors**
```python
import requests

def github_api_call(access_token: str, endpoint: str):
    response = requests.get(
        f"https://api.github.com/{endpoint}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if response.status_code == 401:
        # Token expired - trigger re-authentication
        raise TokenExpiredError("GitHub token invalid or expired")
    return response.json()
```

---

## 7. Implementation Recommendations for Amelia

### Architecture Integration

Based on the [AWS AgentCore Deployment Design](/Users/ka/github/amelia-docs/docs/brainstorming/2025-12-06-aws-agentcore-deployment-design.md), here's how to integrate GitHub authentication:

**Phase 1: GitHub OAuth Credential Provider**
```python
# Deploy script: setup_github_provider.py
from bedrock_agentcore.services.identity import IdentityClient

def setup_github_provider(region: str, github_client_id: str, github_client_secret: str):
    client = IdentityClient(region)

    provider = client.create_oauth2_credential_provider({
        "name": "amelia-github-provider",
        "credentialProviderVendor": "GithubOauth2",
        "oauth2ProviderConfigInput": {
            "githubOauth2ProviderConfig": {
                "clientId": github_client_id,
                "clientSecret": github_client_secret,
                "customParameters": {
                    "access_type": "offline"  # Enable refresh tokens
                }
            }
        }
    })

    print(f"✅ GitHub provider created: {provider['name']}")
    print(f"📋 Callback URL: {provider['callbackUrl']}")
    print(f"⚠️  Add this URL to GitHub OAuth app settings")

    return provider
```

**Phase 2: Developer Agent with Git Operations**
```python
# amelia/agents/developer.py
from bedrock_agentcore.identity.auth import requires_access_token
import subprocess
import tempfile
import os

@requires_access_token(
    provider_name="amelia-github-provider",
    scopes=["repo", "read:org"],
    auth_flow="USER_FEDERATION",
    on_auth_url=send_auth_url_via_websocket
)
async def execute_task_in_git_worktree(
    task: Task,
    repo: str,
    branch: str,
    *,
    access_token: str
) -> TaskResult:
    """
    Execute a development task in an isolated git worktree.

    Args:
        task: Task from TaskDAG
        repo: GitHub repo (format: "owner/repo")
        branch: Branch to work on
        access_token: GitHub OAuth token (auto-injected)
    """
    with tempfile.TemporaryDirectory() as workspace:
        # Clone repo with OAuth token
        repo_url = f"https://x-access-token:{access_token}@github.com/{repo}.git"
        subprocess.run([
            "git", "clone",
            "--branch", branch,
            "--depth", "1",
            repo_url,
            workspace
        ], check=True)

        # Configure git identity
        subprocess.run(["git", "config", "user.name", "Amelia Bot"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.email", "bot@amelia.dev"], cwd=workspace, check=True)

        # Execute task using LLM + shell tools
        result = await execute_with_llm(task, workspace)

        # Commit and push changes
        subprocess.run(["git", "add", "."], cwd=workspace, check=True)
        subprocess.run([
            "git", "commit",
            "-m", f"[Amelia] {task.description}\n\nTask ID: {task.id}"
        ], cwd=workspace, check=True)

        # Push using token in environment
        env = os.environ.copy()
        env.update({
            "GIT_ASKPASS": "/bin/echo",
            "GIT_USERNAME": "x-access-token",
            "GIT_PASSWORD": access_token
        })
        subprocess.run(["git", "push"], cwd=workspace, env=env, check=True)

        return result

def send_auth_url_via_websocket(authorization_url: str):
    """Send OAuth URL to user via Control Plane WebSocket"""
    from amelia.cloud.control_plane.websocket_hub import broadcast_event

    broadcast_event({
        "type": "authorization_required",
        "service": "GitHub",
        "url": authorization_url,
        "message": "Please authorize Amelia to access your GitHub repositories",
        "required_scopes": ["repo", "read:org"]
    })
```

**Phase 3: CLI User Experience**
```bash
# First-time workflow execution
$ amelia start PROJ-123 --remote --profile cloud-prod

# Output:
# 🚀 Starting workflow for PROJ-123...
# ✅ Authenticated as: developer@example.com
# 🔐 GitHub authorization required
#
# Please visit this URL to grant Amelia access to your repositories:
# https://github.com/login/oauth/authorize?client_id=...&scope=repo+read:org
#
# [Opening browser...]
# ⏳ Waiting for authorization...
# ✅ GitHub access granted
# 🏗️  Architect generating plan...
# 📋 Plan ready for approval (12 tasks)
#
# Approve? [y/N]: y
#
# 🔨 Developer executing tasks...
# ✅ Task 1/12 completed: Create user model
# ✅ Task 2/12 completed: Add database migration
# ...

# Subsequent executions (token cached)
$ amelia start PROJ-124 --remote --profile cloud-prod

# Output:
# 🚀 Starting workflow for PROJ-124...
# ✅ Authenticated as: developer@example.com
# ✅ GitHub access already authorized (using cached token)
# 🏗️  Architect generating plan...
```

### Testing Strategy

**Unit Tests:**
```python
# tests/unit/cloud/test_github_auth.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_git_clone_with_oauth_token(mock_github_token):
    """Test git clone using OAuth token from Token Vault"""
    with patch("subprocess.run") as mock_subprocess:
        await execute_task_in_git_worktree(
            task=Task(id="T1", description="Test task"),
            repo="org/repo",
            branch="main",
            access_token=mock_github_token
        )

        # Verify git clone called with token in URL
        mock_subprocess.assert_any_call([
            "git", "clone",
            "--branch", "main",
            "--depth", "1",
            f"https://x-access-token:{mock_github_token}@github.com/org/repo.git",
            pytest.any(str)
        ], check=True)

@pytest.mark.asyncio
async def test_oauth_flow_triggered_when_no_token():
    """Test OAuth flow when Token Vault has no cached token"""
    with patch("amelia.cloud.runtime_wrapper.send_auth_url_via_websocket") as mock_send:
        # Simulate AgentCore triggering OAuth flow
        auth_url = "https://github.com/login/oauth/authorize?client_id=..."
        mock_send(auth_url)

        # Verify WebSocket event sent to user
        mock_send.assert_called_once()
        assert "github.com" in mock_send.call_args[0][0]
```

**Integration Tests (AgentCore Runtime):**
```bash
# Test locally with agentcore CLI
$ agentcore dev --agent amelia-orchestrator

# In separate terminal, invoke with test JWT
$ agentcore invoke '{"issue_id": "TEST-123", "repo": "test/repo"}' \
    --bearer "$(agentcore identity get-cognito-inbound-token)"

# Verify:
# 1. JWT validated
# 2. Workload access token generated
# 3. GitHub OAuth flow triggered (or cached token used)
# 4. Git operations succeed
```

---

## 8. Open Questions & Gaps

### Documentation Gaps

❓ **GitHub App Installation Tokens**
- No mention of GitHub App authentication (only OAuth apps)
- Recommended pattern for org-wide access not documented
- Workaround: Store GitHub App private key in Secrets Manager, generate tokens manually

❓ **Git Protocol Support**
- No explicit examples of git clone/push with OAuth tokens
- Unclear if SSH keys supported (likely no, OAuth recommended)
- Git credential helper configuration not documented

❓ **Scope-to-Permission Mapping**
- GitHub OAuth scopes not listed in AgentCore docs
- Must refer to GitHub's scope documentation
- Fine-grained permissions (GitHub Apps) not covered

❓ **Token Refresh Edge Cases**
- What happens if refresh token expires during long-running workflow?
- How to handle user revoking access mid-execution?
- Error handling patterns not documented

### Recommended Clarifications from AWS

1. **Explicitly document git operations with OAuth tokens** (HTTPS git URLs)
2. **Add GitHub App installation token pattern** (API Key provider workaround)
3. **Provide git credential helper setup** for Runtime environments
4. **Clarify token expiration handling** in long-running agents (8-hour sessions)
5. **Document organization repository access patterns** (OAuth scopes, admin permissions)

---

## 9. References

### Official Documentation

- [AWS Bedrock AgentCore Identity](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-getting-started.html)
- [GitHub OAuth Configuration](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-idp-github.html)
- [Obtain OAuth 2.0 Access Tokens](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-authentication.html)
- [Inbound/Outbound Authentication](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html)
- [Token Vault Overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/obtain-credentials.html)
- [Workload Access Tokens](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/get-workload-access-token.html)

### Blog Posts & Security

- [Introducing AgentCore Identity](https://aws.amazon.com/blogs/machine-learning/introducing-amazon-bedrock-agentcore-identity-securing-agentic-ai-at-scale/)
- [Securing AI Agents with AgentCore Identity](https://aws.amazon.com/blogs/security/securing-ai-agents-with-amazon-bedrock-agentcore-identity/)

### Sample Code

- [AgentCore Starter Toolkit](https://github.com/aws/bedrock-agentcore-starter-toolkit)
- [Identity Quickstart](https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/identity/quickstart.html)
- [AgentCore Samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)

### GitHub OAuth Reference

- [GitHub OAuth Scopes](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)
- [GitHub App Installation Tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)
- [Git Credentials for HTTPS](https://git-scm.com/docs/git-credential-store)

### AWS Services Integration

- [AWS Cognito GitHub Federation](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-social-idp.html)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [AWS CodePipeline GitHub Integration](https://docs.aws.amazon.com/codepipeline/latest/userguide/appendix-github-oauth.html)

---

## Summary

AWS AgentCore Identity provides **robust GitHub OAuth 2.0 support** for user-delegated API access with automatic token management via the Token Vault. However, the documentation **lacks explicit guidance** on git operations (clone/push) and GitHub App installation tokens.

**Key Takeaways for Amelia Deployment:**

✅ Use `GithubOauth2` credential provider with `repo` and `read:org` scopes
✅ Leverage `@requires_access_token` decorator for automatic token injection
✅ Embed tokens in HTTPS git URLs: `https://x-access-token:{token}@github.com/org/repo.git`
✅ Configure Cognito User Pool with GitHub federation for CLI authentication
✅ Handle OAuth authorization URLs via WebSocket events to user
✅ Trust Token Vault for secure storage and automatic refresh token management

⚠️ GitHub App tokens require manual implementation (store private key in Secrets Manager)
⚠️ Git credential helper configuration needed in AgentCore Runtime
⚠️ Token expiration during 8-hour workflows requires error handling + retry logic
