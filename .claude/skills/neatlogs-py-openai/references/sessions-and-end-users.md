# Sessions & End-Users

Lineage is modeled with `parent_session_id`. Application-specific session data is
not hardcoded into SDK parameters: pass any JSON-compatible keys through
`session_custom_fields={...}`. The SDK stores that object as
`neatlogs.session.custom_fields` on the root span. For example:

```python
with neatlogs.identify(
    session_id="child_123",
    parent_session_id="parent_456",
    session_custom_fields={"feature_name": "chat", "entry_point": "slack", "tenant": "acme"},
    end_user_id="u_456",
):
    run_turn()
```


Attach a session and end-user to your traces to turn them into customer analytics: usage, cost, and errors per user and per segment, multi-turn conversation timelines, and per-customer support replay.

## The Model

- **One turn = one trace.** Each user message → one LLM call → one trace.
- **A session groups the turns of a conversation.** Pass the SAME `session_id` on every turn to stitch them into one timeline.
- **End-user is per session.** Pass the SAME `end_user_id` on every turn; `end_user_metadata` (plan, tier, etc.) rides along for segmentation.
- **Identity is stamped on the ROOT only.** The backend rolls it up for the whole trace; child spans ignore identity, so you only set it once per turn.

`neatlogs.init()` does NOT take session/end-user params. Its `user_id` is the SDK operator (you), not your app's users.

## This Skill's Path: `wrap()` + `identify()`

This skill instruments OpenAI with `neatlogs.wrap(OpenAI())`, which gives the wrapped call an auto-root. Bind identity per turn with `neatlogs.identify(...)` around the wrapped call — the auto-root inherits the session and end-user:

```python
import neatlogs
from openai import OpenAI

neatlogs.init(api_key="...", project="chatbot")
client = neatlogs.wrap(OpenAI())

def chat_session(session_id, end_user_id, user_messages):
    history = []
    for message in user_messages:                       # each iteration = one turn = one trace
        history.append({"role": "user", "content": message})
        with neatlogs.identify(
            session_id=session_id,                      # SAME every turn → groups the conversation
            end_user_id=end_user_id,                    # SAME every turn → same end-user
            end_user_metadata={"plan": "pro"},
        ):
            resp = client.chat.completions.create(model="gpt-4o", messages=history)
        reply = resp.choices[0].message.content
        history.append({"role": "assistant", "content": reply})

chat_session("conv_123", "u_456", ["Hi", "What's my order status?", "Thanks!"])
```

## If the App Opens Its Own Root

If a turn is already wrapped in your own root (`@neatlogs.span(kind="WORKFLOW")` or `with neatlogs.trace(...)`), skip `identify()` and pass identity to the root directly instead:

```python
with neatlogs.trace("chat_turn", session_id="conv_123", end_user_id="u_456", end_user_metadata={"plan": "pro"}):
    resp = client.chat.completions.create(model="gpt-4o", messages=history)
```

## Filter & Analyze

The dashboard has End-user and Session filters — use them to scope usage, cost, errors, and replay to a single customer or a whole conversation.
