# Hosting a LangGraph graph on Microsoft Foundry

The support-desk graph in this repository can run as a Microsoft Foundry hosted agent without being
rewritten. LangGraph still owns the nodes, tools, guardrails and interrupts. Foundry would own the
endpoint, the session sandbox, scale, and the Responses transcript.

This repository does not deploy that agent. `src/lcstack/foundry` is an in-process stand-in for the
host class in the articles below. It runs the real graph on the scripted model. `lcstack foundry`
prints the transcript. The manifest under [foundry/azure.yaml](../foundry/azure.yaml) is an example
and is not applied.

Sources for the hosting path:

- [Hosting your LangGraph application on Microsoft Foundry Agents](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/hosting-your-langgraph-application-on-microsoft-foundry-agents/4573342)
- [Host LangGraph agents as Foundry hosted agents](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-hosted-agents)
- [What's new in Foundry Agent Service at Ignite 2026](https://devblogs.microsoft.com/foundry/whats-new-in-foundry-agent-service-at-ignite-2026/)

Further reading for the comparison: [Foundry hosted agents in Agent Framework](https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent),
[hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents),
and [prompt agents](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/prompt-agents).
Framework concepts that are independent of Foundry are in
[langgraph-vs-microsoft-agent-framework.md](langgraph-vs-microsoft-agent-framework.md).

## What the adapter does

The live call, from the Learn article, is `ResponsesHostServer(graph).run()`. That class lives in
`langchain_azure_ai.agents.hosting` and binds HTTP. The class of the same name in
[hosting.py](../src/lcstack/foundry/hosting.py) accepts the same kind of request and returns a
Responses-shaped object. `run` raises, so a test cannot open a port. `handle_create` is the method
the Learn article names as the override point.

```python
server = ResponsesHostServer(foundry_graph(), context_for=context_for, name="support_desk")
server.handle_create({"input": "What's my balance?"}, caller_id="C-100")
```

`caller_id` is an argument, not a field the model can set. A `caller_id` inside the JSON is ignored.
The graph receives a `Customer` context built from the platform identity. For a caller signed in with
Microsoft Entra ID, Foundry scopes the session to that identity. A shared backend identity needs a
separate end-user map; this adapter assumes the platform caller is the customer.

History follows the Learn article:

| Graph | What the host sends on the next turn |
|---|---|
| Compiled with a checkpointer | The new user message only. The conversation id is the LangGraph thread |
| Compiled without a checkpointer | The stored Responses transcript plus the new message |

`langgraph.json` registers `support_desk` with no checkpointer, because the Agent Server injects one
([deployment.md](deployment.md), [scenario 22](../scenarios/22-deploying/README.md)). A Foundry host
does not inject one. Interrupts need a checkpointer, so [desk.py](../src/lcstack/foundry/desk.py)
compiles the same builder with `InMemorySaver`. A live deployment would use a durable saver. The
Learn article names `FoundryCheckpointSaver` for Foundry State Store and `CosmosDBSaver` for Cosmos DB.
This module calls neither. Conversation history is not that checkpoint.

On a checkpointed graph, `store: false` returns status 400. That is the `langchain-azure-ai` 1.3.0 rule.

An `interrupt()` becomes two output items: a `function_call` named `__hosted_agent_adapter_interrupt__`,
and an `mcp_approval_request` with `server_label` `langgraph`. Approval of a LangChain
human-in-the-loop interrupt resumes with `{"decisions": [{"type": "approve"}]}` or `reject`. Approval
of any other interrupt resumes with the original value. Rejection of any other interrupt fails the
response and does not resume the node. `function_call_output` can carry a `Command` payload with
`resume`, `update` or `goto`. `enable_response_branching=True` lets an earlier `previous_response_id`
fork the checkpoint.

`InvocationsHostServer` is the other protocol. The platform does not store that transcript. The same
session id continues graph state only when the graph has a checkpointer, and only for the same caller.

The trace hook records each LangGraph run in memory. Message text and tool arguments stay off the
record unless `record_content=True`. The live package can export OpenTelemetry to Application Insights
when the platform sets `APPLICATIONINSIGHTS_CONNECTION_STRING`. This hook does not read that variable
and does not open a socket.

## Flow

<!-- BEGIN foundry-mermaid -->
```mermaid
flowchart TD
  caller["Caller authenticated with Entra ID"] --> endpoint["Foundry hosted agent endpoint"]
  endpoint --> adapter["ResponsesHostServer adapter"]
  adapter --> conversation["Conversation store for messages and response ids"]
  adapter --> session["Session sandbox and filesystem"]
  adapter --> graph["support_desk graph"]
  graph --> tools["Tools, guardrails and interrupts"]
  adapter --> traces["Trace hook"]
  traces --> insights["Application Insights and the Foundry portal"]
```
<!-- END foundry-mermaid -->

The conversation store and the session sandbox are different. Reusing a session id starts a new
conversation. The trace view in the portal is a view of captured operations, not a replacement for
the LangGraph definition.

## Transcript

Produced by `lcstack foundry` with the scripted model. Regenerate with `python scripts/render_docs.py`.

<!-- BEGIN foundry-demo -->
```text
Kestrel Ridge Bank - support desk as a Microsoft Foundry hosted agent
offline stand-in, azure calls: 0, deployed: no

ResponsesHostServer wraps the existing support_desk graph.
langgraph.json export checkpointer: none
Foundry copy checkpointer: InMemorySaver
A checkpointed graph is sent the new turn only. The Responses conversation is not a graph checkpoint.

protocol probe (counter graph, not a client agent):
  checkpointer turn 1: turns=1 last=alpha (checkpointer)
  checkpointer turn 2 via previous_response_id: turns=2 last=beta
  same session id, new conversation: turns=1 last=beta conversation_changed=True
  no checkpointer turn 2 via previous_response_id: turns=2 last=beta (responses)
  store false on a checkpointed graph: 400 a checkpointed graph must omit store or set it to true

support desk:
  [C-100] What's my balance? -> The balance on your account is 1240.55.
  [C-100] body caller_id ignored -> The balance on your account is 1240.55.
  [C-200] What's my balance? -> The balance on your account is 88.10.
  [C-100] What are the wire transfer cutoff times?
    Domestic wires sent before 4:30 pm Eastern on a business day arrive the same day. International wires are sent the same day if requested before 2:00 pm Eastern and usually arrive in one to three business days. (source: wire-transfers.md)
  [C-100] Please refund the overdraft fee -> incomplete function_call __hosted_agent_adapter_interrupt__, mcp_approval_request server_label=langgraph name=issue_fee_refund ledger=[]
  [C-100] approve -> Done: the 35.00 overdraft fee has been refunded to your account. ledger=['fee_refund C-100 35.0']
  [C-100] injection -> I can't act on instructions like that. I can help with your accounts, cards and Kestrel's policies. ledger_grew=False
  message text in trace: no
  tools traced: get_account_summary, issue_fee_refund, list_transactions, search_kb

Invocations protocol (the platform does not store the transcript):
  no checkpointer, same session: turns=1 last=alpha | turns=1 last=beta
  checkpointer, same session: turns=1 last=alpha | turns=2 last=beta
  same session id, other caller: turns=1 last=beta

foundry/azure.yaml
  valid example (not applied, no credentials)
  host: azure.ai.agent  kind: hosted  protocol: responses
  entry point compiles support_desk with a checkpointer; the langgraph.json copy has none
```
<!-- END foundry-demo -->

## Manifest

[foundry/azure.yaml](../foundry/azure.yaml) follows the `azure.yaml` shape in the hosting articles:
`host: azure.ai.agent`, `kind: hosted`, `PYTHONNOUSERSITE: "1"`, runtime `python_3_13`. The entry
point is `python -m lcstack.foundry.serve --protocol responses`, because that module compiles the
checkpointer in. A messages-only graph with no interrupts can use
`python -m langchain_azure_ai.agents.hosting.run support_desk --protocol responses` instead.
`FOUNDRY_PROJECT_ENDPOINT` is left unset; the platform injects it. `LCSTACK_MODEL` stays `scripted`
so this example cannot be read as a live model call. `AZURE_AI_MODEL_DEPLOYMENT_NAME` is the sample
name from the Learn article (`gpt-4.1`). Deploying needs the Foundry Project Manager role and
`azd`; neither is used here.

## LangGraph hosted agent or Agent Framework on Foundry

Foundry Agent Service has two ways to bring your own code, plus a path that brings no orchestration
code. Hosted agents are described as generally available. The Python Agent Framework hosting package
is called out separately below.

| Path | What you bring | What runs the loop |
|---|---|---|
| LangGraph hosted agent | A compiled graph. This repository's support desk | LangGraph. The host exposes `/responses` or `/invocations` |
| Agent Framework hosted agent | An `Agent`, or a native workflow | Agent Framework. Python uses `ResponsesHostServer` from `agent_framework_foundry_hosting`. .NET uses `AgentHost` and `AddFoundryResponses` |
| Prompt agent | Instructions, a model, and Foundry tools | Foundry. The Microsoft Copilot harness is the managed loop for long-running tool use, and it is public preview [verify] |

### When I choose

| Situation | Choose |
|---|---|
| The graph, its interrupts and its tests already exist | LangGraph hosted agent |
| The team ships Python and .NET, or the workflow is already Agent Framework executors | Agent Framework hosted agent |
| The behavior is instructions plus Foundry tools, and there is no graph to keep | Prompt agent |
| Reducers, time travel, or a fork from an earlier checkpoint matter | LangGraph hosted agent, with a checkpointer and response branching |
| Group chat, Magentic, or typed messages between executors are the model | Agent Framework hosted agent |
| The caller sends a webhook body or a non-chat JSON document | Invocations, on either hosted path |
| LangSmith datasets and a regression gate already decide releases | Keep them. Foundry evaluations sit beside that gate |
| The client wants the Agent Server API: threads, runs, crons | Scenario 22 and [deployment.md](deployment.md) |

### What hosting does not erase

| | LangGraph on Foundry | Agent Framework on Foundry |
|---|---|---|
| Unit you deploy | Compiled graph | Agent, or a native workflow |
| Host entry, Python | `langchain_azure_ai.agents.hosting.ResponsesHostServer` | `agent_framework_foundry_hosting.ResponsesHostServer`. The Python package is prerelease [verify] |
| How the next turn gets history | Checkpointer present or absent | `history_source` of `agent_server`, `service`, or `agent`, as the Agent Framework hosting article describes it |
| Resume | `interrupt` and `Command` | Request-info events, or workflow responses on a native workflow |
| Languages for this hosting path | Python in the LangGraph article | Python and .NET |
| Traces | LangSmith, and OpenTelemetry into Foundry when configured | OpenTelemetry into Foundry and Application Insights |

The .NET package `Microsoft.Agents.AI.Foundry.Hosting` is installed with `--prerelease` [verify].

### What Foundry takes on, for either hosted path

| Foundry | The team that owns the agent |
|---|---|
| Endpoint, session sandbox, scale, including scale to zero after the idle timeout | Graph or workflow, tools, prompts, business rules |
| Entra identity of the agent, and session scope for a direct caller | The end-user map when one backend identity calls Foundry for many people |
| Responses transcript | A LangGraph or Agent Framework checkpoint, when runtime state is more than the transcript |
| A content-safety policy attached to the agent definition | Allowlists, input screens, and human approval of side effects. A filter on the endpoint does not prove those checks ran |
| Trace viewer, once tracing is connected | Whether message content and tool arguments are stored, and who can open the trace |
| Evaluations you configure | The decision to release a change |

The Ignite 2026 post describes idle timeout as configurable per agent version, 15 minutes by default,
from 2 minutes up to 4 hours. It describes long-running recovery as generally available and as a rerun
of the handler, so a tool that moves money or writes a record has to be idempotent. The same post
describes network egress controls, shared subnet addresses for sessions, and production Insights
(including LangGraph and LangChain traces) as generally available. Insights are a reading of captured
traces. They do not replace the graph.

Memory snapshots of a sandbox are public preview [verify]. They shorten a cold start. They are not a
graph checkpoint. State that must survive idle time still goes to a durable saver.

## Check these before you depend on them

Each line below carries `[verify]`: confirm the current page before you depend on the item.

- Microsoft Copilot harness, public preview [verify]
- Python package `agent-framework-foundry-hosting`, prerelease [verify]
- .NET package `Microsoft.Agents.AI.Foundry.Hosting`, installed with `--prerelease` [verify]
- Memory snapshots, public preview [verify]
- Private certificate authority trust, public preview [verify]
- Azure Policy governance of egress settings, public preview [verify]
- Hosted agents on a customer-owned AKS cluster, coming soon [verify]
- Custom MCP on-behalf-of configuration, preview [verify]
- Agent metrics on the Monitor tab, preview in the LangGraph hosting post [verify]
- Annotations on traces, public preview [verify]
- Evaluation datasets built from those annotations, preview [verify]
- Sending an insight to Agent Optimizer, preview [verify]
- Skill optimization, preview [verify]
- Cost optimization, public preview [verify]
- Recurring evaluations and alerts, preview [verify]
- Work IQ and Fabric IQ, preview [verify]
- Toolbox tool policies, preview [verify]
- Browser automation into private networks, preview [verify]

## Interview points

- Keep the graph when the graph is already tested. Foundry hosts it. Agent Framework is the path when the code is already Agent Framework, or when .NET is part of the deliverable.
- A Responses transcript and a LangGraph checkpoint answer different questions. Interrupts need the checkpoint.
- A session id selects a sandbox. It does not restore the chat.
- Identity for a tool comes from the platform caller, via `context`. Text in the message is not that identity.
- Human-in-the-loop approval becomes a middleware decision. Rejection of a raw `interrupt()` stops the response.
- Tracing can be on while message content stays off the record.
- Content safety on the Foundry definition sits beside the graph's own screens. One does not stand in for the other.
- Recovery that reruns a handler needs idempotent tools. That is the same rule as resuming a LangGraph node.
- The manifest in this repository is an example. Shipping it means a Foundry project, the hosting package, and a decision you can point at in traces and evaluations.

Names marked `[verify]` were preview or prerelease in the posts linked above. Read the current documentation before treating one as a commitment.
