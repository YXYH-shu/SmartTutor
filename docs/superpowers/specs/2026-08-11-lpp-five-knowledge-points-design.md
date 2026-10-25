# LPP Five Knowledge Points Design

## Goal

Expose a stable, ordered five-knowledge-point learning path while preserving
the existing DSMOEA/KT question-level search as an internal scoring source.

## Boundary

The runtime will publish an ordered `recommendation.knowledge_points` list
with exactly five distinct knowledge points.  The list is derived primarily
from the existing ACE-ranked `top_k` knowledge points and filled, in a stable
order, from the already selected questions only when the ranked list is short.
Question selection remains internal compatibility data; it is not supplied to
the learning-path LLM or returned as the path's primary recommendation.

## Backend behaviour

The adapter validates the five-point list, projects only those point facts
into the LLM prompt, and creates one P1--P5 learning stage per point.  The
existing planning rationale, stage objectives, and adaptive-rule prompt
templates remain unchanged.  The user-facing response exposes
`recommended_knowledge_points`, not `recommended_questions`.

## Error handling and tests

If the runtime cannot form five distinct knowledge points, it returns a
structured unavailable result rather than silently duplicating a point.
Tests cover runtime selection order, adapter validation, prompt projection,
and the agent's final public shape.
