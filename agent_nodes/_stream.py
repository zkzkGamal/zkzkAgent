"""Shared helper for streaming an LLM reply to stdout, live, for the CLI."""


def stream_to_stdout(stream):
    """Print an assistant reply token-by-token as it streams.

    The "[AI]: " header is deferred until the first chunk that actually carries
    text, so turns that only emit tool calls (no prose) don't leave a dangling
    empty "[AI]:" line — which made the CLI look like it was dropping replies.

    Returns the accumulated message chunk (with tool_calls preserved) or None
    if the stream produced nothing at all.
    """
    response = None
    started = False
    for chunk in stream:
        response = chunk if response is None else response + chunk
        if chunk.content:
            if not started:
                print("\n[AI]: ", end="", flush=True)
                started = True
            print(chunk.content, end="", flush=True)
    if started:
        print("\n")
    return response
