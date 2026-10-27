# Harness

Runs a frozen prompt set against generative engines and logs everything needed to analyze it later.

Planned:

- Engines: ChatGPT with web search, Gemini with grounding, Perplexity Sonar, via API, plus a search-off probe of each model
- Per run: prompt, engine, model version, timestamp, full answer, cited URLs, retrieved sources where the API exposes them
- Fixed sample sizes committed up front, repeated windows two weeks apart
- Checksums of every cited page per window
