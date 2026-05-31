from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from pydantic import BaseModel as PydanticModel


class LLMUtils:
    """Utilities for invoking LLMs with prompts from node code."""

    @staticmethod
    async def invoke(
        llm: BaseChatModel,
        template: str,
        variables: dict | None = None,
        system: str | None = None,
    ) -> AIMessage:
        """Render a template with variables and invoke the LLM."""
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        rendered = template.format(**(variables or {}))
        messages.append(HumanMessage(content=rendered))
        return await llm.ainvoke(messages)

    @staticmethod
    async def chat(
        llm: BaseChatModel,
        messages: list[BaseMessage],
        system: str | None = None,
    ) -> AIMessage:
        """Invoke LLM with a raw message list."""
        if system:
            messages = [SystemMessage(content=system)] + messages
        return await llm.ainvoke(messages)

    @staticmethod
    async def invoke_structured(
        llm: BaseChatModel,
        template: str,
        variables: dict | None = None,
        output_schema: type[PydanticModel] = None,
        system: str | None = None,
    ) -> PydanticModel:
        """Invoke LLM and parse response into a Pydantic model."""
        structured_llm = llm.with_structured_output(output_schema)
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        rendered = template.format(**(variables or {}))
        messages.append(HumanMessage(content=rendered))
        return await structured_llm.ainvoke(messages)

    @staticmethod
    async def invoke_with_tools(
        llm: BaseChatModel,
        messages: list[BaseMessage],
        tools: list,
        system: str | None = None,
    ) -> AIMessage:
        """Invoke LLM with tool bindings."""
        llm_with_tools = llm.bind_tools(tools)
        if system:
            messages = [SystemMessage(content=system)] + messages
        return await llm_with_tools.ainvoke(messages)
