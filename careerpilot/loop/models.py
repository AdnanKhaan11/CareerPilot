from __future__ import annotations
import json
import os
from dataclasses import dataclass
from types import SimpleNamespace
from careerpilot.config.settings import Settings


@dataclass(frozen=True)
class Provider:
    kind: str  # anthropic or openai
    key_env: str  # which env var holds the key
    base_url: str | None
    model: str  # default main model
    small_model: str  # default cheap model (retrieval gate + consolidation)
    catalog_url: str | None = None
    flagship: str = ""
    fast: str = ""

    def default_pair(self) -> list[str]:
        """[flagship, fast], deduped — the switcher's default picks."""
        pair = [self.flagship or self.model, self.fast or self.small_model]
        return list(dict.fromkeys(m for m in pair if m))


PROVIDERS: dict[str, Provider] = {
    "anthropic": Provider(
        "anthropic",
        "ANTHROPIC_API_KEY",
        None,
        "claude-sonnet-5",
        "claude-haiku-4-5-20251001",
        catalog_url="https://api.anthropic.com/v1/models",
        flagship="claude-opus-4-8",
        fast="claude-sonnet-5",
    ),
    "openai": Provider(
        "openai",
        "OPENAI_API_KEY",
        None,
        "gpt-5.3-chat-latest",
        "gpt-4.1-mini",
        catalog_url="https://api.openai.com/v1/models",
    ),
    "openrouter": Provider(
        "openai",
        "OPENROUTER_API_KEY",
        "https://openrouter.ai/api/v1",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "google/gemma-4-26b-a4b-it:free",
    ),
    "gemini": Provider(
        "openai",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        flagship="gemini-3.1-pro-preview",
        fast="gemini-3.5-flash",
    ),
    "deepseek": Provider(
        "openai",
        "DEEPSEEK_API_KEY",
        "https://api.deepseek.com",
        "deepseek-v4-pro",
        "deepseek-v4-pro",
    ),
    "minimax": Provider(
        "anthropic",
        "MINIMAX_API_KEY",
        "https://api.minimaxi.com/anthropic",
        "MiniMax-M3",
        "MiniMax-M2",
    ),
    "kimi": Provider(
        "anthropic",
        "MOONSHOT_API_KEY",
        "https://api.moonshot.ai/anthropic",
        "kimi-k3",
        "kimi-k2.6",
        catalog_url="https://api.moonshot.ai/v1/models",
        flagship="kimi-k3",
        fast="kimi-k2.7-code-highspeed",
    ),
    "glm": Provider(
        "anthropic",
        "ZHIPU_API_KEY",
        "https://api.z.ai/api/anthropic",
        "glm-5.2",
        "glm-5-turbo",
    ),
    "xai": Provider(
        "openai",
        "XAI_API_KEY",
        "https://api.x.ai/v1",
        "grok-4",
        "grok-4-fast",
        catalog_url="https://api.x.ai/v1/models",
    ),
    "groq": Provider(
        "openai",
        "GROQ_API_KEY",
        "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ),
}


def get_client(settings: Settings):
    provider = PROVIDERS.get(settings.provider)
    if provider is None:
        raise SystemExit(
            f"Unknown CAREERPILOT_PROVIDER '{settings.provider}'."
            f" pick one of: {','.join(PROVIDERS)}"
        )

    api_key = (settings.api_key or os.getenv(provider.key_env, "")).strip()
    if not api_key:
        raise SystemExit(f"no api key for provider {settings.provider}")

    try:
        api_key.encode("latin-1")
    except UnicodeEncodeError:
        raise SystemExit(
            f"{provider.key_env} contains a non-ASCII character (e.g. a smart quote "
            f"or arrow from a bad paste). Re-paste the key with no spaces or line breaks."
        )

    settings.model = settings.model or provider.model
    settings.small_model = settings.small_model or provider.small_model
    base_url = settings.base_url or provider.base_url
    timeout = float(os.getenv("CAREERPILOT_TIMEOUT", "120"))

    if provider.kind == "anthropic":
        import anthropic

        kwargs: dict = {"api_key": api_key, "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        return anthropic.Anthropic(**kwargs)

    return OpenAICompatClient(api_key=api_key, base_url=base_url, timeout=timeout)


def _parse_tool_arguments(raw: str | None) -> dict:
    """Some providers (seen with Groq) emit the literal string "null"
    for a no-argument tool call, instead of "{}" — json.loads("null")
    correctly returns None, which then crashes any tool function
    expecting a dict. This normalizes both cases to a real empty dict.
    """
    if not raw or raw == "null":
        return {}
    parsed = json.loads(raw)
    return parsed if parsed is not None else {}


class OpenAICompatClient:
    def __init__(
        self, api_key: str, base_url: str | None = None, timeout: float = 120.0
    ):
        import openai

        self._client = openai.OpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout
        )
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    def _to_openai(self, *, model, messages, max_tokens, system=None, tools=None):
        """Translator and packager. Takes the conversation stored in
        Anthropic's format, converts every message into OpenAI's format,
        wraps everything (model, messages, token limit, tools) into a
        single kwargs dict, and hands that package to _call().
        """
        oai_messages = []

        # System prompt.
        if system:
            oai_messages.append({"role": "system", "content": system})

        # messages is the WHOLE conversation.
        for message in messages:
            content = message["content"]

            if isinstance(content, str):
                oai_messages.append({"role": message["role"], "content": content})

            # If the message belongs to the assistant, we separate text
            # from tool calls, because OpenAI stores these separately.
            elif message["role"] == "assistant":
                # Assistant content is a list of blocks, e.g. TextBlock, ToolUseBlock.
                # getattr means: if b.type exists return it, else return "" —
                # if we wrote b.type directly and it didn't exist, this crashes.
                text = "".join(
                    b.text for b in content if getattr(b, "type", "") == "text"
                )
                calls = []
                for b in content:
                    if getattr(b, "type", "") != "tool_use":
                        continue
                    # Why hardcode "function"? Because OpenAI tool calls
                    # require "type":"function" — like a government form
                    # that says "Gender: male, female" — we don't invent
                    # "boy" or "girl", we follow the required format.
                    call = {
                        "id": b.id,
                        "type": "function",
                        "function": {"name": b.name, "arguments": json.dumps(b.input)},
                    }
                    extra = getattr(b, "extra", None)
                    if extra:
                        call["extra_content"] = extra
                    calls.append(call)

                # built once per message, after collecting every block —
                # not once per tool call, or a 2-tool-call turn would
                # duplicate the assistant entry.
                entry: dict = {"role": "assistant", "content": text or None}
                if calls:
                    entry["tool_calls"] = calls
                oai_messages.append(entry)

            else:
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        oai_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": block["tool_use_id"],
                                "content": block["content"],
                            }
                        )
        # Great! I have translated everything. How do I package it so I can send it to the OpenAI API?
        kwargs: dict = {
            "model": model,
            "messages": oai_messages,
            "max_completion_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]
        return kwargs

    # this function nactuially called the openai model
    def _call(self, kwargs: dict, **extra):
        try:
            return self._client.chat.completions.create(**kwargs, **extra)
        except Exception as exc:
            m = str(exc).lower()
            if (
                "max_completion_tokens" not in m
                and "max_tokens" not in m
                and "tool_use_failed" not in m
            ):
                raise
            if "tool_use_failed" in m:
                # Some Groq-hosted models occasionally emit a tool call as
                # literal text instead of the API's structured format, which
                # Groq then rejects outright rather than returning as plain
                # text. Retrying once without tools lets the model at least
                # reply normally instead of crashing the whole turn.
                k = dict(kwargs)
                k.pop("tools", None)
                return self._client.chat.completions.create(**k, **extra)
            k = dict(kwargs)
            k["max_tokens"] = k.pop("max_completion_tokens", None)
            return self._client.chat.completions.create(**k, **extra)

    def _create(self, *, model, messages, max_tokens, system=None, tools=None):
        """Reverse translator. Takes OpenAI's response, converts its text,
        tool calls, token usage, and stop reason into Anthropic's response
        format, and returns an object the agent loop can use without
        knowing which provider actually generated the response.
        """
        response = self._call(
            self._to_openai(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
            )
        )

        if not getattr(response, "choices", None):
            err = getattr(response, "error", None) or "endpoint returned no choices"
            raise RuntimeError(f"{model}: {err}")

        choice = response.choices[0].message
        blocks = []

        if choice.content:
            blocks.append(SimpleNamespace(type="text", text=choice.content))

        # Loop through every tool call returned by OpenAI.
        # .tool_calls comes from OpenAI's response.
        # why use "or []" suppose OpenAI return None then this carsh so we return [] so that its never crash
        # and after that  it will be go next
        # Where does it go next?
        # will now be converted into an Anthropic tool block because our agent
        #  loop only understands Anthropic format.
        for call in choice.tool_calls or []:
            blocks.append(
                SimpleNamespace(
                    type="tool_use",
                    id=call.id,
                    name=call.function.name,
                    input=_parse_tool_arguments(call.function.arguments),
                    extra=getattr(call, "extra_content", None),
                )
            )

        usage = getattr(response, "usage", None)
        return SimpleNamespace(
            stop_reason="tool_use" if choice.tool_calls else "end_turn",
            # We're converting OpenAI's usage into Anthropic's usage format.
            usage=SimpleNamespace(
                input_tokens=getattr(usage, "prompt_tokens", 0),
                output_tokens=getattr(usage, "completion_tokens", 0),
            ),
            content=blocks,
        )

    def _stream(self, *, model, messages, max_tokens, system=None, tools=None):
        """Convert Anthropic-style request into OpenAI format and start
        streaming. Returns an _OpenAIStream that behaves like Anthropic's
        messages.stream(), so the agent loop doesn't know whether it's
        talking to Anthropic or OpenAI.
        """

        # Convert Anthropic request format into OpenAI request format.
        kwargs = self._to_openai(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
        )
        return _OpenAIStream(self, kwargs)


class _OpenAIStream:
    """Acts like Anthropic's streaming API but internally uses OpenAI's
    stream.

    Responsibilities:
    1. Receive text chunks from OpenAI.
    2. Receive tool call chunks.
    3. Rebuild complete tool calls.
    4. Store token usage.
    5. Return one final Anthropic-style response.
    """

    def __init__(self, client: OpenAICompatClient, kwargs: dict):
        """
        Prepare everything needed for streaming.

        client -> OpenAI client used to make API calls.
        kwargs -> Request (model, messages, tools, etc.)
        """
        # Save OpenAI client.
        # Later text_stream() will use it to make the API request.
        self._client = client

        # Save the converted OpenAI request.
        self._kwargs = kwargs

        # During streaming, text arrives in small pieces.
        # Example:
        #   "Hel"
        #   "lo"
        #
        # We collect all pieces here and join them later.
        self._text: list[str] = []

        # Streaming tool calls also arrive in pieces.
        #
        # Key   -> tool index (0,1,2...)
        # Value -> {
        #            id,
        #            name,
        #            args
        #         }
        #
        # We gradually rebuild each tool call here.
        self._tools: dict[int, dict] = {}

        # Stores token usage when OpenAI sends it.
        self._usage = None

    def __enter__(self):
        """Allows:

        with _OpenAIStream(...) as stream:

        Returns this object itself.
        """

        return self

    def __exit__(self, *exc):
        return False  # never suppress exceptions

    @property
    def text_stream(self):
        """
        Streams text exactly like Anthropic.

        This generator:
        - receives streaming chunks
        - yields text immediately
        - rebuilds tool calls
        - stores usage information
        """
        # Start OpenAI streaming request.
        stream = self._client._call(
            self._kwargs,
            stream=True,
            # Ask OpenAI to also send token usage.
            stream_options={
                "include_usage": True
            },  # ask OpenAI to also send token usage
        )
        # Read streaming response one chunk at a time.
        for chunk in stream:
            # Some chunks contain token usage.
            # Save it for the final response.
            if getattr(chunk, "usage", None):
                self._usage = chunk.usage
            #
            # Some chunks contain only usage.
            # No text, no tool calls.

            if not chunk.choices:  # Skip Usage-only Chunk
                continue  # usage-only chunk, no text/tool content
            # delta = the NEW piece generated by the model.
            # (Streaming sends only new pieces, not the whole answer.)
            # streaming does not only send "hello" it send chunk like chunk 1: "he", chunk 2: "ll" 3: "o"
            # Each new piece(chunk) is called delta
            delta = chunk.choices[0].delta
            # If this chunk contains text..
            if getattr(delta, "content", None):
                # Save it.
                self._text.append(delta.content)
                # Immediately send it to whoever is reading the stream.

                # yield returns ONE piece and pauses.
                # Next iteration resumes from here.
                yield delta.content

            # Some chunks contain tool calls instead of text.
            for tc in getattr(delta, "tool_calls", None) or []:
                # Get existing tool entry.

                # If it doesn't exist,
                # create a new empty one.
                slot = self._tools.setdefault(
                    tc.index, {"id": None, "name": "", "args": ""}
                )
                # Tool ID may arrive separately.
                if tc.id:
                    slot["id"] = tc.id
                # Tool name may arrive separately.
                if tc.function and tc.function.name:
                    slot["name"] = tc.function.name

                # Tool arguments usually arrive in multiple chunks.
                #
                # Example:
                #
                # Chunk 1:
                # {"city"
                #
                # Chunk 2:
                # :"London"}
                #
                # += gradually rebuilds the complete JSON string.
                if tc.function and tc.function.arguments:
                    slot["args"] += tc.function.arguments

    def get_final_message(self):
        """Build one complete Anthropic-style response after streaming
        finishes, from the accumulated text, tool calls, and usage.

        Converts:
                    text pieces
                    tool pieces
                    usage

                into the same format returned by _create().
        """
        blocks = []
        # Join all streamed text into one string.
        text = "".join(self._text)
        # Add assistant text block.
        if text:
            blocks.append(SimpleNamespace(type="text", text=text))
        # Convert rebuilt tool calls into Anthropic tool_use blocks.
        for slot in self._tools.values():
            blocks.append(
                SimpleNamespace(
                    type="tool_use",
                    id=slot["id"],
                    name=slot["name"],
                    # Tool arguments were rebuilt as a JSON string.
                    # Convert them back into a Python dictionary.
                    input=_parse_tool_arguments(slot["args"]),
                )
            )

        usage = self._usage
        # Return a response that looks exactly like
        # Anthropic's Messages API response.
        return SimpleNamespace(
            # If tool calls exist, tell the agent loop
            # that tools should be executed next.
            stop_reason="tool_use" if self._tools else "end_turn",
            # Convert OpenAI usage names into Anthropic usage names.
            usage=SimpleNamespace(
                input_tokens=getattr(usage, "prompt_tokens", 0),
                output_tokens=getattr(usage, "completion_tokens", 0),
            ),
            # Final text + tool blocks.
            content=blocks,
        )
