"""Model adapters for terminal tasks. Models only ever emit bash/submit tool calls; the host runs them."""

import json
import urllib.request

SYSTEM = """You are a software engineer working in a Linux container. The task is below.
Use the bash tool to inspect files, write code and test it. Each bash call runs in /workspace with a
20-second limit; state such as `cd` does not persist between calls, but files do. There is no network.
Hidden tests grade the result after you call submit, so test your work on your own inputs first.
Call exactly one tool per response. When the task is complete, call submit with a short summary."""

TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "Run one bash command in /workspace.",
                                      "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                                                     "required": ["command"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "submit", "description": "Finish the episode.",
                                      "parameters": {"type": "object", "properties": {"summary": {"type": "string"}},
                                                     "required": ["summary"], "additionalProperties": False}}},
]


class Ollama:
    def __init__(self, model="william-qwen38-agent:latest", endpoint="http://127.0.0.1:11434", think=False):
        self.model, self.endpoint, self.think = model, endpoint, think
        self.name = "ollama:" + model

    def metadata(self):
        with urllib.request.urlopen(self.endpoint + "/api/tags", timeout=5) as response:
            found = next((m for m in json.load(response)["models"] if m["name"] == self.model), None)
        if found is None:
            raise RuntimeError("Model is not installed; nothing is downloaded")
        return {"adapter": "ollama-native-tools@1", "model": self.model, "digest": found["digest"], "think": self.think}

    def decide(self, messages, seed, timeout=180):
        payload = {"model": self.model, "messages": messages, "tools": TOOLS, "think": self.think, "stream": False,
                   "options": {"temperature": 0.7, "num_ctx": 32768, "num_predict": 4096, "seed": seed}}
        request = urllib.request.Request(self.endpoint + "/api/chat", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
        message = {k: v for k, v in result.get("message", {}).items() if k != "thinking"}
        calls = [{"name": c["function"]["name"], "arguments": c["function"].get("arguments", {})} for c in message.get("tool_calls", [])]
        usage = {"input_tokens": result.get("prompt_eval_count"), "output_tokens": result.get("eval_count")}
        return message, calls, usage

    @staticmethod
    def tool_message(name, call_id, content):
        return {"role": "tool", "tool_name": name, "content": content}


def run_model(env, adapter, seed, max_decisions=40):
    """Drive one episode. Invalid outputs consume a decision but execute nothing."""
    observation = env.reset(seed)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": observation["task"]}]
    events = []
    for decision in range(max_decisions):
        if env.terminated or env.truncated:
            break
        try:
            message, calls, usage = adapter.decide(messages, seed)
        except Exception as exc:  # provider/network failure: recorded; cli.py marks the trial status 'error'
            events.append({"decision": decision, "error": type(exc).__name__ + ": " + str(exc)[:500]})
            env.truncated, env.reason = True, "model_error"
            break
        events.append({"decision": decision, "usage": usage, "calls": len(calls), "text": (message.get("content") or "")[:2000]})
        messages.append(message)
        if len(calls) != 1:
            messages.append({"role": "user", "content": "Call exactly one tool (bash or submit)."})
            continue
        call = calls[0]
        args = call["arguments"]
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"_raw": args}
        result = env.step({"tool": call["name"], "args": args})
        messages.append(adapter.tool_message(call["name"], call.get("id"), json.dumps(result)))
    if not env.terminated and not env.truncated:
        env.truncated, env.reason = True, "decision_budget"
    return events
