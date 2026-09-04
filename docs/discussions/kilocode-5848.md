# I saved 10M tokens (89%) on my Claude Code sessions with a CLI proxy

> Archived copy of a GitHub Discussion, downloaded 2026-09-04.
>
> | | |
> |---|---|
> | **Source** | <https://github.com/Kilo-Org/kilocode/discussions/5848> |
> | **Repository** | Kilo-Org/kilocode |
> | **Discussion** | #5848 |
> | **Category** | 💡 1. Feature requests |
> | **Author** | @muskiness |
> | **Posted** | Feb 13, 2026 |
> | **Status** | Open · unanswered · unlocked |
> | **Reactions** | 9 (👍 4, 🚀 4) |
> | **Comments** | 2 |

---

## Original post

**@muskiness** — Feb 13, 2026

Feature Request: Built-in CLI output filtering/compression to reduce token usage (inspired by RTK)

Hey team! 👋

I recently came across an interesting project called **[RTK (Rust Token Killer)](https://github.com/rtk-ai/rtk)** — a CLI proxy that filters and compresses command output before it reaches the LLM context. The author shared their results on [Reddit](https://www.reddit.com/r/ClaudeAI/comments/1r2tt7q/i_saved_10m_tokens_89_on_my_claude_code_sessions/), and the numbers are impressive:

- `cargo test`: 155 lines → 3 lines (98% reduction)
- `git status`: 119 chars → 28 chars (76% reduction)
- `git log`: compact summaries instead of full output
- **Total savings over 2 weeks: ~10M tokens (89%)**

The core idea is simple: most CLI output sent to the LLM is noise — passing tests, verbose logs, progress bars, redundant formatting. Stripping that out before it hits the context window saves a massive amount of tokens without losing any useful information.

**Why this would be valuable as a built-in feature in your project:**

1. Users wouldn't need to install and configure a separate tool
2. Filtering rules could be context-aware and tightly integrated with your existing command execution pipeline
3. It directly reduces costs and improves response quality (less noise = better reasoning)
4. It could be opt-in with sensible defaults

**Possible implementation scope:**

- Configurable output filters for common commands (`git`, `npm`, `cargo`, `pip`, test runners, etc.)
- Smart truncation with summary (e.g., "47 tests passed, 2 failed" instead of full test output)
- User-defined rules for custom commands
- Toggle on/off per session or globally

I think this kind of optimization would be a huge quality-of-life improvement for users and a natural fit for your tool. Would love to hear your thoughts on whether this is something you'd consider exploring!

References:

- RTK repo: <https://github.com/rtk-ai/rtk>
- RTK site: <https://www.rtk-ai.app>
- Reddit discussion: <https://www.reddit.com/r/ClaudeAI/comments/1r2tt7q/>

---

## Comments

### 1. @travaillecommemoi — Mar 14, 2026

Definitely

### 2. @juanptovardev — Apr 9, 2026

Nice

---

_No further replies, hidden threads, or "load more" indicators were present on the page at the time of download._
