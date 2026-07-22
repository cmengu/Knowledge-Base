# Knowledge base — evals

31 position(s), 1 contested. Canonical data lives in `positions.json`; this file is a rendered view.

## evals-0001 — ○ open question

**Research shows that using too many skills at once actually makes an agent substantially worse.**

_1 source(s) · same-day_

**Sources**

- "there's lots of research out there that shows that if you use very many of these, it actually makes your agent substantially worse."
  — spNAUEgq_A8 · 2026-06-29 · affirms · `spNAUEgq_A8#17`
- "the truth about inheritance is it works. It does work... Eventually, inheritance starts to break down... There's some point at which I get diminishing returns from adding additional context."
  — spNAUEgq_A8 · 2026-06-29 · mixed · `spNAUEgq_A8#20`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`spNAUEgq_A8#17`)

## evals-0002 — ○ open question

**Domain-specific (narrow) agents are substantially more token efficient than broader agents, regularly achieving over 80% token efficiency gains for a given task.**

_1 source(s) · same-day_

**Sources**

- "they are far more token efficient. Far more token efficient. We regularly see over 80% token efficiency for any given task."
  — spNAUEgq_A8 · 2026-06-29 · affirms · `spNAUEgq_A8#24`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`spNAUEgq_A8#24`)

## evals-0003 — ○ open question

**The cost and usability advantages of small models depend on the model reliably completing its narrowly scoped task; repeated failures erode both the savings and the usability benefit.**

_1 source(s) · same-day_

**Sources**

- "if DeepSeek V4 Flash fails over and over and over again to do the job, then not only is it going to be, you know, not that much cheaper, it's also going to be much more annoying to use it."
  — spNAUEgq_A8 · 2026-06-29 · mixed · `spNAUEgq_A8#28`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`spNAUEgq_A8#28`)

## evals-0004 — ⚔ contested

**The long-running decline in the cost of intelligence reversed in 2026: IQ-adjusted token costs have risen roughly 29-30% this year, and unadjusted token costs have risen roughly 76%.**

_2 source(s) · 10-day span_

**Supporting**

- "the cost of intelligence is going down. That trend reversed in 2026... They're up 29% when you adjust for IQ... tokens are up 76% this year."
  — spNAUEgq_A8 · 2026-06-29 · denies · `spNAUEgq_A8#36`

**Opposing** (contested — both stances kept)

- "GPT 5.6 Terra, I think it's in like dark blue in there. Brings GPT 5.5 level intelligence, but at half the cost."
  — pMggiOb18tc · 2026-07-09 · affirms · `pMggiOb18tc#27`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`spNAUEgq_A8#36`)
- 2026-07-22 — open-question → contested: contested — empirical disagreement, unreconciled — genuinely open: They disagree over the factual direction of intelligence costs in 2026. The existing position asserts a measured, aggregate reversal (IQ-adjusted token costs up ~29-30%, unadjusted up ~76%), while the new unit cites a specific model release as evidence that costs are still falling (same intelligence at half the cost). One flagship release halving its price does not by itself settle whether aggregate IQ-adjusted costs rose this year, and neither side presents data covering the other's scope, so the disagreement remains an unresolved question of measurement. (`pMggiOb18tc#27`)

## evals-0005 — ○ open question

**Being able to distinguish good skills from bad skills for AI agents is becoming increasingly important.**

_1 source(s) · same-day_

**Sources**

- "the ability to distinguish good skills from bad skills is only getting more important"
  — UNzCG3lw6O0 · 2026-06-29 · affirms · `UNzCG3lw6O0#0`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`UNzCG3lw6O0#0`)

## evals-0006 — ○ open question

**The root cause of 'skill hell' is the absence of a shared rubric or framework for evaluating what makes a skill great.**

_1 source(s) · same-day_

**Sources**

- "the thing that we're missing is we don't know what makes a skill great...There's no shared rubric, no framework for looking at a skill and making it better"
  — UNzCG3lw6O0 · 2026-06-29 · affirms · `UNzCG3lw6O0#2`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`UNzCG3lw6O0#2`)

## evals-0007 — ◔ emerging trend

**Model-invoked skills are unpredictable because the model can decline to invoke a skill even when it is a perfect fit for the task, which forces developers to build evals to verify that skills are invoked at the right time.**

_2 source(s) · 15-day span_

**Sources**

- "the model may just choose not to follow it, you know, even if it's absolutely perfect for the task, it may just choose not to invoke the skill."
  — UNzCG3lw6O0 · 2026-06-29 · affirms · `UNzCG3lw6O0#11`
- "I much prefer removing that level of unpredictability, imposing a bit more cognitive load on the user, and what you get is just you're removing a class of problem from even being a problem."
  — UNzCG3lw6O0 · 2026-06-29 · affirms · `UNzCG3lw6O0#12`
- "we have seen 50% of the failures uh because the skill was not triggered correctly because the prompt of the user was not uh detailed enough for the model to understand"
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#25`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`UNzCG3lw6O0#11`)
- 2026-07-22 — open-question → emerging-trend: emerging — 2 independent sources so far (15d span) (`0vphxNt4wyk#25`)

## evals-0008 — ○ open question

**The effectiveness of a leading-word technique can be verified by observing whether the chosen phrase appears in the agent's reasoning/thinking traces.**

_1 source(s) · same-day_

**Sources**

- "The cool thing about this technique is you can know if it's worked because you say vertical slice in your skill, and then you'll notice in the reasoning traces that it's saying, "Okay, we're going to do this as a thin vertical slice.""
  — UNzCG3lw6O0 · 2026-06-29 · affirms · `UNzCG3lw6O0#21`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`UNzCG3lw6O0#21`)

## evals-0009 — ○ open question

**Skills can be kept small and effective by systematically applying deletion tests, compacting instructions into leading words, and removing irrelevant content and sediment.**

_1 source(s) · same-day_

**Sources**

- "it's just using these techniques, using deletion tests, using um making sure that I compact things into leading words, I don't have anything irrelevant in there, and I don't have any sediment."
  — UNzCG3lw6O0 · 2026-06-29 · affirms · `UNzCG3lw6O0#30`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`UNzCG3lw6O0#30`)

## evals-0010 — ○ open question

**A key challenge with Fable is identifying its 'capability overhang' — discovering what tasks are newly possible with the model that were not possible before.**

_1 source(s) · same-day_

**Sources**

- "this is I think part of the challenge with Fable is figuring out this capability overhang. What is now possible?"
  — 9fubhllmsBU · 2026-07-06 · affirms · `9fubhllmsBU#8`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`9fubhllmsBU#8`)

## evals-0011 — ○ open question

**Benchmark scores for the same model vary dramatically depending on the evaluation harness used; in HarnessBench, the same model scored between 52.4% and 76.2% — a swing of more than 20 points — with only the harness changed.**

_1 source(s) · same-day_

**Sources**

- "scores range from 52.4% to 76.2%. So, more than a 20-point difference, and only the harness changed."
  — 2e9ANoOEn28 · 2026-07-07 · affirms · `2e9ANoOEn28#5`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`2e9ANoOEn28#5`)

## evals-0012 — ○ open question

**The PFA version of the agent is the best demonstrated so far because it produces the correct solution without any human input, although it still does not actually apply the fix to the code itself.**

_1 source(s) · same-day_

**Sources**

- "this version of this agent is the best one we've seen so far because it does give us the correct solution without any human input needed, but it hasn't actually fixed the code."
  — 2e9ANoOEn28 · 2026-07-07 · mixed · `2e9ANoOEn28#25`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`2e9ANoOEn28#25`)

## evals-0013 — ○ open question

**Self-optimization is a major advance because it replaces trial-and-error prompt tweaking (guess-and-check) with a systematic, measurable process for improving agent performance.**

_1 source(s) · same-day_

**Sources**

- "the reason this self-optimization is so great is because we're not guessing and checking. We're systematically measuring and improving, which is a big leap forward."
  — 2e9ANoOEn28 · 2026-07-07 · affirms · `2e9ANoOEn28#36`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`2e9ANoOEn28#36`)

## evals-0014 — ○ open question

**Given equal time on a medium-length computer task, current AI models typically outperform an average person on the average task.**

_1 source(s) · same-day_

**Sources**

- "if you pick like a medium length computer task and you give me and the model the same amount of time to get that task done, probably at least in my case, the model will do a better job than me for the average task."
  — pMggiOb18tc · 2026-07-09 · affirms · `pMggiOb18tc#11`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`pMggiOb18tc#11`)

## evals-0015 — ○ open question

**The Luna model outperforms several notable models on the featured benchmark while being priced at only $1 per million input tokens and $6 per million output tokens, making it exceptional value for its performance.**

_1 source(s) · same-day_

**Sources**

- "Luna there beats some pretty notable models in this eval. But at only $1 per million input tokens and $6 per million output tokens... that is insane value."
  — pMggiOb18tc · 2026-07-09 · affirms · `pMggiOb18tc#28`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`pMggiOb18tc#28`)

## evals-0016 — ○ open question

**GPT 5.6 Sol running on Cerebras hardware delivers frontier-level intelligence at approximately 750 tokens per second.**

_1 source(s) · same-day_

**Sources**

- "this is GPT 5.6 Soul running on Cerebras, the frontier intelligence at now 750 tokens a second."
  — pMggiOb18tc · 2026-07-09 · affirms · `pMggiOb18tc#29`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`pMggiOb18tc#29`)

## evals-0017 — ○ open question

**As AI agents improve at self-verification and correctness checking, the human role in checking correctness is decreasing over time.**

_1 source(s) · same-day_

**Sources**

- "the role of humans in correctness checking is decreasing."
  — WkBPX-oDMnA · 2026-07-10 · affirms · `WkBPX-oDMnA#4`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`WkBPX-oDMnA#4`)

## evals-0018 — ○ open question

**Reduced human involvement in correctness-checking is acceptable, provided the human's intent is clear and the agent executes it correctly.**

_1 source(s) · same-day_

**Sources**

- "And you know what? I actually don't hate that. If I have a clear idea of what I want to do, and the agent does it correctly... I'm into it."
  — WkBPX-oDMnA · 2026-07-10 · affirms · `WkBPX-oDMnA#5`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`WkBPX-oDMnA#5`)

## evals-0019 — ○ open question

**The vast majority of publicly shared skills lack evals — Skill Bench indexed over 50,000 skills and found almost none had evals, with most being AI-written and untested, making it hard to assess skill quality given agent non-determinism.**

_1 source(s) · same-day_

**Sources**

- "Skill Bench is a very popular and nice like eval or benchmark which um index like over like 50,000 skills from like it up and like try to look into him and almost none of those skills had evals. Most of them were AI written um not really tested"
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#0`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#0`)

## evals-0020 — ○ open question

**Preference skills — skills encoding company- or domain-specific knowledge that foundation models lack — should be protected with evals so that agent or model updates do not silently degrade performance on those domain-specific preferences.**

_1 source(s) · same-day_

**Sources**

- "those uh preference skills are then protected with e-walls where because most of like the foundation models might not uh integrate the knowledge which is very specific to your use case or your domain."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#4`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#4`)

## evals-0021 — ○ open question

**According to the Skill Bench 1.1 evaluation across open and closed models and multiple harnesses, skills are effective, improving model performance by roughly 15% on average.**

_1 source(s) · same-day_

**Sources**

- "do skills work? Yes, they do work and I going back to a skills bench which has an update of 1.1 which has evaluated all kinds of open and closed models in different harnesses showing that skills on average improve the performance by roughly 15%."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#5`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#5`)

## evals-0022 — ○ open question

**Human-written skills outperform AI-generated skills and are the best skills you can provide to AI agents.**

_1 source(s) · same-day_

**Sources**

- "human-written skills are the best we can provide."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#7`
- "AI-generated skills can uh impact performance negatively."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#8`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#7`)

## evals-0023 — ○ open question

**Teams should test skills early with a small eval set of roughly 10-20 prompts per skill — about five covering the happy path and five covering cases where the skill should not trigger — and should incorporate real production traces into these tests when available.**

_1 source(s) · same-day_

**Sources**

- "Always try to create 10 of 20 prompts. I like to create five for like the happy path... Five when I don't want to use that skill just to make sure the model is not over triggering... nothing is better than than real-world data."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#18`
- "include negative tests. Uh we always forget negative tests. Start small. Even like 10 to 20 skill eval samples are better than nothing. You will be surprised on how much you will find even from like five to 10 examples."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#27`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#18`)

## evals-0024 — ○ open question

**AI-generated skills tend to contain many 'no-ops' — instructions that do not actually change agent behavior (e.g., telling the model to make code easy to read) — and these no-op instructions should be identified and removed from skills.**

_1 source(s) · same-day_

**Sources**

- "AI generated skills tend to include a lot of no-ops. And no-ops basically is an instruction which does nothing to change the agent's behavior. It's like before making an implementation easy to read."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#19`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#19`)

## evals-0025 — ○ open question

**Teams should periodically run evals with a skill enabled and disabled, and retire the skill if the model performs just as well without it, in order to save token cost and reduce maintenance burden.**

_1 source(s) · same-day_

**Sources**

- "always try to run evals with and without the skill enabled. And if the model achieves the performance without even like triggering the skill, you know you can retire that skill, save the cost uh for your tokens"
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#20`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#20`)

## evals-0026 — ○ open question

**Most skill evals can be implemented as simple, cheap regex-based assertions (e.g., checking for the correct SDK, model, methods, and the absence of deprecated patterns) that are easy to update and rerun, while LLM-as-judge evaluation is better reserved for complex skills that require judging whole traces.**

_1 source(s) · same-day_

**Sources**

- "most of the tests or evals for skills can be regex... it's really for us it was all about, 'Okay, do we use the correct SDK? Do we use the correct um model?'... But of course, you can use LLM as a judge if you have like more complex skills"
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#23`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#23`)

## evals-0027 — ○ open question

**Skill evals should assert on task outcomes rather than on the specific trajectory the model takes — e.g., it should not matter on which turn the skill loads, only whether the model achieves the task from the prompt.**

_1 source(s) · same-day_

**Sources**

- "definitely like create outcomes, not paths. Uh we don't want to test if the model loads the skill on like the first turn. We really want to test if it can achieve the task based on the prompt."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#28`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#28`)

## evals-0028 — ○ open question

**Skill evals should be run in isolated environments, because coding agents are adept at 'cheating' — retrieving context from prior chats or other executions instead of genuinely exercising the skill under test.**

_1 source(s) · same-day_

**Sources**

- "coding agents are very good at finding or cheating. So, if you run inside uh your existing environment, it might look up previous chats or it might look up some other executions and then like try to cheat it and get the context from the skill without even using the skill."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#29`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#29`)

## evals-0029 — ○ open question

**Because model outputs are non-deterministic, skill evals should run multiple trials (roughly two to six) per test case in order to reliably measure skill performance.**

_1 source(s) · same-day_

**Sources**

- "definitely run more than one trial when running evals. Like agents, our models are non-deterministic... always run the to six uh trials per case and to measure reliability"
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#30`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#30`)

## evals-0030 — ○ open question

**Skill evals should be tested across multiple agent harnesses and models rather than a single one, because a skill's effectiveness can vary significantly depending on the harness and model used.**

_1 source(s) · same-day_

**Sources**

- "test across different harnesses... not only just evaluate against Claude or anti-gravity... maybe your skill is very good with a Gemini but very bad with Codex and then you have uh customers, consumers using your harness with Codex and then it fails."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#31`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#31`)

## evals-0031 — ○ open question

**When a skill is retired because the model no longer needs it, its eval should be retained and kept running so that future model or agent regressions can be detected and the skill reintroduced if performance degrades.**

_1 source(s) · same-day_

**Sources**

- "You don't need to throw that eval away because you throw the skill away. You can keep that eval to make sure that the model or the agent keeps the performance and as soon as you start seeing some degradation, you can reintroduce the skill."
  — 0vphxNt4wyk · 2026-07-14 · affirms · `0vphxNt4wyk#32`

**Status history**

- 2026-07-22 — opened as open-question: opened as a new open position (novel unit) (`0vphxNt4wyk#32`)
