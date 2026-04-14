"""
workers/policy_tool.py — Policy & Tool Worker
Sprint 2+3: Kiểm tra policy dựa vào context, gọi MCP tools khi cần.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: context từ retrieval_worker
    - needs_tool: True nếu supervisor quyết định cần tool call

Output (vào AgentState):
    - policy_result: {"policy_applies", "policy_name", "exceptions_found", "source", "rule"}
    - mcp_tools_used: list of tool calls đã thực hiện
    - worker_io_log: log

Gọi độc lập để test:
    python workers/policy_tool.py
"""

import os
import sys
from typing import Optional

WORKER_NAME = "policy_tool_worker"


# ─────────────────────────────────────────────
# MCP Client — Sprint 3: Thay bằng real MCP call
# ─────────────────────────────────────────────


def _call_mcp_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Gọi MCP tool và trả về trace với mcp_tool_called + mcp_result.
    """
    try:
        from mcp_server import dispatch_tool

        return dispatch_tool(tool_name, tool_input)
    except Exception as e:
        from datetime import datetime

        return {
            "mcp_tool_called": tool_name,
            "mcp_input": tool_input,
            "mcp_result": None,
            "error": {"code": "MCP_CALL_FAILED", "reason": str(e)},
            "timestamp": datetime.now().isoformat(),
        }


# ─────────────────────────────────────────────
# Policy Analysis Logic
# ─────────────────────────────────────────────


def _get_llm_client():
    """
    Trả về OpenAI client hoặc None nếu không có API key.
    """
    try:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return OpenAI(api_key=api_key)
    except ImportError:
        pass
    return None


def analyze_policy_with_llm(task: str, chunks: list) -> dict:
    """
    Phân tích policy dùng LLM (GPT-4o-mini hoặc tương đương).
    Fallback to rule-based nếu không có LLM.
    """
    client = _get_llm_client()

    if not client:
        # Fallback to rule-based
        return analyze_policy_rule_based(task, chunks)

    # Build context từ chunks
    context_text = "\n".join(
        [f"[{c.get('source', 'unknown')}] {c.get('text', '')}" for c in chunks if c]
    )

    system_prompt = """Bạn là Policy Analyst của một công ty. Nhiệm vụ của bạn là phân tích yêu cầu của khách hàng dựa trên các chính sách nội bộ.

Nhiệm vụ:
1. Xác định yêu cầu của khách hàng là gì (refund, access, ticket, v.v.)
2. Tìm các exception cases hoặc điều kiện đặc biệt:
   - Flash Sale: Đơn hàng từ chương trình Flash Sale không được hoàn tiền
   - Digital Product: Sản phẩm kỹ thuật số (license, subscription) không được hoàn tiền
   - Activated Product: Sản phẩm đã kích hoạt hoặc đăng ký không được hoàn tiền
   - Temporal scoping: Các đơn hàng trước 01/02/2026 áp dụng policy v3
3. Quyết định policy có áp dụng hay không
4. Trả về JSON response với cấu trúc rõ ràng

Response format (MUST be valid JSON):
{
    "policy_applies": boolean,
    "policy_name": string,
    "exceptions_found": [
        {
            "type": string (e.g., "flash_sale_exception", "digital_product_exception", "activated_exception"),
            "rule": string (nội dung rule cụ thể từ policy),
            "source": string (tên tài liệu)
        }
    ],
    "policy_version_note": string (ghi chú về version nếu có),
    "explanation": string (giải thích ngắn gọn lý do)
}"""

    user_message = f"""Phân tích yêu cầu sau dựa trên chính sách:

**Yêu cầu:** {task}

**Chính sách và tài liệu có liên quan:**
{context_text}

Hãy phân tích và trả về JSON response."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        analysis_text = response.choices[0].message.content
        import json

        analysis = json.loads(analysis_text)

        # Validate response format
        if isinstance(analysis, dict) and "policy_applies" in analysis:
            return analysis
        else:
            # Fallback if response is malformed
            return analyze_policy_rule_based(task, chunks)

    except Exception as e:
        print(f"⚠️  LLM analysis failed ({e}), falling back to rule-based")
        return analyze_policy_rule_based(task, chunks)


def analyze_policy_rule_based(task: str, chunks: list) -> dict:
    """
    Rule-based policy check (fallback when LLM is unavailable).
    """
    task_lower = task.lower()
    context_text = " ".join([c.get("text", "") for c in chunks]).lower()

    # --- Rule-based exception detection ---
    exceptions_found = []

    # Exception 1: Flash Sale
    if "flash sale" in task_lower or "flash sale" in context_text:
        exceptions_found.append(
            {
                "type": "flash_sale_exception",
                "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách v4).",
                "source": "policy_refund_v4.txt",
            }
        )

    # Exception 2: Digital product
    if any(
        kw in task_lower
        for kw in ["license key", "license", "subscription", "kỹ thuật số"]
    ):
        exceptions_found.append(
            {
                "type": "digital_product_exception",
                "rule": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền (Điều 3).",
                "source": "policy_refund_v4.txt",
            }
        )

    # Exception 3: Activated product
    if any(kw in task_lower for kw in ["đã kích hoạt", "đã đăng ký", "đã sử dụng"]):
        exceptions_found.append(
            {
                "type": "activated_exception",
                "rule": "Sản phẩm đã kích hoạt hoặc đăng ký tài khoản không được hoàn tiền (Điều 3).",
                "source": "policy_refund_v4.txt",
            }
        )

    # Determine policy_applies
    policy_applies = len(exceptions_found) == 0

    # Determine which policy version applies (temporal scoping)
    policy_name = "refund_policy_v4"
    policy_version_note = ""
    if "31/01" in task_lower or "30/01" in task_lower or "trước 01/02" in task_lower:
        policy_version_note = "Đơn hàng đặt trước 01/02/2026 áp dụng chính sách v3 (không có trong tài liệu hiện tại)."

    sources = list({c.get("source", "unknown") for c in chunks if c})

    return {
        "policy_applies": policy_applies,
        "policy_name": policy_name,
        "exceptions_found": exceptions_found,
        "source": sources,
        "policy_version_note": policy_version_note,
        "explanation": "Analyzed via rule-based policy check.",
    }


def analyze_policy(task: str, chunks: list) -> dict:
    """
    Phân tích policy dựa trên context chunks.

    Cố gắng dùng LLM nếu có API key, fallback to rule-based nếu không.

    Xử lý các exceptions:
    - Flash Sale → không được hoàn tiền
    - Digital product / license key / subscription → không được hoàn tiền
    - Sản phẩm đã kích hoạt → không được hoàn tiền
    - Đơn hàng trước 01/02/2026 → áp dụng policy v3 (không có trong docs)

    Returns:
        dict with: policy_applies, policy_name, exceptions_found, source, rule, explanation
    """
    return analyze_policy_with_llm(task, chunks)


# ─────────────────────────────────────────────
# Worker Entry Point
# ─────────────────────────────────────────────


def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.

    Args:
        state: AgentState dict

    Returns:
        Updated AgentState với policy_result và mcp_tools_used
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    needs_tool = state.get("needs_tool", False)

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state.setdefault("mcp_tools_used", [])

    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "needs_tool": needs_tool,
        },
        "output": None,
        "error": None,
    }

    try:
        # Step 1: Nếu chưa có chunks, gọi MCP search_kb
        if not chunks and needs_tool:
            mcp_result = _call_mcp_tool("search_kb", {"query": task, "top_k": 3})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(
                f"[{WORKER_NAME}] mcp_tool_called={mcp_result.get('mcp_tool_called')}"
            )

            kb_result = mcp_result.get("mcp_result") or {}
            if kb_result.get("chunks"):
                chunks = kb_result["chunks"]
                state["retrieved_chunks"] = chunks

        # Step 2: Phân tích policy
        policy_result = analyze_policy(task, chunks)
        state["policy_result"] = policy_result

        # Step 3: Nếu cần thêm info từ MCP (e.g., ticket status), gọi get_ticket_info
        if needs_tool and any(kw in task.lower() for kw in ["ticket", "p1", "jira"]):
            mcp_result = _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(
                f"[{WORKER_NAME}] mcp_tool_called={mcp_result.get('mcp_tool_called')}"
            )

        worker_io["output"] = {
            "policy_applies": policy_result["policy_applies"],
            "exceptions_count": len(policy_result.get("exceptions_found", [])),
            "mcp_calls": len(state["mcp_tools_used"]),
        }
        state["history"].append(
            f"[{WORKER_NAME}] policy_applies={policy_result['policy_applies']}, "
            f"exceptions={len(policy_result.get('exceptions_found', []))}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "POLICY_CHECK_FAILED", "reason": str(e)}
        state["policy_result"] = {"error": str(e)}
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Policy Tool Worker — Standalone Test")
    print("=" * 50)

    test_cases = [
        {
            "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
            "retrieved_chunks": [
                {
                    "text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền.",
                    "source": "policy_refund_v4.txt",
                    "score": 0.9,
                }
            ],
        },
        {
            "task": "Khách hàng muốn hoàn tiền license key đã kích hoạt.",
            "retrieved_chunks": [
                {
                    "text": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền.",
                    "source": "policy_refund_v4.txt",
                    "score": 0.88,
                }
            ],
        },
        {
            "task": "Khách hàng yêu cầu hoàn tiền trong 5 ngày, sản phẩm lỗi, chưa kích hoạt.",
            "retrieved_chunks": [
                {
                    "text": "Yêu cầu trong 7 ngày làm việc, sản phẩm lỗi nhà sản xuất, chưa dùng.",
                    "source": "policy_refund_v4.txt",
                    "score": 0.85,
                }
            ],
        },
    ]

    for tc in test_cases:
        print(f"\n▶ Task: {tc['task'][:70]}...")
        result = run(tc.copy())
        pr = result.get("policy_result", {})
        print(f"  policy_applies: {pr.get('policy_applies')}")
        if pr.get("exceptions_found"):
            for ex in pr["exceptions_found"]:
                print(f"  exception: {ex['type']} — {ex['rule'][:60]}...")
        print(f"  MCP calls: {len(result.get('mcp_tools_used', []))}")

    print("\n✅ policy_tool_worker test done.")
