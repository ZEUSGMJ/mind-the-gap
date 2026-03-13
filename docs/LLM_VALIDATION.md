# LLM Validation Note
## Mind the Gap: Optional Cohen's Kappa Second Pass

This document describes the optional LLM-based second-pass classification used
to compare model outputs against the deterministic AST classifier and compute
Cohen's kappa. This path is not required for the main 01-05 reproduction
workflow.

## What the LLM Pass Is For

The main study uses the deterministic classifier in `pipeline/04_classify.py`.
The LLM scripts are included as auxiliary validation runs that answer a
narrower question: how closely does a local or API-based model agree with the
same priority-ordered gap taxonomy?

Available scripts:

- `pipeline/04b_classify_ollama.py` for local Ollama models
- `pipeline/04b_classify_anthropic.py` for the Anthropic API path

The Python dependencies for both scripts are declared in `requirements.txt`.
You still need the runtime prerequisites described below.

## Official Resources

- Ollama docs: <https://docs.ollama.com/>
- Ollama Docker docs: <https://docs.ollama.com/docker>
- Ollama download page: <https://ollama.com/download>
- `llmfit` model-sizing helper: <https://github.com/AlexsJones/llmfit>

## Local Ollama Setup

The tested local endpoint is:

- `http://localhost:11434`

The tested local model is:

- `phi3:mini`

Direct local setup:

```bash
ollama serve
ollama pull phi3:mini
python3 pipeline/04b_classify_ollama.py --model phi3:mini
```

The script writes results into `data/results/cohens_kappa.json` and may also
write model-specific disagreement files in `data/results/`.

### Docker Compose Option

The original local validation setup used Ollama behind Docker Compose. If you
prefer that route, use a portable Compose file rather than copying any
machine-specific host paths.

Example:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

volumes:
  ollama_data:
```

If your machine has NVIDIA GPU support available to Docker, you can extend that
setup with the appropriate GPU reservation options. CPU-only runs also work,
but will usually be slower.

## Anthropic API Setup

The tested API-based path is `pipeline/04b_classify_anthropic.py`.

Prerequisites:

- `ANTHROPIC_API_KEY` exported in the environment

Example:

```bash
export ANTHROPIC_API_KEY=your_key_here
python3 pipeline/04b_classify_anthropic.py
```

Important notes:

- The current script is Anthropic-specific and uses the Anthropic Messages API.
- The model is currently pinned in code to `claude-haiku-4-5-20251001`.
- Trying another Anthropic model will usually require editing the model
  constant in the script.
- Using another provider such as OpenAI, Gemini, or OpenRouter requires
  adapting the script.
- API pricing, rate limits, and model availability may change over time.

## Choosing a Local Model

If you are unsure what your machine can handle locally, use `llmfit` first.
That is the easiest way to estimate which model sizes fit your RAM and VRAM
before you start pulling models.

Example:

```bash
llmfit plan
```

Confirmed local hardware on the original workstation:

| Spec | Value |
|------|-------|
| CPU | Intel i5-8300H @ 2.30GHz (8 cores) |
| RAM | 15.51 GB total |
| GPU | NVIDIA GeForce GTX 1050 (4.0 GB VRAM, CUDA) |
| OS | Ubuntu Linux 6.17.0-14-generic |

Model-selection notes from that setup:

| Model | Params | Min VRAM | Fit Status | Est. Speed |
|-------|--------|----------|------------|------------|
| phi3:mini | 3.8B | 2.8 GB | Perfect | ~66 tok/s |
| qwen3.5:4b | 4B | 2.4 GB | Perfect | ~82 tok/s |
| llama3:8b | 8B | 5.4 GB | Too large without CPU offload | ~16 tok/s |
| llama3.3:70b | 70B | N/A | Far too large | N/A |

Decision: `phi3:mini` and `qwen3.5:4b` were the local target models. In
practice, only `phi3:mini` completed successfully on the original workstation.
`qwen3.5:4b` was attempted but not completed due to instability. Larger models
were not practical on the original hardware.

## Inference Setup

- Ollama runtime: v0.6+
- Ollama endpoint: `http://localhost:11434/api/generate`
- Temperature: `0.0`
- Max tokens: `30`
- Prompt: the same priority-ordered taxonomy encoded in the validation scripts

## Results

| Model | Path | Kappa | Agreement | N Tests | Date |
|-------|------|-------|-----------|---------|------|
| phi3:mini (3.8B) | local Ollama | 0.2062 | 40.8% (86/211) | 211 | 2026-03-06 |
| claude-haiku-4-5 | Anthropic API | 0.2135 | 47.9% (101/211) | 211 | 2026-03-06 |

## Which Path Should I Use?

- Use Ollama if you want a local rerun and your machine can handle a small
  model such as `phi3:mini`.
- Use Anthropic if you do not want to run local inference.
- Use `llmfit` first if you are unsure which local model fits your hardware.
- Skip the LLM pass entirely if you only want to reproduce the main study
  artifacts. The deterministic 01-05 pipeline is the primary workflow.

## Notes

- Cohen's kappa is computed between the deterministic AST rule-based classifier
  and each LLM's classifications.
- Local hardware, model availability, Ollama version, and API availability may
  affect ease of reproduction and runtime.
- Low kappa from small models is expected because they do not reliably follow
  the priority ordering.
- `phi3:mini` over-classifies as `NONE_NULL_HANDLING`.
- Claude Haiku tends to over-classify into `RETURN_VALUE`, collapsing more
  specific categories into a broader one when the prompt rules are not followed
  strictly.
