#!/usr/bin/env bash
#
# Backfill the "Area" field on the Amelia Roadmap GitHub Project.
#
# For each project item that has no Area set, infers the correct area from:
#   1. area:* labels on the issue
#   2. Title keyword matching
#   3. Body keyword matching (first 500 chars)
#
# Usage:
#   ./scripts/backfill-project-areas.sh                        # Dry run (default)
#   ./scripts/backfill-project-areas.sh --apply                # Actually apply changes
#   ./scripts/backfill-project-areas.sh --all                  # Re-evaluate ALL items (dry run)
#   ./scripts/backfill-project-areas.sh --all --apply          # Re-evaluate ALL items and apply
#   ./scripts/backfill-project-areas.sh --strip-labels         # Remove area:* labels from issues (dry run)
#   ./scripts/backfill-project-areas.sh --strip-labels --apply # Remove area:* labels from issues

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
ORG="existential-birds"
PROJECT_NUMBER=1
PROJECT_ID="PVT_kwDODvSqSs4BLK3J"
AREA_FIELD_ID="PVTSSF_lADODvSqSs4BLK3Jzg60vHQ"

# Area name → option ID lookup
area_option_id() {
  case "$1" in
    Core)           echo "71295761" ;;
    Agents)         echo "7c7b7274" ;;
    Dashboard)      echo "120592f8" ;;
    CLI)            echo "1300bab7" ;;
    Server)         echo "bc7d4cb8" ;;
    Knowledge)      echo "2a1c170a" ;;
    Sandbox)        echo "6d389495" ;;
    Pipelines)      echo "b3998bd7" ;;
    Drivers)        echo "fbb59f30" ;;
    Integrations)   echo "e775a143" ;;
    Docs)           echo "36e4a113" ;;
    Infrastructure) echo "578c6aa8" ;;
    *) echo "" ;;
  esac
}

# ── Parse args ────────────────────────────────────────────────────────────────
APPLY=false
EVAL_ALL=false
STRIP_LABELS=false
for arg in "$@"; do
  case "$arg" in
    --apply)        APPLY=true ;;
    --all)          EVAL_ALL=true ;;
    --strip-labels) STRIP_LABELS=true ;;
    --help|-h)
      echo "Usage: $0 [--apply] [--all] [--strip-labels]"
      echo "  --apply         Apply changes (default is dry run)"
      echo "  --all           Re-evaluate all items, not just unset ones"
      echo "  --strip-labels  Remove area:* labels from issues (keeps them on PRs)"
      exit 0
      ;;
    *) echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

AREA_LABELS="area:core area:agents area:dashboard area:cli area:server area:documentation"

# ── Label → Area mapping ─────────────────────────────────────────────────────
label_to_area() {
  local label="$1"
  case "$label" in
    area:core)          echo "Core" ;;
    area:agents)        echo "Agents" ;;
    area:dashboard)     echo "Dashboard" ;;
    area:cli)           echo "CLI" ;;
    area:server)        echo "Server" ;;
    area:documentation) echo "Docs" ;;
    *)                  echo "" ;;
  esac
}

# ── Title/body keyword → Area inference ───────────────────────────────────────
# Returns area based on keyword patterns in title+body text.
# Order matters: more specific patterns first.
infer_from_text() {
  local text="$1"
  text=$(echo "$text" | tr '[:upper:]' '[:lower:]')

  # Dashboard (check early — feat(dashboard) prefix is very high signal)
  if [[ "$text" =~ feat\(dashboard\) ]]; then
    echo "Dashboard"; return
  fi

  # Knowledge / RAG / embeddings / ingestion
  if [[ "$text" =~ (knowledge.library|embedding|vector.store|rag[^e]|document.ingestion|docling|chunker|knowledge.pr) ]]; then
    echo "Knowledge"; return
  fi

  # Sandbox / container / devcontainer / worktree isolation
  if [[ "$text" =~ (sandbox|container.driver|devcontainer|worktree.isolation|docker.driver|devcontainer.sandbox) ]]; then
    echo "Sandbox"; return
  fi

  # Pipelines / langgraph / pipeline / workflow graph / review loop
  if [[ "$text" =~ (pipeline|langgraph|workflow.graph|pipeline.registry|routing.node|review.iteration|review.loop) ]]; then
    echo "Pipelines"; return
  fi

  # Drivers / LLM abstraction
  if [[ "$text" =~ (driver.abstraction|api.driver|cli.driver|llm.driver|pydantic.ai|openrouter|drivertype|driverinterface|deepagent) ]]; then
    echo "Drivers"; return
  fi

  # Integrations / trackers / jira / client SDK
  if [[ "$text" =~ (tracker.sync|jira|github.tracker|client.sdk|amelia.client|telegram|slack.integration|trackertype) ]]; then
    echo "Integrations"; return
  fi

  # Infrastructure / CI / CD / release / docker-compose / github.action / type hints / chore
  if [[ "$text" =~ (ci/cd|ci.pipeline|github.action|release.process|docker.compose|pre.push|\.github|license.header|type.hint|return.type|type:.ignore) ]]; then
    echo "Infrastructure"; return
  fi

  # Docs / documentation site / vitepress / mintlify
  if [[ "$text" =~ (documentation.site|vitepress|docs.site|docs/site|mintlify) ]]; then
    echo "Docs"; return
  fi

  # Dashboard (use specific terms to avoid matching "dashboard" in body context)
  if [[ "$text" =~ (feat\(dashboard\)|dashboard.ui|dashboard.component|frontend.dev|ui.component|dashboard.layout|dashboard.view|costs.view|design.system|batch.progress.visual|responsive.*layout|single.column|display.task.progress|quick.shot.modal|design.document.import) ]]; then
    echo "Dashboard"; return
  fi

  # CLI
  if [[ "$text" =~ (feat\(cli\)|cli.command|typer|amelia.start|amelia.review|amelia.config|command.line|--stream.flag|--task.option|first.time.setup|cli.thin.client) ]]; then
    echo "CLI"; return
  fi

  # Server / API endpoints / FastAPI
  if [[ "$text" =~ (api.endpoint|fastapi|server.route|websocket.server|http.server|api.route|rest.api|server.restart|server.foundation|database.foundation|postgresql|workflow.models|event.bus|pairing.api) ]]; then
    echo "Server"; return
  fi

  # Agents
  if [[ "$text" =~ (architect.agent|developer.agent|reviewer.agent|agent.prompt|agent.behavior|agent.tool|agent.output|brainstorm|evaluator.agent|oracle|debate.mode|reviewer.*agentic|agentic.review|agent.schema|feedback.evaluator) ]]; then
    echo "Agents"; return
  fi

  # Core / orchestrator / state machine (broad, check last)
  if [[ "$text" =~ (orchestrat|state.machine|execution.state|core.types|shared.types|executionstate|context.compiler|context.window|tool.registry|workflow.recovery|plan.generation|session.continuity|verification.framework|dead.code|remove.dead|refactor.*consolidat|stateless.reducer) ]]; then
    echo "Core"; return
  fi

  echo ""
}

# ── Fetch all project items ───────────────────────────────────────────────────
echo "Fetching project items..."

ALL_ITEMS="[]"
HAS_NEXT=true
CURSOR=""

while [[ "$HAS_NEXT" == "true" ]]; do
  if [[ -z "$CURSOR" ]]; then
    AFTER_ARG=""
  else
    AFTER_ARG=", after: \"$CURSOR\""
  fi

  RESPONSE=$(gh api graphql -f query="
    query {
      organization(login: \"$ORG\") {
        projectV2(number: $PROJECT_NUMBER) {
          items(first: 50$AFTER_ARG) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              fieldValueByName(name: \"Area\") {
                ... on ProjectV2ItemFieldSingleSelectValue {
                  name
                }
              }
              content {
                __typename
                ... on Issue {
                  number
                  title
                  body
                  labels(first: 20) {
                    nodes { name }
                  }
                }
                ... on PullRequest {
                  number
                  title
                  body
                  labels(first: 20) {
                    nodes { name }
                  }
                }
                ... on DraftIssue {
                  title
                  body
                }
              }
            }
          }
        }
      }
    }
  ")

  PAGE_ITEMS=$(echo "$RESPONSE" | jq '.data.organization.projectV2.items.nodes')
  ALL_ITEMS=$(echo "$ALL_ITEMS" "$PAGE_ITEMS" | jq -s '.[0] + .[1]')
  HAS_NEXT=$(echo "$RESPONSE" | jq -r '.data.organization.projectV2.items.pageInfo.hasNextPage')
  CURSOR=$(echo "$RESPONSE" | jq -r '.data.organization.projectV2.items.pageInfo.endCursor')
done

TOTAL=$(echo "$ALL_ITEMS" | jq 'length')
echo "Found $TOTAL project items."
echo ""

# ── Process each item ─────────────────────────────────────────────────────────
ASSIGNED=0
SKIPPED_HAS_AREA=0
SKIPPED_NO_MATCH=0
FAILED=0

for i in $(seq 0 $((TOTAL - 1))); do
  ITEM=$(echo "$ALL_ITEMS" | jq ".[$i]")
  ITEM_ID=$(echo "$ITEM" | jq -r '.id')
  CURRENT_AREA=$(echo "$ITEM" | jq -r '.fieldValueByName.name // empty')
  NUMBER=$(echo "$ITEM" | jq -r '.content.number // empty')
  TITLE=$(echo "$ITEM" | jq -r '.content.title // empty')
  BODY=$(echo "$ITEM" | jq -r '.content.body // empty' | head -c 500)
  LABELS=$(echo "$ITEM" | jq -r '.content.labels.nodes[]?.name // empty' 2>/dev/null || echo "")

  # Build display label
  if [[ -n "$NUMBER" ]]; then
    DISPLAY="#$NUMBER: $TITLE"
  elif [[ -n "$TITLE" ]]; then
    DISPLAY="(draft) $TITLE"
  else
    DISPLAY="(unknown item $ITEM_ID)"
  fi

  # Skip items that already have an area (unless --all)
  if [[ -n "$CURRENT_AREA" && "$EVAL_ALL" == "false" ]]; then
    SKIPPED_HAS_AREA=$((SKIPPED_HAS_AREA + 1))
    continue
  fi

  # ── Inference: title keywords first (most specific), then labels, then body
  INFERRED=""

  # 1. Try title keywords (highest signal, most specific)
  INFERRED=$(infer_from_text "$TITLE")

  # 2. Fall back to area:* labels
  if [[ -z "$INFERRED" ]]; then
    while IFS= read -r lbl; do
      [[ -z "$lbl" ]] && continue
      RESULT=$(label_to_area "$lbl")
      if [[ -n "$RESULT" ]]; then
        INFERRED="$RESULT"
        break
      fi
    done <<< "$LABELS"
  fi

  # 3. Fall back to body keywords (broadest, most noise)
  if [[ -z "$INFERRED" ]]; then
    INFERRED=$(infer_from_text "$BODY")
  fi

  # No match
  if [[ -z "$INFERRED" ]]; then
    SKIPPED_NO_MATCH=$((SKIPPED_NO_MATCH + 1))
    echo "  ?  $DISPLAY"
    echo "     → no area inferred (labels: ${LABELS:-none})"
    continue
  fi

  OPTION_ID=$(area_option_id "$INFERRED")

  # Show what would change
  if [[ -n "$CURRENT_AREA" ]]; then
    echo "  ~  $DISPLAY"
    echo "     → $CURRENT_AREA → $INFERRED"
  else
    echo "  +  $DISPLAY"
    echo "     → $INFERRED"
  fi


  # Apply if --apply
  if [[ "$APPLY" == "true" ]]; then
    if gh api graphql -f query="
      mutation {
        updateProjectV2ItemFieldValue(input: {
          projectId: \"$PROJECT_ID\"
          itemId: \"$ITEM_ID\"
          fieldId: \"$AREA_FIELD_ID\"
          value: { singleSelectOptionId: \"$OPTION_ID\" }
        }) {
          projectV2Item { id }
        }
      }
    " > /dev/null 2>&1; then
      ASSIGNED=$((ASSIGNED + 1))
    else
      FAILED=$((FAILED + 1))
      echo "     ✗ failed to update"
    fi
  else
    ASSIGNED=$((ASSIGNED + 1))
  fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────"
if [[ "$APPLY" == "true" ]]; then
  echo "Applied:          $ASSIGNED"
  [[ $FAILED -gt 0 ]] && echo "Failed:           $FAILED"
else
  echo "Would assign:     $ASSIGNED"
fi
echo "Already set:      $SKIPPED_HAS_AREA"
echo "No match:         $SKIPPED_NO_MATCH"
echo "Total items:      $TOTAL"
echo "────────────────────────────────────────"

if [[ "$APPLY" == "false" && $ASSIGNED -gt 0 ]]; then
  echo ""
  echo "This was a dry run. Re-run with --apply to make changes."
fi

# ── Strip area:* labels from issues ──────────────────────────────────────────
if [[ "$STRIP_LABELS" == "true" ]]; then
  echo ""
  echo "Scanning for area:* labels to remove from issues..."
  STRIPPED=0
  STRIP_SKIPPED=0

  for i in $(seq 0 $((TOTAL - 1))); do
    ITEM=$(echo "$ALL_ITEMS" | jq ".[$i]")
    TYPENAME=$(echo "$ITEM" | jq -r '.content.__typename // empty')
    NUMBER=$(echo "$ITEM" | jq -r '.content.number // empty')
    TITLE=$(echo "$ITEM" | jq -r '.content.title // empty')
    LABELS=$(echo "$ITEM" | jq -r '.content.labels.nodes[]?.name // empty' 2>/dev/null || echo "")

    # Only strip from issues, not PRs or drafts
    if [[ "$TYPENAME" != "Issue" ]]; then
      continue
    fi

    # Check for area:* labels
    FOUND_AREA_LABELS=""
    while IFS= read -r lbl; do
      [[ -z "$lbl" ]] && continue
      case "$lbl" in
        area:*) FOUND_AREA_LABELS="$FOUND_AREA_LABELS $lbl" ;;
      esac
    done <<< "$LABELS"

    if [[ -z "$FOUND_AREA_LABELS" ]]; then
      continue
    fi

    echo "  -  #$NUMBER: $TITLE"
    echo "     remove:$FOUND_AREA_LABELS"

    if [[ "$APPLY" == "true" ]]; then
      for lbl in $FOUND_AREA_LABELS; do
        gh issue edit "$NUMBER" --repo "$ORG/amelia" --remove-label "$lbl" > /dev/null 2>&1 || true
      done
      STRIPPED=$((STRIPPED + 1))
    else
      STRIPPED=$((STRIPPED + 1))
    fi
  done

  echo ""
  echo "────────────────────────────────────────"
  if [[ "$APPLY" == "true" ]]; then
    echo "Labels stripped:  $STRIPPED issues"
  else
    echo "Would strip:      $STRIPPED issues"
  fi
  echo "────────────────────────────────────────"
fi
