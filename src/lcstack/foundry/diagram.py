"""Mermaid diagram of the Foundry hosted-agent path. The docs page embeds this string."""

MERMAID = """\
flowchart TD
  caller["Caller authenticated with Entra ID"] --> endpoint["Foundry hosted agent endpoint"]
  endpoint --> adapter["ResponsesHostServer adapter"]
  adapter --> conversation["Conversation store for messages and response ids"]
  adapter --> session["Session sandbox and filesystem"]
  adapter --> graph["support_desk graph"]
  graph --> tools["Tools, guardrails and interrupts"]
  adapter --> traces["Trace hook"]
  traces --> insights["Application Insights and the Foundry portal"]
"""
