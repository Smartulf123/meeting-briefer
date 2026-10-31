# meeting-briefer

Checked on 31 October 2026, for your own use (a portfolio project for the ElevenLabs application).

## Summary
**Building for yourself: tools that already exist and what to build with**

Meeting summarizers are common: commercial bots such as Fireflies, Otter and Zoom AI Companion extract action items, and the most popular self-hosted option, Meetily, has 32k stars. The closest open-source project is MoM AI (174 stars), which also uses Anthropic and ElevenLabs, but only ElevenLabs Scribe for speech-to-text. None of the projects found speaks the result back as a briefing, and none measures its extraction with an eval set. Those two pieces set this project apart. The planned stack holds up: the Anthropic SDK with `messages.parse`, the ElevenLabs SDK with `eleven_flash_v2_5`, FastAPI, pydantic-settings and pytest with a plain scoring script.

## Tools that might save you time
| Project | Type | Stars or users | License | Match | What it does |
|---|---|---|---|---|---|
| [MoM AI](https://github.com/inboxpraveen/LLM-Minutes-of-Meeting) | repo | 174 stars | see repo | direct | Recording or transcript to decisions and action items, Anthropic as one LLM option, ElevenLabs Scribe for transcription. No spoken briefing, no evals. |
| [Meeting-Summary-Generator](https://github.com/Otutu11/Meeting-Summary-Generator) | repo | 53 stars | see repo | direct | Transcript to summary, decisions and action items with OpenAI. |
| [vtt-summarizer](https://github.com/itsmetamike/vtt-summarizer) | repo | 33 stars | see repo | direct | Transcript to JSON with a second LLM pass to clean the JSON. |
| [Meetily](https://github.com/Zackriya-Solutions/meetily) | repo | 32k stars | see repo | partial | Self-hosted desktop meeting assistant: recording, transcription, summaries. No API. |
| [Fireflies.ai](https://fireflies.ai/blog/fireflies-vs-otter/) | app | commercial | closed | partial | Meeting bot with action items, owners and deadlines, pushes tasks to other tools. |
| [Otter.ai](https://circleback.ai/compare/firefliesai-vs-otterai) | app | commercial | closed | partial | Notetaker with assignable action items (seen only on a third-party comparison page). |
| [Zoom AI Companion](https://uis.georgetown.edu/zoom/zoom-ai/) | app | built into Zoom | closed | partial | Summaries with action items emailed after the meeting (seen on a university IT page). |
| [Teams-Transcript-Summarizer](https://github.com/Bradybry/Teams-Transcript-Summarizer) | repo | 33 stars | see repo | partial | Flask app that turns Teams transcripts into bullet summaries. Last push 2024. |
| [Vexa](https://github.com/Vexa-ai/vexa) | repo | 2.9k stars | see repo | adjacent | Open-source meeting transcription API, a possible upstream source of transcripts. |

## Gaps
1. No spoken output. None of the open-source summarizers found turns the result into a spoken briefing; MoM AI uses ElevenLabs only for speech-to-text. Evidence: [MoM AI](https://github.com/inboxpraveen/LLM-Minutes-of-Meeting), [vtt-summarizer](https://github.com/itsmetamike/vtt-summarizer). Checked: three direct-match READMEs, and a GitHub search for "audio briefing elevenlabs" returned nothing above 20 stars.
2. No measured quality. None of them ships an eval set, so there is no number behind "it finds the action items". Evidence: [MoM AI](https://github.com/inboxpraveen/LLM-Minutes-of-Meeting), [Meeting-Summary-Generator](https://github.com/Otutu11/Meeting-Summary-Generator). Checked: the same three READMEs.

## Recommended stack
| Layer | Top pick | Popularity | License | Alternative | Why it fits this project |
|---|---|---|---|---|---|
| AI SDK | [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) | 4.0k stars | MIT | [Instructor](https://github.com/567-labs/instructor) | `messages.parse` returns a validated Pydantic object; structured outputs need no beta header. |
| Backend | [FastAPI](https://github.com/fastapi/fastapi) + [uvicorn](https://github.com/Kludex/uvicorn) | 103k stars | MIT, BSD-3 | none worth padding in | Pydantic request models, OpenAPI docs and TestClient for the webhook. |
| Config | [pydantic-settings](https://github.com/pydantic/pydantic-settings) | 1.5k stars | MIT | | Typed `.env` loading for both API keys. |
| Text-to-speech | [ElevenLabs Python SDK](https://github.com/elevenlabs/elevenlabs-python) | 3.2k stars | MIT (PyPI) | [VoxCPM2](https://github.com/OpenBMB/VoxCPM) | `text_to_speech.convert`; Flash v2.5 covers 32 languages including Norwegian. |
| Testing | [pytest](https://github.com/pytest-dev/pytest) | 14.6k stars | MIT | | Fake clients keep the test suite free of API calls. |
| Evals | plain scoring script | | | [Pydantic Evals](https://github.com/pydantic/pydantic-ai) | Extraction has checkable answers, so keyword and owner matching beats an LLM judge for 8 cases. |

- Anthropic SDK: structured outputs ignore some schema constraints (such as string length), so business rules like "the owner must appear in the transcript" need your own check and retry. Instructor would do the retry for you, but a hand-written loop shows more of your own work.
- ElevenLabs: `eleven_multilingual_v2` does not list Norwegian; Flash v2.5, v3 and v4 do ([models page](https://elevenlabs.io/docs/overview/models)). The free plan gives about 10k credits a month, has no commercial license, and published audio should credit ElevenLabs ([pricing](https://elevenlabs.io/pricing), [publishing rules](https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform)). Whether a free key can call the TTS API was not confirmed from the docs, so test one call first.
- VoxCPM2 needs a GPU and is a competitor's model, so it is a poor fit for this application.

## Skills for your coding agent
| Skill | Helps with | Installs or stars | Why |
|---|---|---|---|
| [ElevenLabs text-to-speech](https://skills.sh/elevenlabs/skills/text-to-speech) | TTS calls | 17.8k installs | Official ElevenLabs usage for Python. Its examples default to `eleven_v4`, and its setup runs the ElevenLabs CLI, so read that step first. |
| [FastAPI](https://skills.sh/fastapi/fastapi/fastapi) | the webhook | 14.1k installs | Official FastAPI practices: Pydantic models, dependencies, async vs sync. |
| [Pydantic](https://skills.sh/pydantic/skills/pydantic) | the schema | 2.3k installs | From the Pydantic team. |
| claude-api | the Claude calls | already installed | Anthropic's own skill for SDK parameters, structured outputs and model ids. |

## Building blocks for the features
- **Eval harness:** a plain pytest-style scoring script, Use. Deterministic precision and recall per field, no extra cost. Alternatives: [promptfoo](https://github.com/promptfoo/promptfoo), Use, good for model comparison, but a Node CLI (26.7k stars, MIT); [DeepEval](https://github.com/confident-ai/deepeval), Use, mostly LLM-judge metrics, which add cost and noise (19.2k stars, Apache-2.0).
- **Structured extraction with retries:** `messages.parse` plus your own check and retry loop, or [Instructor](https://github.com/567-labs/instructor), Use (14k stars, MIT).

## Products worth studying
- [MoM AI](https://github.com/inboxpraveen/LLM-Minutes-of-Meeting): how it attributes decisions and action items to speakers, and its health and metrics endpoints. Read the README and code.
- [Fireflies.ai](https://fireflies.ai/blog/fireflies-vs-otter/): its action-item fields (owner, deadline, dependencies) as a check on your schema.
- [Agent audio briefs with ElevenLabs](https://www.developersdigest.tech/blog/agent-audio-briefs-elevenlabs): how to write for the ear (short sentences, no bullets) before the TTS call.

Learn the patterns and make them your own; code, images, icons and a look-alike design stay the owner's.

## Next step
Spend ten minutes with MoM AI's README to see what a similar project already shows, then keep the two pieces it lacks (the spoken briefing and the eval numbers) front and centre in your README.

## Sources
https://github.com/inboxpraveen/LLM-Minutes-of-Meeting
https://github.com/Otutu11/Meeting-Summary-Generator
https://github.com/itsmetamike/vtt-summarizer
https://github.com/Zackriya-Solutions/meetily
https://github.com/Bradybry/Teams-Transcript-Summarizer
https://github.com/chulipinho/summit
https://github.com/Vexa-ai/vexa
https://fireflies.ai/blog/fireflies-vs-otter/
https://circleback.ai/compare/firefliesai-vs-otterai
https://uis.georgetown.edu/zoom/zoom-ai/
https://skills.sh/nousresearch/hermes-agent/meeting-action-items
https://github.com/anthropics/anthropic-sdk-python
https://github.com/567-labs/instructor
https://github.com/fastapi/fastapi
https://github.com/Kludex/uvicorn
https://github.com/pydantic/pydantic-settings
https://github.com/elevenlabs/elevenlabs-python
https://github.com/OpenBMB/VoxCPM
https://github.com/pytest-dev/pytest
https://github.com/pydantic/pydantic-ai
https://github.com/promptfoo/promptfoo
https://github.com/confident-ai/deepeval
https://skills.sh/fastapi/fastapi/fastapi
https://skills.sh/elevenlabs/skills/text-to-speech
https://skills.sh/pydantic/skills/pydantic
https://elevenlabs.io/docs/overview/models
https://elevenlabs.io/pricing
https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform
https://www.developersdigest.tech/blog/agent-audio-briefs-elevenlabs
