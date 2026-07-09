# AI Behavior

The system should:

1. Extract facts from user input
2. Identify affected objects
3. Propose structured updates for confirmation
4. Save approved changes and link related objects
5. Generate briefing and prep outputs on demand

## Runtime behavior

- Capture uses OpenAI Structured Outputs when `OPENAI_API_KEY` is configured.
- The model receives a compact list of known companies, people, and strategic issues to improve entity linking.
- Suggested updates and follow-up questions are disposable until the user explicitly confirms updates.
- Without an API key or during a provider outage, the app returns a visibly labeled, limited local preview instead of silently pretending that rules-based extraction is AI.
- Screenshot capture uses the same structured approval workflow and requires a configured AI connection.
- The system must extract only facts supported by the capture and never invent missing context.
- Corrections are authoritative. When a capture says "X, not Y", the system must not assign Y.
- Employment transitions should preserve former company, new primary company, timing, and ongoing advisory or part-time relationships when stated.
- `details` may provide readable context, but durable typed fields should be populated whenever possible.
- Briefing, meeting-prep, and search outputs are generated views over memory, not source-of-truth records.
