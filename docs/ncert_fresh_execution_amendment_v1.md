# Fresh execution configuration amendment

Frozen before any fresh graph construction or predictions. Graph extraction and review use a 32,768-token context window, temperature 0, seed 42, 5,000 output tokens and no retries. Baseline answering remains at a 16,384-token context window with 1,500 output tokens.

The largest selected graph prefix is 31,633 native-text characters; entity/candidate schemas and review claims add substantial context. Both installed local models have a 32,768-token architecture context limit, according to the parent agent's local model inspection. Raising construction context is a pre-execution capacity setting, not a response to fresh model outcomes.

Graph-stage HTTP timeout is 900 seconds. The earlier development Mistral review took 187.6 seconds for 1,566 output tokens, so a 5,000-token generation could exceed the former 300-second timeout. The longer bound avoids a predictable transport cutoff; it does not add retries.

No fresh question text, answer reference or generated answer is inspected by the execution agent. Raw artifacts are retained. Every planned arm, including unavailable graph arms, remains in the attempt denominator. All fresh answer-reference scores remain unset pending postprediction AI review.
