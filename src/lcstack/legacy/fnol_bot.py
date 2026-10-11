"""LEGACY: Ferrowind's original first-notice-of-loss bot, written in the pre-1.0 style.

AgentExecutor + create_tool_calling_agent, an LLMChain for summaries and ConversationBufferMemory for
history. Kept to prove the migrated version behaves the same (tests/test_s24_migration.py).
"""

from __future__ import annotations

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_classic.chains.llm import LLMChain
from langchain_classic.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate


def legacy_executor(model, tools) -> AgentExecutor:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You take first notice of loss for Ferrowind Insurance."),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(model, tools, prompt)
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    return AgentExecutor(agent=agent, tools=tools, memory=memory, return_intermediate_steps=True)


def legacy_summary_chain(model) -> LLMChain:
    return LLMChain(llm=model, prompt=PromptTemplate.from_template("Summarize this claim for the adjuster: {text}"))
