# Local Lab Design

## Purpose

TALK's next phase is a small home-LAN multi-Agent lab, not a cloud Agent platform. It is expected to run on demand while the local computer is in use, with roughly five active AI Agents and one human operator sharing the same conversation space.

The first implementation target is a minimal Codex bridge. The broader product model should be settled enough to avoid reworking the bridge when Groups, Hall mode, streaming, scheduling, and document-edit coordination arrive.

## Scope

In scope for the local lab phase:

- Bridge processes that connect external Agent runtimes to TALK.
- A shared Hall timeline for discussion, later scoped by Group.
- Multiple independent Groups / rooms for separate discussions.
- SSE streaming for long-running Agent output.
- Agent instance and scheduling APIs.
- A document-edit coordination protocol so only one Agent edits a document at a time.

Out of scope for this phase:

- Public internet deployment as a hosted service.
- Fine-grained multi-tenant authorization.
- End-to-end encryption.
- Replacing the underlying model runtimes.

## Agent Bridge Model

Each bridge is a small local process with one TALK member identity.

Planned bridge families:

- `Codex CLI -> codex bridge -> TALK`
- `Claude Code -> claude bridge -> TALK`
- `DeepSeek / Kimi -> pi bridge -> TALK`

Common bridge responsibilities:

- Register or refresh its `agent:*` member.
- Listen for visible TALK messages through the SDK.
- Decide whether a message is addressed to this Agent.
- Convert TALK messages and files into the runtime-specific prompt/input format.
- Invoke the underlying runtime with a bounded timeout.
- Send the final reply back to TALK.
- Report runtime instance status.
- Later: emit stream events and respect document locks.

The first Codex bridge is intentionally narrow: it responds to direct text messages addressed to `agent:codex`, invokes `codex exec`, replies to the original sender, and reports its local runtime instance status.

## Groups And Hall

A Group is a discussion room. A Hall is the shared timeline inside a Group.

The current message model already supports broadcast and directed messages through `to_ids`, but it does not distinguish rooms. The future message model should add a room scope, likely `group_id`, while preserving direct mentions inside that room.

Expected Hall behavior:

- The Web UI opens to the active Group's Hall timeline.
- Human and Agent messages appear in one chronological stream.
- Broadcast messages are visible to all members in that Group.
- Mentions still route attention to specific Agents, but the Hall remains the default collaboration surface.
- Private or direct views can exist later, but should not drive the main UX.

## Discussion Protocol

The first multi-Agent discussion protocol should be moderator-led.

Minimum fields for a discussion session:

- Group / room id.
- Moderator member id.
- Participant member ids.
- Topic / task prompt.
- Round limit.
- Stop condition.
- Material bundle references.
- Final summary policy.

Minimum flow:

1. Moderator opens a discussion in a Group.
2. Moderator posts the topic and material references to the Hall.
3. Participants answer in bounded turns.
4. Moderator may ask follow-up questions or request review from another Agent.
5. Moderator stops when the round limit or stop condition is reached.
6. Moderator posts a final summary with decisions, open questions, and next actions.

## SSE Streaming

WebSocket already handles committed messages and presence. SSE should be used for long-running Agent output where the user should see partial text before the final message is committed.

Initial event shape:

- `stream_start`: identifies `stream_id`, `group_id`, `from`, optional `reply_to`.
- `stream_delta`: appends text to the active stream.
- `stream_end`: finalizes the stream and links to the committed message id.
- `stream_error`: ends the stream with an error reason.

The canonical record remains the final message in SQLite. Stream deltas are transient UI events unless a later product decision asks for raw generation traces.

## Instances And Scheduling

Current `members` describe identity. `agent_instances` now describes running bridge processes.

Model split:

- `member`: stable identity such as `agent:codex`.
- `instance`: one running bridge process for a member.
- `task`: a requested unit of work, still future.
- `schedule`: delayed or repeated task trigger, still future.

Minimum instance fields:

- `id`
- `member_id`
- `runtime` such as `codex`, `claude`, or `pi`
- `status` such as `starting`, `online`, `busy`, `idle`, `stopping`, `offline`, `error`
- `pid` or host-local process reference when available
- `last_seen_at`
- `current_task_id`

Implemented first slice:

- `PUT /api/instances/{instance_id}` lets an authenticated `agent:*` member create or update its own instance status.
- `GET /api/instances` lets authenticated members list instances, with `member_id` and `status` filters.
- Codex bridge uses this API to report `idle`, `busy`, `error`, and `offline`.

Open implementation details:

- Task and schedule table shape.
- Whether the scheduler owns bridge process startup or only tracks submitted work.
- How Web UI should present active / busy / errored instances.

## Document Editing Coordination

Multiple Agents must not edit the same document at the same time.

Initial protocol:

- Lock granularity starts at whole-file locks.
- A write-capable Agent must acquire a lock before editing a file.
- Other Agents may read and review locked files, but must not write them.
- Locks should include owner, file path, purpose, acquired time, and expiry time.
- Stale locks can be released after timeout or by the moderator.
- If an Agent cannot acquire a lock, it should switch to suggestion/review mode and post proposed changes instead of writing.

Open implementation details:

- Exact lock timeout.
- Whether locks live in SQLite, filesystem sidecars, or both.
- Whether lock paths are project-root relative or absolute.
- How the Web UI shows active locks.
- Whether the moderator can grant, extend, or revoke locks.

## First Implementation Slice

The first slice is Codex bridge MVP:

1. Add `bridges/codex_bridge.py`.
2. Use `TalkClient` for registration and message listening.
3. Default member id: `agent:codex`.
4. Process direct text messages only.
5. Invoke `codex exec --skip-git-repo-check --sandbox workspace-write --color never -`.
6. Pipe the TALK task into Codex through stdin.
7. Reply to the original sender with the final output.
8. Keep command, working directory, timeout, and reply size configurable.

This gives the project a real bridge to test before the deeper Group / Hall / SSE / scheduler changes.
