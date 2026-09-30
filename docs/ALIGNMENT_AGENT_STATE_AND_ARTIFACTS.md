# Alignment Agent: state, fallback, resume, and artifacts

The ACORD Alignment workspace is orchestrated by the LangGraph workflow in
[`alignment_agent/workflow.py`](../src/canonical_model_generator/alignment_agent/workflow.py).
Matching remains deterministic and evidence-preserving; the graph controls validation, matching,
independent proposal validation, review preparation, retry, and durable resume.

## Package boundary

| Path | Responsibility |
| --- | --- |
| `alignment_agent/contracts.py` | JSON-serializable graph state and recoverable failure contract |
| `alignment_agent/workflow.py` | LangGraph nodes, bounded retry, stable input identity, start/load/resume calls |
| `alignment_agent/persistence.py` | Strict SQLite checkpoint serializer and durable review-draft storage |
| `acord_alignment.py` | Deterministic matching, decision validation, and approved artifact construction |

`acord_alignment.py` remains a deterministic service and compatibility API. Streamlit no longer
calls its proposal function directly; proposal generation is reached through `run_alignment_agent`.

## Input boundary and graph

The graph receives one regional entity/attribute catalog, regional domain/capability tree,
regional endpoint inventory, selected ACORD ingestion, and an optional immutable canonical
baseline. A SHA-256 digest covers all inputs. Reusing a run ID with different evidence is rejected.

Normal path:

`validate_inputs` -> `propose_alignment` -> `validate_proposal` -> `prepare_review`

- Matching compares the canonical baseline first. Incomplete matches use ACORD as the fallback.
- Proposal validation independently accounts for every regional entity, attribute, domain, and
  capability ID and rejects missing or duplicate nodes.
- Each material node has at most three attempts with bounded backoff for transient exceptions.
  Contract and input errors fail immediately.
- The terminal state is `awaiting_review` with `stop_reason=review_required`; no proposed match is
  automatically approved.

## SQLite and resume

The ignored database `.alignments/alignment-agent.sqlite3` contains LangGraph checkpoints plus an
`alignment_review_drafts` table. Checkpoint deserialization allows only built-in message-pack
types; credentials are not graph inputs and are never stored.

If a node still fails after its retry allowance, the public call raises `AlignmentAgentError` with
the latest state. `resume_alignment_agent(database, run_id)` invokes the same thread with no new
input, so LangGraph reruns the failed node from the preceding checkpoint instead of repeating
completed nodes. Streamlit exposes this as **Resume Alignment Agent**. Reviewer decisions are
upserted separately so a browser or Streamlit restart can reopen an in-progress review.

## Artifact and governance boundary

The graph produces a proposal and unapproved review defaults, not a canonical model. Existing
deterministic validation still requires explicit approval for every entity, attribute, domain, and
capability plus whole-model confirmation. Only then is the approved alignment JSON written under
`.alignments/<alignment-id>/` and a new immutable canonical `vN` appended to the canonical SQLite
registry. Regional, Discovery, API Analyzer, ACORD ingestion, and prior canonical artifacts are
never overwritten.

