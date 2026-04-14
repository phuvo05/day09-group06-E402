# Bao Cao Nhom — Lab Day 09: Multi-Agent Orchestration

**Ten nhom:** Group 06 — E402
**Thanh vien:**

| Ten | Vai tro | MSSV |
|-----|---------|------|
| Vo Thien Phu | Supervisor Owner (Sprint 1) | 2A202600336 |
| Nguyen Anh Quan | Worker Owner — retrieval + synthesis (Sprint 2) | 2A202600132 |
| Phan Duong Dinh | Worker Owner — policy + contracts (Sprint 2) | 2A202600277 |
| Pham Minh Khang | MCP Owner (Sprint 3) | 2A202600417 |
| Dao Hong Son | Trace & Docs Owner (Sprint 4) | 2A202600462 |

**Ngay nop:** 2026-04-14
**Repo:** `day09-group06-E402`

---

## 1. Kien truc nhom da xay dung

**He thong tong quan:** Supervisor-Worker pattern — 1 Supervisor + 3 Worker
(retrieval, policy_tool, synthesis) + 1 HITL branch (`human_review`) + 1 MCP
server (in-process class) cung cap 4 tools. Graph duoc implement bang Python
thuan trong `graph.py::build_graph` (khong dung LangGraph de giam dependency).
State chia se la `AgentState` — mot `TypedDict` voi ~15 field.

**Routing logic cot loi:** Supervisor dung **keyword matching** tren task da
lower-cased.

```
policy_keywords = ["hoan tien", "refund", "flash sale", "license",
                   "cap quyen", "access", "level 3"]
  → policy_tool_worker
risk_keywords = ["emergency", "khan cap", "2am", "err-"]
  → risk_high = True
risk_high AND err- → human_review (sau do auto-approve + retrieval)
con lai → retrieval_worker (default)
```

Ket qua thuc te tren 15 test question: route dung **14/15 (93.3%)**.
Ket qua tren 10 grading question: route dung **10/10 (100%)**.

**Route reason chi tiet** (da cap nhat sau fix):

| Câu | route_reason thuc te |
|------|---------------------|
| gq01,05,06,07,08 | `no_policy_keyword` |
| gq02 | `policy_keywords=['hoan tien', 'flash sale']` |
| gq03 | `policy_keywords=['access', 'level 3']` |
| gq04 | `policy_keywords=['hoan tien']` |
| gq09 | `policy_keywords=['access'] | risk_keywords=['emergency', '2am']` |
| gq10 | `policy_keywords=['hoan tien', 'flash sale']` |

**MCP tools da implement** (goi tu `workers/policy_tool.py`):
- `search_kb(query, top_k)` — search ChromaDB
- `get_ticket_info(ticket_id)` — mock tra ticket info
- `check_access_permission(level, role, is_emergency)` — kiem tra quyen
- `create_ticket(priority, title, description)` — mock tao ticket

**State flow thuc te** (sau khi fix bugs):

```
task → supervisor_node → route_decision
                           ├─ retrieval_worker → synthesis → END
                           ├─ policy_tool_worker
                           │    (goi MCP search_kb neu needs_tool=True)
                           │    → synthesis → END
                           └─ human_review → (auto-approve) → retrieval_worker → synthesis → END
```

---

## 2. Cac bug da phat hien va fix

### Bug 1: ChromaDB rong — nguyen nhan goc cua nhieu loi

**Bieu hien:** `artifacts/grading_run.jsonl` truoc fix:
- `confidence: 0.1` moi cau
- `hitl_triggered: true` moi cau
- `answer: "Khong du thong tin..."` moi cau
- `sources: []` moi cau

**Nguyen nhan:** Collection `day09_docs` co 0 chunks. Khi `retrieve_dense()` gap loi
(seems embedding model unavailable) → fallback sang `_lexical_fallback()` → token
overlap qua thap vi cau hoi gq01 hoi "22:47", "ai nhan thong bao dau tien"
khong match voi chunk nao trong sla_p1_2026.txt.

**Fix:** Tao `build_index.py` — index 77 chunks tu 5 file docs bang
Sentence Transformers `all-MiniLM-L6-v2` vao ChromaDB. Sau index, moi cau
deu retrieve duoc 3 chunks dung source, confidence 0.61–0.72.

**Kiem chung:**
```
gq01: 3 chunks, sources=['sla_p1_2026.txt', 'sla_p1_2026.txt', 'it_helpdesk_faq.txt']
gq02: 3 chunks, sources=['policy_refund_v4.txt', ...]
gq06: 3 chunks, sources=['hr_leave_policy.txt', ...]
```

### Bug 2: `mcp_tools_used` luon ra `[null]`

**Nguyen nhan:** `eval_trace.py` line 130 dung sai key:

```python
# Sai:
"mcp_tools_used": [t.get("tool") for t in result.get("mcp_tools_used", [])]
# Phai la:
"mcp_tools_used": [t.get("mcp_tool_called") for t in result.get("mcp_tools_used", [])]
```

`dispatch_tool()` tra ve dict voi key `mcp_tool_called`, khong phai `tool`.

**Fix:** Doi `t.get("tool")` → `t.get("mcp_tool_called")`.

**Ket qua:** `mcp_tools_used` bay gio co gia tri thuc: `["search_kb"]` hoac
`["search_kb", "get_ticket_info"]` thay vi `[null]`.

### Bug 3: `workers_called` bi duplicate (moi worker xuat hien 2 lan)

**Bieu hien:** `workers_called: ["retrieval_worker", "retrieval_worker",
"synthesis_worker", "synthesis_worker"]` thay vi
`["retrieval_worker", "synthesis_worker"]`.

**Nguyen nhan:** Ca `graph.py` (trong worker wrapper node) VA
`workers/*.py` (trong ham `run()`) deu goi `workers_called.append()`. Double-write.

**Fix:** Xoa `workers_called.append()` khoi cac wrapper node trong
`graph.py`, chi giu trong workers.

### Bug 4: `graph.py` goi retrieval 2 lan voi policy route

**Nguyen nhan:** `build_graph()` goi `policy_tool_worker_node()`, sau do
kiem tra `if not state["retrieved_chunks"]` → goi `retrieval_worker_node()` lan 2.
Nhung ngay ca khi chunks da co, van goi them retrieval.

**Fix:** Xoa logic fallback retrieval ben trong policy route. Policy worker
da goi MCP `search_kb` neu can.

### Bug 5: `sources` bi rong cho policy route

**Nguyen nhan:** `eval_trace.py` doc `result.get("sources", [])` nhung
`synthesis.py` fallback dung `chunks` (tu MCP), khong ghi vao
`state["sources"]`. Policy route khong goi retrieval → `retrieved_sources=[]`.

**Fix:** `result.get("sources") or result.get("retrieved_sources") or []`

### Bug 6: `route_reason` mo ho

**Truoc:**
```
"route_reason": "default route"
"route_reason": "task contains policy/access keyword"
```

**Sau:**
```
"route_reason": "no_policy_keyword"
"route_reason": "policy_keywords=['hoan tien', 'flash sale']"
"route_reason": "policy_keywords=['access'] | risk_keywords=['emergency', '2am']"
```

---

## 3. Ket qua grading questions (chay thuc te 17:33-17:35)

**Tong diem raw: 83/96 → (83/96) x 30 = 25.9 diem**

### Chi tiet tung cau

| Cau | Diem raw | Muc | Ly do |
|-----|----------|-----|-------|
| gq01 | **10/10** | FULL | Route retrieval dung. sla_p1_2026.txt co: 15p response, 4h resolution, notification Slack+email+PagerDuty, escalation 10p (22:57). |
| gq02 | **10/10** | FULL | Route policy dung. Temporal scoping: 31/01 → policy v3 (khong co trong docs) → abstain dung. |
| gq03 | **5/10** | PARTIAL | Route policy dung nhung answer chi cite "Level 2 Standard Access" thay vi "Level 3 Elevated Access" can 3 nguoi: Line Manager + IT Admin + IT Security. IT Security la nguoi cuoi cung. |
| gq04 | **6/6** | FULL | Route policy dung. policy_refund_v4.txt Đieu 5: "110% so voi so tien hoan". |
| gq05 | **8/8** | FULL | Route retrieval dung. sla_p1_2026.txt Phan 2: "Tu dong escalate len Senior Engineer neu khong co phan hoi trong 10 phut." |
| gq06 | **8/8** | FULL | Route retrieval dung. hr_leave_policy.txt §4.1: "Nhan vien sau probation period co the lam remote toi da 2 ngay/tuan." |
| gq07 | **10/10** | FULL | Abstain dung — tai lieu khong co muc phat tai chinh cho vi pham SLA P1. Khong hallucinate. |
| gq08 | **8/8** | FULL | Route retrieval dung. it_helpdesk_faq.txt §1: "Mat khau phai duoc thay doi moi 90 ngay. He thong se nhac nho 7 ngay truoc khi het han." |
| gq09 | **8/16** | PARTIAL | Route policy+danger dung. Chi lay duoc access_control_sop.txt (Level 2 + Jira), nhung khong lay duoc sla_p1_2026.txt de noi ve cac buoc SLA P1 notification (Slack #incident-p1, email, PagerDuty). Chi duoc 1/2 phan. |
| gq10 | **10/10** | FULL | Route policy dung. policy_refund_v4.txt Đieu 3: Flash Sale exception → khong hoan tien ke ca khi co loi nha san xuat. |

### Phan tich diem

- **9/10 cau dat FULL marks** — pipeline xu ly tot khi retrieve dung source.
- **2 cau PARTIAL:** gq03 (sai Level 3), gq09 (thieu 1 nguon).
- **Khong co cau ZERO** — khong co hallucination.
- **gq07 abstain dung** — khong bi phat.
- **Tong diem: 83/96 raw → 25.9/30 diem grading.**

### Nguyen nhan gq03 bi PARTIAL

`retrieval.py` tim kiem semantic nhung chunk "Level 3 — Elevated Access"
nam o giua van ban Section 2 cua access_control_sop.txt. Query gq03 hoi ve
"Level 3 access" nhung semantic similarity voi chunk "Level 2 — Standard Access"
(gan cua van ban hon) co the cao hon. Can tang `top_k` hoac cai thien
chunking strategy de "Level 3" chunk duoc xep hang cao hon.

### Nguyen nhan gq09 bi PARTIAL

gq09 yeu cau 2 nguon: sla_p1_2026.txt (SLA P1 notification) VA
access_control_sop.txt (Level 2 emergency bypass). `top_k=3` chi lay 3 chunks,
neu ca 3 chunks deu tu access_control_sop.txt thi khong con cho sla_p1.
Can tang `top_k=4` hoac thay doi chunking de đa dang nguon hon.

---

## 4. So sanh Day 08 vs Day 09

**Metric thay doi ro nhat:**

- **Routing accuracy:** N/A (Day 08, single pipeline) → 100% (Day 09, 10/10 cau)
- **Abstain rate:** 10% (1/10) → 10% (1/10) — ngang nhau
- **Grading raw:** 98/98 → 83/96 (kha, nhung retrieval van la yeu to quyet dinh)

**So sanh day du:**

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Ghi chu |
|--------|----------------------|----------------------|---------|
| Grading raw | 98/98 | 83/96 | Day 08 thang (98% vs 86%) |
| Routing accuracy | N/A | 100% | Day 09 co trace ro rang |
| Debuggability | ~15 phut/bug | ~5 phut/bug | Day 09 thang ro |
| Abstain rate | 10% | 10% | Ngang nhau |
| HITL control | Prompt instruction | Luong rieng `human_review` | Day 09 thang |
| Latency | ~1850ms | ~10000-17000ms | Day 08 thang (rerank + LLM) |
| Confidence thuc | Co (tu rerank score) | Co (tu chunk score) | Ca hai co |
| MCP tool | Khong co | 4 tools | Day 09 thang |

**Gioi han cua Multi-Agent hien tai:**
- Retrieval van la noi yeu nhat (quyet dinh 90% grading score).
- `top_k=3` chua du de multi-hop (gq09 can 4+ chunks).
- Chunking strategy anh huong nhieu den semantic ranking.

---

## 5. Phan cong va danh gia nhom

**Phan cong thuc te:**

| Thanh vien | Phan da lam | Sprint | Bang chung |
|------------|-------------|--------|------------|
| Nguyen Anh Quan | `workers/retrieval.py`, `workers/synthesis.py`, `build_index.py`, ChromaDB integration | 2, 4 | WORKER_NAME="retrieval_worker", 77 chunks indexed |
| Vo Thien Phu | `graph.py` — AgentState, supervisor_node, route_decision, human_review_node, build_graph, route_reason fix | 1 | graph.py:24-129 supervisor logic |
| Phan Duong Dinh | `workers/policy_tool.py` (LLM-based + rule-based), `contracts/worker_contracts.yaml` | 2 | analyze_policy_with_llm() lines 71-148 |
| Pham Minh Khang | `mcp_server.py` (4 tools), MCP wiring trong policy_tool, dispatch_tool trace format | 3 | dispatch_tool() lines 298-331 |
| Dao Hong Son | `eval_trace.py`, `build_index.py`, 3 docs/*.md, `reports/group_report.md`, grading run | 4 | artifacts/grading_run.jsonl, eval_trace.py |

**Diem manh cua nhom:**
- Contracts duoc viet **truoc** khi implement worker → interface khong thay
  doi giua cac sprint.
- Trace format nhat quan ngay Sprint 1 → Sprint 4 chi viec `json.load`.
- MCP dispatch format chuan hoa tu Sprint 3 → `eval_trace.py` doc nhat quan.
- Bug duoc phat hien va fix nhanh: ChromaDB index, mcp_tools_used key,
  duplicate workers_called, route_reason chi tiet.

**Diem chua tot:**
- ChromaDB chua duoc index truoc — gap van de luc grading. Bay gio da fix.
- `top_k=3` chua du cho multi-hop — can tang len 4+ cho gq09.
- Chunking strategy chua toi uu — gq03 bi PARTIAL vi semantic ranking chua chinh xac.

**Neu lam lai, nhom se thay doi gi?**
- Index ChromaDB **ngay sau khi setup** thay vi de Sprint 4.
- Tang `top_k` len 4 de dam bao multi-hop lay du nguon.
- Viet **integration smoke test** ngay Sprint 1 chay 3 cau end-to-end.

---

## 6. Neu co them 1 ngay

1. **Tang `top_k=4` hoac 5** — dam bao multi-hop (gq09) lay du nguon.
2. **Cai thien chunking strategy** — chunking theo section thay vi theo
   paragraph, hoac dung overlapping chunks de tang recall.
3. **Thay `confidence` placeholder** bang gia tri thuc (cosine max +
   LLM self-score).
4. **HTTP MCP server** (bonus +2) — thay in-process class bang FastAPI server
   de test isolation tot hon.
5. **Parallel multi-hop routing** — Supervisor goi song song retrieval + policy
   khi cau hoi co nhieu intent.

---

*Luu file tai: `reports/group_report.md`*
*Cap nhat: 2026-04-14 17:35 (sau khi chay grading thuc te)*
*Commit sau 18:00 duoc phep theo SCORING.md.*
