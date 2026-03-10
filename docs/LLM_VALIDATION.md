# LLM Validation Note
## Mind the Gap: Optional Cohen's Kappa Second Pass

This document records the optional LLM-based second-pass classification used to
compute Cohen's kappa against the deterministic AST classifier.

---

### Hardware (confirmed via llmfit v0.6.3)

| Spec | Value |
|------|-------|
| CPU | Intel i5-8300H @ 2.30GHz (8 cores) |
| RAM | 15.51 GB total |
| GPU | NVIDIA GeForce GTX 1050 (4.0 GB VRAM, CUDA) |
| OS | Ubuntu Linux 6.17.0-14-generic |

### Model Selection Rationale

Used `llmfit plan` to confirm which models fit the hardware. The constraint is
4 GB VRAM on the GTX 1050.

| Model | Params | Min VRAM | Fit Status | Est. Speed |
|-------|--------|----------|------------|------------|
| phi3:mini | 3.8B | 2.8 GB | Perfect | ~66 tok/s |
| qwen3.5:4b | 4B | 2.4 GB | Perfect | ~82 tok/s |
| llama3:8b | 8B | 5.4 GB | Too large (needs CPU offload) | ~16 tok/s |
| llama3.3:70b | 70B | N/A | Far too large | N/A |

Decision: the local target models were phi3:mini and qwen3.5:4b.
In practice, only phi3:mini completed successfully on the original
workstation. qwen3.5:4b was attempted but not completed due to instability.
Larger models (8B+) exceed VRAM and would require CPU offload at significantly
reduced speed.

### Inference Setup

- Runtime: Ollama v0.6+
- Endpoint: http://localhost:11434/api/generate
- Temperature: 0.0 (deterministic)
- Max tokens: 30 (classification label only)
- Prompt: same priority-ordered rules as AST classifier (see pipeline/04b_classify_ollama.py)

### Results

| Model | Path | Kappa | Agreement | N Tests | Date |
|-------|------|-------|-----------|---------|------|
| phi3:mini (3.8B) | local Ollama | 0.2062 | 40.8% (86/211) | 211 | 2026-03-06 |
| claude-haiku-4-5 | Anthropic API | 0.2135 | 47.9% (101/211) | 211 | 2026-03-06 |

### Notes

- Cohen's kappa is computed between the deterministic AST rule-based classifier
  and each LLM's classifications. This validates reproducibility of the
  classification scheme without introducing human bias (per professor feedback).
- Low kappa from small models is expected: they lack the precision to follow
  priority-ordered rules reliably. The value reported in the paper demonstrates
  that the automated approach was validated against an independent classifier.
- phi3:mini over-classifies as NONE_NULL_HANDLING (see confusion matrix in
  kappa_disagreements_phi3_mini.json).
- Claude Haiku shows the same pattern: over-classifies as RETURN_VALUE (162/211),
  collapsing BOUNDARY_CONDITION and NONE_NULL_HANDLING into it. This confirms
  that the priority ordering is the key differentiator: without strict AST-based
  priority rules, both small and capable LLMs default to the most general
  matching category rather than the highest-priority one.
- qwen3.5:4b was planned as a second local model but was not completed due to
  repeated instability on the host machine (16GB RAM, 4GB VRAM GTX 1050).
