# Orchestrator

## Inputs

Read:

- `project.yaml`;
- `state/research-context.yaml`;
- existing ledger, assumptions, dependency graph, and source registry if present;
- the user's current request.

## Step 1 — Resolve intent

Classify the task as one of:

- Quick View
- Full Initiation
- Update
- Scenario
- Publish/Edit

Prefer the smallest workflow capable of answering the request.

## Step 2 — Provide early value

Before a long run, state concisely:

1. principal investor debate;
2. preliminary valuation/setup signal if available;
3. 2–4 hypotheses to test;
4. any material uncertainty that changes the research path.

Do not wait until the final IOC to expose the core research question.

## Step 3 — Load minimum context

For every analytical node, retrieve only:

- relevant active ledger records;
- relevant assumptions;
- required source extracts;
- direct upstream analytical conclusions.

Never concatenate every earlier module into the prompt by default.

## Step 4 — Execute and persist

Each node must persist:

- new ledger records;
- changed assumptions;
- contradictions;
- research gaps;
- dependencies;
- node output in `analysis/`.

## Step 5 — Recompute intelligently

If existing state is present, use `workflows/recompute.md` to decide which nodes are stale. Do not rerun stable nodes merely because a new report is being generated.

## Step 6 — Validate before publication

Run both:

- structural workspace validation;
- analytical QA reviewer.

If QA fails, correct only the affected nodes and rerun downstream synthesis.
