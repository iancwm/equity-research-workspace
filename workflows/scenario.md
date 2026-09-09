# Workflow — Scenario

Use when the user changes assumptions rather than underlying evidence.

Examples:

- WACC / terminal growth;
- revenue growth;
- utilization;
- margin;
- AI productivity retention;
- commodity price;
- FX;
- capex;
- valuation multiple.

## Steps

1. Record scenario overrides separately from the base case.
2. Do not browse unless the user requests fresh evidence or the assumption requires current validation.
3. Identify affected nodes through dependency graph.
4. Recompute only affected calculations and downstream conclusions.
5. Preserve base-case assumptions unchanged unless the user explicitly promotes the scenario to base case.
6. Produce `outputs/scenario-note.md` with assumption deltas and resulting valuation/thesis effects.
