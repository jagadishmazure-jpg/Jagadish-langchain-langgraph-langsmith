"""Model factory: the scripted model by default, a real provider when ``LCSTACK_MODEL`` says so.

    LCSTACK_MODEL unset / "scripted"  -> ScriptedChatModel (offline, deterministic, used by CI and tests)
    LCSTACK_MODEL=azure               -> AzureChatOpenAI with a Microsoft Entra ID token (no API key):
                                         AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, OPENAI_API_VERSION
    LCSTACK_MODEL=<provider:model>    -> init_chat_model("<provider:model>"), e.g. "openai:gpt-4.1-mini"
                                         or "anthropic:claude-sonnet-4-5"; the provider package and its
                                         own credential variable must be present

The same rules apply to embeddings through ``LCSTACK_EMBEDDINGS`` ("hashing", "azure" or a
"provider:model" string for ``init_embeddings``). Real models are documented and wired, never required.
Scenario outputs in the docs come from the scripted model; with a real model the wording will differ.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from lcstack.core.embeddings import HashingEmbeddings
from lcstack.core.scripted import Playbook, scripted

AZURE_SCOPE = "https://cognitiveservices.azure.com/.default"


def model_choice() -> str:
    return (os.getenv("LCSTACK_MODEL") or "scripted").strip()


def is_scripted() -> bool:
    return model_choice() in {"scripted", "fake", ""}


def _entra_token_provider():
    # Lazy import: azure-identity is an optional extra ([azure]).
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    return get_bearer_token_provider(DefaultAzureCredential(), AZURE_SCOPE)


def azure_chat_model(**kwargs: Any) -> BaseChatModel:
    """Azure OpenAI / Foundry deployment, authenticated with Entra ID (managed identity, az login, workload identity)."""
    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        api_version=os.getenv("OPENAI_API_VERSION", "2024-10-21"),
        azure_ad_token_provider=_entra_token_provider(),
        temperature=0,
        **kwargs,
    )


def chat_model(playbook: Playbook | None = None, *, name: str = "scripted", fail_times: int = 0) -> BaseChatModel:
    """Return the chat model for a scenario. ``playbook`` only matters for the scripted model."""
    choice = model_choice()
    if is_scripted():
        return scripted(playbook, name=name, fail_times=fail_times)
    if choice == "azure":
        return azure_chat_model()
    from langchain import chat_models

    return chat_models.init_chat_model(choice, temperature=0)


def embeddings() -> Embeddings:
    choice = (os.getenv("LCSTACK_EMBEDDINGS") or "hashing").strip()
    if choice == "hashing":
        return HashingEmbeddings()
    if choice == "azure":
        from langchain_openai import AzureOpenAIEmbeddings

        return AzureOpenAIEmbeddings(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_deployment=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            api_version=os.getenv("OPENAI_API_VERSION", "2024-10-21"),
            azure_ad_token_provider=_entra_token_provider(),
        )
    from langchain.embeddings import init_embeddings

    return init_embeddings(choice)
