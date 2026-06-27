# Taste (Continuously Learned by [CommandCode][cmd])

[cmd]: https://commandcode.ai/

# workflow
- Use no-mistakes as the default quality gate for every PR. Confidence: 0.75
- Invoke agentic-engineering (dummy pipeline integration test) only when the user deems it necessary, and run it before executing the full pipeline to deploy. Confidence: 0.75

