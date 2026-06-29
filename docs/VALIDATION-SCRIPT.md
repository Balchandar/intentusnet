# Customer Validation Script — MCP Security & Governance

> Purpose: cheaply confirm (or kill) the thesis behind the IntentusNet pivot
> **before** building more scanner rules or the inline enforcer.
>
> The last cycle spent months building "provable determinism" on an unvalidated
> assumption. This document exists so that does not happen again.

---

## The thesis we are testing (falsifiable)

> **Teams putting MCP into production feel real, present pain about the *security*
> of connecting agents to tools — enough that they have already tried to solve it,
> improvised something, or blocked a rollout over it.**

If that pain is real and present, the scanner + gateway is the right line.
If people are only *mildly* concerned, or treat it as "future us" problem, the
thesis is weak and we adjust **now**, cheaply.

This is a search for **evidence of existing behavior**, not enthusiasm for an idea.

---

## The one rule (read before every call)

**Ask about their life, not your idea.** Do not pitch IntentusNet. Do not describe
the scanner. Do not ask "would you use a tool that…". People lie to be nice about
ideas; they can't lie about what they already did last month.

You are done talking when you've learned what they actually do today. If you find
yourself explaining your product, stop and ask another question about them.

---

## Who to talk to (5–8 people)

In priority order:
1. Platform / infra engineers who have **already shipped** an agent that calls MCP tools in prod.
2. Security engineers at a company **currently rolling out** internal MCP/agents.
3. Eng leads who **evaluated MCP and held back** (the "no" stories are gold).

Avoid: people who only read about MCP, AI influencers, anyone who'd buy to be nice.

---

## The 5 core questions

Open, past-tense, non-leading. Let silence do the work — don't rescue them.

### Q1 — Walk me through the last time you connected an agent to a tool or MCP server in production. What did that actually look like?
*Goal: establish that they have real, recent behavior here at all. If they don't, they're not your customer — end politely.*
- Probe: Whose server was it — yours, or a third party's?
- Probe: Who, if anyone, looked at it before it went live?

### Q2 — When you brought in that server, what worried you, if anything?
*Goal: see if security/permissions/audit surfaces **unprompted**. This is the single most important signal. Do NOT say the word "security" first.*
- Probe: Did anything make you hesitate or slow down?
- Probe: What would have had to go wrong for that to be a bad day?

### Q3 — What did you actually do about that concern?
*Goal: distinguish real pain (they spent time/money/effort) from theoretical concern (they shrugged). Action is the proof.*
- Probe: Did you build anything, review anything, write a doc, add a policy?
- Probe: How long did that take? Who paid attention to it?
- Probe: Is it still in place, or did it fall away?

### Q4 — Who in your org has to sign off before an agent can touch real tools or data? What do they ask for?
*Goal: find the actual buyer and the actual gate. If security/compliance has a checklist, that checklist is your spec.*
- Probe: Has a rollout ever been blocked or delayed by that review?
- Probe: What would they need to see to say yes faster?

### Q5 — If you could wave a wand and have one thing handled for you about running agents in prod, what would it be?
*Goal: a wide-open close. Note whether they reach for security/audit, or for something else entirely (cost, reliability, evals). Either answer is useful.*
- Probe: Why that one and not the others?
- Probe: What does it cost you today to not have it?

---

## Reading the signals

For each person, mark the thesis as supported or not:

| Signal | Strong YES (thesis holds) | NO / weak (adjust) |
|--------|---------------------------|--------------------|
| Q2 unprompted | They raise injection / over-permissioned tools / "untrusted third-party server" without you steering | They mention cost, latency, accuracy, or "nothing really" |
| Q3 behavior | They already **built or improvised** something (a review step, an allowlist, a wrapper, a Slack approval) | "We just trusted it" / "haven't gotten to it" |
| Q4 buyer | A named security/platform gate exists and has **delayed a rollout** | No gate, or "we'll figure it out later" |
| Q5 wand | Reaches for security/audit/permissions | Reaches for something else |

**Decision rule after ~6 conversations:**
- **≥4 strong YES** on Q2+Q3 (unprompted concern *and* prior action) → thesis holds. Build the inline enforcer, and let Q4 checklists define the policy rules.
- **Mixed, but Q5 consistently points elsewhere** (e.g. everyone says *cost* or *evals*) → the gateway position is right, the *use* is wrong. Re-aim the same proxy at that pain (you already have `cost_commands.py`).
- **Mostly weak/NO** → the pain isn't present yet. Keep `intentus-scan` as a free OSS credibility asset, but do **not** invest months. Re-test in a quarter.

---

## Anti-patterns (how this goes wrong)

- **Pitching.** The moment you explain the scanner, the data is contaminated.
- **Leading with "security."** If you say it first, they'll agree to be agreeable. Make them say it.
- **Counting compliments.** "Cool idea" / "I'd totally use that" is noise, not a signal. Only past behavior and committed resources count.
- **Talking to the wrong people.** Five people who've never shipped MCP teach you nothing.
- **Asking about the future.** "Would you…" / "Will you…" answers are worthless. Anchor every question in what already happened.

---

## Logging template (one per conversation)

```
Person / role / company stage:
Have they shipped MCP→tools in prod? (Y/N):
Q2 unprompted concern (verbatim):
Q3 what they actually did:        [built / improvised / nothing]
Q4 named gate + did it block a rollout?:
Q5 wand wish:
Strong YES on Q2+Q3? (Y/N):
Best quote:
Surprise / thing I didn't expect:
```

Fill the template **immediately** after each call. The surprises are where the
real product is — more than the answers you predicted.
