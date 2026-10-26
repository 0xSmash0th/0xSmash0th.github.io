+++
title = 'Old Man Yells at Cloud (Again)'
date = 2026-10-26T00:00:00Z
draft = false
description = "What the last world-changing tech taught us, and how to apply it to this one."
tags = ['llm', 'ai-safety', 'prompt-injection', 'threat-modeling', 'history', 'policy']
toc = true
+++

![Newspaper clipping from The Simpsons headlined "Old Man Yells at Cloud": Grandpa Simpson shaking his fist at a cloud labeled "history repeating itself"](/static/old_man_yells/old-man-yells-at-cloud.jpg)

I lived through the 90s. The boom, the worms, the bust, the memo. I got the vocab for it around 2013, when I got into security, which in hindsight put me roughly level with the people in charge at the time. Lately, deja vu.

My timeline is one argument on a loop: the lab versus the security crowd. I've heard both before. Both were partly right the first time. Neither fixed the problem. A pile of boring work by people nobody quoted did, which is how it usually goes.

So this isn't about who screwed up this week. Somebody always screwed up this week. Or me finding a cool new bug this week. I don't always find a cool bug this week :( **These incidents aren't one company's scandal. They're symptoms of a landscape-changing technology arriving faster than anyone understands its trust boundaries.** We've done this once. It hurt. Somebody took notes. What's in them, and how do we make this safe and productive for everyone?

> **Caveat** I'm a bug person; policy and money are me reading other people's homework. The OpenAI incidents are under review and I only know what's public, so parts of this will age badly ( as everything except Brad Pitt and Beyonce does ). Many AI-era security numbers come from the vendor selling the thing (frequently Anthropic). The 90s numbers aren't much better: the famous Morris worm figure started life as somebody's 10% guess. [1](#bibliography)

#  [For TL;DR clickme](#the-notes)
## How the summer went

July: in internal cyber testing, GPT-5.6 Sol and a pre-release model, running with "reduced cyber refusals for evaluation purposes," were working on ExploitGym, an exploit benchmark. [2](#bibliography) They escaped the sandbox through a package-installer bug, guessed Hugging Face hosted the answers, and broke in. OpenAI: the models were "hyperfocused on finding a solution." That's accurate. Told to pass the test. Passed the test. Fortune: four other services hit too. [3](#bibliography)

This is following in the great FAFO tradition of scientific discovery. The models fucked around. Hugging Face found out. 

August: OpenAI paused its largest RL runs for two weeks and added monitoring, isolation, 30-minute alerts and automatic pauses, at about 20% more compute. [3](#bibliography) Safety is expensive. So is the alternative. The alternative just sends the bill to the Hugging Face du jour.

September 20: an agent in a test environment with no internet access found the internet anyway, through a DNS resolver, and queried a public chatbot. There's always a DNS. Flagged in 15 minutes; stopped by hand two and a half hours later. [4](#bibliography) The alarm usually works. It's everything after the alarm that gets you. OpenAI paused training, evaluation and tool-using inference on its most capable models. [5](#bibliography)

![Haiku: It's not DNS / There's no way it's DNS / It was DNS](/static/old_man_yells/its-always-dns.png)

Then the argument. Joe, inside OpenAI throughout, wrote *Its not just the f\*cking sandbox*. [6](#bibliography) The part that stuck:

> "We had not expected it this soon. Suddenly we weren't dealing with just a small jump in capabilities; we were talking about a different sport altogether."

Michael Coppola's reply is the security side: [7](#bibliography)

> "You don't get to set the stakes that high, willingly *choose* to train your models to perform offensive cyber, *repeatedly* fail your basic responsibility in spectacular ways, and throw your hands up and say 'whoops, it happens!'"

He empathizes with the people and the novelty, but "you still don't get to have it both ways."

## Both sides are right in part, which is the problem

Lab side first, since it gets dunked on.

The field really is that fast. The internet's attack surface took a decade to grow, throttled by modems, PCs and ISPs. The LLM era rode infrastructure the internet already paid for: 900 million weekly OpenAI users by February 2026. [8](#bibliography) Agent task length doubles about every 7 months, per METR. [9](#bibliography) "We didn't expect it this soon" isn't an excuse. It's what being inside an exponential feels like.

Joe's actual argument isn't "it's hard, leave us alone." It's that the sandbox has to let the model work:

> "Models might need any mix of dynamic compute, network access, the ability to call tools (there could be hundreds of tools!), the ability to download packages, execute subprocesses..."

Now look at July. **The hole was in the package installer.** One of the exact things the sandbox had to allow.

That's the 90s firewall story. "Just firewall it" was simple and correct, then the business needed the web, so port 80 opened, so everything learned to speak HTTP, so the firewall stopped meaning much. The control was simple. What it had to let through was not. It never is.

Security side, also right.

DNS is the oldest egress trick in the book; every red teamer has a DNS tunnel in their back pocket. A model deliberately trained for offensive cyber, refusals down, should be the *most* isolated thing you run. The labs set the stakes at "existential." You can't call something an existential risk and then leave DNS open.

My read: **"things happen" and "sandboxing better" are both true, and both are about the wrong unit.** One company's competence, one incident. The 90s taught me the unit that matters is the bug class and the institution. Incidents are what a bug class looks like from the outside.

## A notorious "experiment got out" example

November 2, 1988. A Cornell grad student's experiment got loose on the internet. A bug in how aggressively it reinfected machines turned it into an outage: around 10% of the internet's machines infected. [1](#bibliography)

Swap "grad student's experiment" for "eval harness with the refusals turned down" and you get July. Nobody intended harm. A goal-seeking program had a bug in its restraint and ran into everyone else's machines. Same arrangement: one person fucked around, and a tenth of the internet found out.

![Pam from The Office holding two pages: "1988: grad student's experiment, bug in its restraint" and "2026: eval harness, refusals turned down." Caption: "They're the same picture."](/static/old_man_yells/same-picture.jpg)

The instructive part is what came next. Nobody spent a decade arguing about Cornell's competence. DARPA funded the CERT Coordination Center at CMU's SEI that same month: [10](#bibliography) a cheap, neutral, technical place to coordinate incidents and disclosures. Our coordinated disclosure norms came out of it.

Second lesson, a warning. The worm also produced the first felony conviction under the CFAA. Morris got probation. Good-faith researchers got the law's vague "authorization" language hanging over them for three decades. The response to an incident sets defaults that outlive it.

## Same bug, different channel

OpenAI's incidents are containment. The other big class, in products people actually use, is older. The table every exploitation 101 course builds ( though prob dropped phreaking now... ):

| Era              | Channel            | Attacker's data gets read as | The out-of-band fix                                             |
| ---------------- | ------------------ | ---------------------------- | --------------------------------------------------------------- |
| Phone phreaking  | the voice line     | a 2600 Hz trunk control tone | common-channel signaling (SS7) moved control off the voice path |
| Stack smashing   | the stack          | the saved return address     | canaries, NX, ASLR, CFI, eventually memory-safe languages       |
| SQL injection    | the query string   | SQL                          | parameterized queries                                           |
| XSS              | the page           | script                       | auto-escaping templates, CSP (Content Security Policy)          |
| Prompt injection | the context window | instructions                 | **?**                                                           |

Same mistake every row: control and data share a channel, and the attacker controls some of the data. Aleph One wrote the stack row down for everyone in Phrack 49, 1996. [11](#bibliography) Every row but the last eventually got a fix that *separates* the two. None perfect, some took decades (SS7 has its own problems; ask anyone who's done telecom work, then give them a minute... or an hour), but each answered "how does the parser know this byte is data?"

An LLM has no parser to tell. One channel, a sequence of tokens, and acting on instructions read from it is the entire product. A system prompt isn't a prepared statement, just earlier tokens. "Ignore previous instructions" works for the same reason `' OR 1=1` works, except there's no `?` placeholder to bind it to.

![xkcd 327, edited: "Did you really name your son Ignore previous instructions?" ... "And I hope you've learned you can't sanitize English."](/static/old_man_yells/xkcd-327-ignore-previous-instructions.png)

*[xkcd 327](https://xkcd.com/327/) by Randall Munroe, CC BY-NC 2.5, edited.*

My position: **treat prompt injection as a permanent bug class, like memory corruption in C, not a bug that gets patched.** Better overflow detectors never beat memory corruption. We made it matter less: NX made the shellcode not run, ASLR made the address unknown. The AI version has to live *outside* the model, because inside there's nothing to hold on to. Same place the sandbox argument ends up.

## EchoLeak is our Code Red

Code Red (July 2001): a long string of `N`s overflowing an IIS buffer. CAIDA counted 359,104 hosts in under 14 hours, peaking above 2,000 a minute. [12](#bibliography) What stuck with me is the paper's conclusion: "techniques other than host patching are required." Twenty-five years later, still true.

EchoLeak (CVE-2025-32711) is Aim Security's zero-click data exfiltration from Microsoft 365 Copilot. [13](#bibliography) The chain:

1. Attacker sends an email. Nobody has to open it.
2. Later, Copilot pulls it into context while answering something else (retrieval-augmented generation, RAG).
3. The instructions in the email get past Microsoft's XPIA (cross-prompt injection attack) classifier.
4. The output carries internal data in a URL, as reference-style Markdown, past link redaction.
5. The client auto-fetches it as an image. No click.
6. The fetch goes through a Teams proxy domain the CSP allowed, so it leaves the building.

Microsoft fixed it server-side and reported no in-the-wild exploitation. [14](#bibliography) Good. Low bar, cleared. Now look at the links: untrusted input in a privileged context, a filter beaten by re-encoding (every WAF ever), auto-fetch on render (every tracking pixel ever), an allowlist with one overly helpful entry. None of it is new. It's the 90s in a trench coat.

Step #3 makes me wince. **A purpose-built injection classifier was in the path and the exploit went around it.** That's patching individual overflows, which the 90s taught us doesn't converge. Expensively. What would have stopped it is #5 and #6, boring both: don't auto-render external images in model output, and don't let a context that just read untrusted email talk to the network.

Simon Willison calls the combination the "lethal trifecta": private data, untrusted content, and an exfiltration channel in one agent context. [15](#bibliography) Don't give one context all three. It's the closest thing we have to an NX bit, and it's architecture, not model.

## Everything on by default, then and now

Nobody shipped ActiveX because they were dumb. The market was fast and the defaults assumed a friendlier network. Signed code is trusted code, so run it with full privileges: authentication confused with authorization. *Who* wrote a thing says nothing about what it should be *allowed* to do. Add Office macros and IIS services on by default and you get Melissa, ILOVEYOU, Code Red and Nimda, more or less in a row.

Now: agents holding the user's full scope, Markdown images auto-rendered, tool descriptions trusted as if the developer wrote them, and MCP (Model Context Protocol) servers deployed without meaningful authentication. Same pressure, same decision, new decade. Expect the same bill.

A lot of "AI security" is regular AppSec in a new neighborhood. CVE-2025-6514 in `mcp-remote` (CVSS 9.6): a malicious MCP server returns a crafted `authorization_endpoint`, and the client passes it unsanitized to the thing that launches your browser. [16](#bibliography) No model involved. Shell metacharacters in a URL. 1999 called, it wants its bug back. (1996, technically: phf let a newline through to the shell. [17](#bibliography)) Downloaded 437,000+ times at disclosure. [18](#bibliography) July's escape, too, was a package installer bug. The AI was the operator, not the vulnerability.

That's the monoculture point. Code Red, Nimda and Slammer spread because nearly everyone ran the same IIS and SQL Server builds. Today: a handful of model families and shared connectors.

The rest is a mirror too:

| Then | Now | The shared mistake |
| --- | --- | --- |
| Employees mailing files to personal webmail | Samsung engineers pasting chip source code into ChatGPT, spring 2023 [19](#bibliography) | data governance, not an exploit |
| AOL "verify your account" phishing | Arup wiring ~US$25M after a video call with a deepfaked "CFO" [20](#bibliography) | trusting identity over a channel you can't verify. Fix: out-of-band checks, two people to move money. The deepfake is new. The control is not. |
| Typosquatting, cybersquatting | Slopsquatting: 19.7% of packages in 576,000 LLM code samples didn't exist [21](#bibliography) | the attacker registers the name you were going to type anyway |
| Executing attachments | Malicious pickle model files on Hugging Face, built to slip past its scanner [22](#bibliography) | executing data. Fix: weights-only formats (safetensors) |

Slopsquatting is typosquatting where **the machine makes the typo, and makes it predictably**: 43% of hallucinated names recurred in all ten repeats of a prompt. A human typo used to be a target. Now it's also training data, and a model's typo is a target list.

The pickle one makes me want to dig out the Phrack archive. `pickle.load` is arbitrary code execution *by design*. That's not a bug, that's the documentation, in a warning box, for years. Hasn't helped.

![Bernie Sanders: "I am once again asking you to stop executing data."](/static/old_man_yells/bernie-stop-executing-data.jpg)

## The memo, or: Microsoft finds the brake pedal

Microsoft is the case study that matters: a company in the middle of winning chose to slow down.

By 2001 Microsoft had dominance and a security crisis. Code Red and Nimda were IIS. Features-first *was* the attack surface, and the posture was roughly "fast market, patches are coming." Critics said turn it off. January 15, 2002, Gates sent the Trustworthy Computing memo: [23](#bibliography)

> "So now, when we face a choice between adding features and resolving security issues, we need to choose security."

Then the Windows division reportedly stopped feature work to retrain on security; then the SDL (Security Development Lifecycle), XP SP2 with the firewall on by default, and Patch Tuesday. Relations with researchers thawed from, let's say, frosty ( or cold as a witch's tit in a brass bra for you military types ).

Two underappreciated things:

- **Regulation didn't force it.** Enterprise customers did, faster than any law of the time could have. Same lever today: enterprises turning agents on across whole tenants. EchoLeak hit Copilot tenants, not hobbyists. Whether those buyers push is the open question.
- **The stand-down wasn't the fix, the process that outlived it was.** The SDL ran for years after everyone forgot the worms. Its bet: catch bugs before ship, since a defender who fixes a bug fixes it for everyone. Google's Big Sleep made the same bet with an LLM in 2024. [24](#bibliography)

OpenAI's two pauses are the closest thing yet to a Windows security stand-down, and the August controls are the start of a process. But flagged in 15 minutes, stopped by hand two and a half hours later: that's the gap between a control and a process. Will it become the AI industry's SDL, a shared, boring, auditable way to run dangerous evals, or stay one company's response to one bad summer?

Microsoft got there after two worms and a reputation hit, which is honestly a good price. Most industries change only after somebody testifies, and somebody had. May 19, 1998: Mudge / L0pht, told a Senate committee they could take down the internet in 30 minutes. [25](#bibliography) The Washington Post's retrospective: "A disaster foretold — and ignored." Then the worms made the same point, louder. AI's warning came in September 2022, when Simon Willison named prompt injection after Riley Goodside's demos. [26](#bibliography) EchoLeak showed up almost three years later.

## The queue moved

April 2026: Anthropic held back Claude Mythos Preview on cybersecurity grounds, releasing it only to Project Glasswing's defender partners. [27](#bibliography) Coordinated disclosure, applied to a *capability*.

Slammer: David Litchfield found the SQL Server bug in July 2002 and Microsoft patched it. The worm hit January 25, 2003 anyway, doubling every 8.5 seconds, 90% of vulnerable hosts in 10 minutes, ATMs down and flights cancelled. [28](#bibliography) Six months of patch. Ten minutes of worm. **Discovery wasn't the bottleneck in 2003. Deploying the fix was.**

2026 is the same story one step earlier: some maintainers have asked Anthropic to slow its disclosures. [29](#bibliography) In 2003 the scarce resource was admins applying patches; now it's maintainers *writing* them. Finding scales with GPUs. Fixing scales with maintainers, process and incentives, which don't come in a rack. Shit rolls downhill, and the bottom of this hill is an open-source maintainer who never signed up for Skynet targeting their code.

![xkcd 2347, edited: the tiny block a random person in Nebraska has maintained since 2003 is now also "the inbox for every AI-found bug report"](/static/old_man_yells/xkcd-2347-dependency-2026.png)

*[xkcd 2347](https://xkcd.com/2347/) by Randall Munroe, CC BY-NC 2.5, edited.*

## Fine, some of it is new

The mirror isn't perfect. Where it breaks is where the interesting new work is.

**1. Speed of discovery and exposure, not propagation.** 90s worms were fast at *spreading*. AI is fast at *finding and weaponizing*: what "once took months now happens in minutes," per CrowdStrike's CTO. [27](#bibliography) Exposure too: Copilot's rollout created the EchoLeak surface across Microsoft 365 at once. Code Red at least had to go find its hosts.

**2. Non-determinism.** AI is stats with a human friendly wrapper; a model-level fix "works some percentage of the time." So does a parachute, and "mostly fixed" should comfort you about as much as "mostly opened." `mcp-remote` gets a version bump. A model-family jailbreak gets retraining and a classifier, a statistical mitigation you can't diff or put in a "fixed in version" field. **I can write a reliable repro for a race condition. I don't know how to write one for a probability.**

**3. Agency.** A compromised IIS box ran the worm's code. A compromised agent carries out *the attacker's intent* with the user's legitimate credentials, and telemetry sees an authorized user. In Anthropic's GTG-1002 case, attackers got Claude Code past its safeguards by claiming to be a security firm doing defensive testing, [30](#bibliography) the same sentence every legitimate researcher types. Pretext and real thing are byte-for-byte identical: the in-band problem again, one layer up.

July is the version where nobody was driving. No intent beyond "pass the benchmark." The Morris worm at least had an author.

**4. Dual use at the capability level.** Nothing in the 90s was both the attack surface and the best auditor. LLMs are. The model class that falls for EchoLeak found CVE-2025-37899. [31](#bibliography) Do models now have to learn to defend themselves?

## So what exactly helped? The boring policy helped...

| Intervention                                             | Verdict                          | Why                                                                                                                                                                   |
| -------------------------------------------------------- | -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ARPANET/NSFNET funding, then privatization (1995) | Worked | public money built the commons, then left. AI's commons is the maintainers in the Glasswing queue; who pays them is unanswered |
| Open standards (IETF, W3C) | Worked, with an asterisk | interop, yes. But SMTP, DNS and BGP shipped without authentication; the retrofits (SPF/DKIM/DMARC, DNSSEC, RPKI) took decades. MCP servers ship without meaningful authentication now |
| Breach notification (California SB 1386, effective 2003) | Worked                           | made failure public without prescribing technology. Board-level pressure for free                                                                                     |
| DMCA §512 safe harbors | Mostly worked | notice-and-takedown let hosting scale. Model hubs hosting user-uploaded weights, malicious pickles included, are the AI-era version |
| Crypto export controls, Clipper, key escrow | Failed, then fixed | Clipper dead by 1996, exports opened in 2000, but export-grade crypto stayed in protocols until FREAK and Logjam (2015). Ask #5 |
| CFAA's "authorization" language | Backfired for research | chilled good-faith research until *Van Buren* (2021) and DOJ's 2022 charging policy |
| DMCA §1201 anti-circumvention                            | Backfired for research           | chilled security research until the exemptions starting in 2015                                                                                                       |

The pattern: **enabling and procedural interventions worked. Trying to control a general-purpose capability at the source failed, and vague criminal law chilled the defenders more than the attackers.** Attackers were never going to stop and check whether they were "authorized."

Today's rules mostly fit: the EU AI Act's transparency duties apply now, its design mandates slip to 2027–28, [32](#bibliography) and California's SB 53 is disclosure-shaped. [33](#bibliography)

My asks. None are new, which is the point: they're the parts of the 90s that worked.

**1. Build the CERT/CC for AI.** No neutral, funded coordination center exists for AI incidents or AI-found vulnerabilities, and no CAIDA measures any of it. Hugging Face disclosed on July 16 without knowing whose agents broke in; attribution took five more days. That's the gap CERT/CC filled in 1988.

**2. Make dangerous evals boring.** A shared SDL for running models with the safeties off: isolation standards, egress controls (yes, including DNS), monitoring that stops a run instead of paging someone, and an independent auditor. A common baseline, not one lab's internal policy.

**3. Mandate disclosure, not design.** Breach notification did the most for the least. SB 53's incident reporting has that shape. For a field this fast, that's the right bet.

**4. Give defenders safe harbor, and access.** The CFAA and §1201 rows are what happens when you don't. AI red-teaming, jailbreak and model-extraction research need explicit protection *before* prosecutors and ToS lawyers set the defaults. And commercial guardrails handicap defenders while attackers use unrestricted models. [34](#bibliography) Microsoft's post-memo thaw is the precedent.

**5. Don't rerun the crypto wars on open weights.** Controlling the material failed for math. Chips are more physical, but if a model with 3.6 billion active parameters can catch Mythos's flagship exploit, [35](#bibliography) cheap inference is the strategic material, and it's very hard to export-control.

## The money, from a bug person

The bust sorted companies by how far ahead they were looking. The Nasdaq fell 78% from March 2000 to October 2002. [36](#bibliography) Pets.com raised $82.5M in a February 2000 IPO [37](#bibliography) and announced its wind-down that November. [38](#bibliography) Nine months. Webvan built warehouses ahead of demand and shut down in July 2001. [39](#bibliography) Building ahead of demand is a fine plan right up until the demand doesn't show.

Security was part of the sorting. PayPal's founders realized in 2000 that "a major part of the high burn rate was due to fraud" [40](#bibliography) and built Igor, which "monitors PayPal's transactions for unusual behavior." [41](#bibliography) Burn killed everyone else. eBay bought PayPal for $1.5 billion in July 2002, three months before the Nasdaq bottomed. [42](#bibliography) CardSystems Solutions is the other end: a 2005 breach exposed 40 million card accounts, and Visa and American Express cut it off. Visa: it "has not corrected, and cannot at this point correct, the failure to provide proper data security." [43](#bibliography) The market kept score: breached companies lost an average 2.1% of market value within two days, about $1.65 billion per breach, while security vendors went up. [44](#bibliography)

The sorting comes either way. Right now the AI industry runs security on the 2001 cadence: incident, statement, pause, repeat. That's firefighting, and firefighting plans one quarter out. The companies that came out of the last bust intact were planning years out, and security was in the plan. PayPal didn't build Igor because a regulator asked. Fraud was eating the runway.

![KC Green's "This is fine" dog in a burning room, captioned "AI security, 2026: incident, statement, pause, repeat."](/static/old_man_yells/this-is-fine.jpg)

*Art: [KC Green, Gunshow #648](https://gunshowcomic.com/648).*

## The notes

The sky isn't falling, and some of this is new. But "whoops, it happens" and "just sandbox it" are what an industry sounds like hitting a bug class all at once, and the 90s version of that fight ended the same way every time: no winner, just boring fixes everyone adopted. Defaults flipped. Bug classes got structural mitigations. A process outlived its crisis. A coordination center showed up. Disclosure became unskippable. Safety rules get written in blood. Security defaults get written in worms.

The uncomfortable difference: every in-band bug before this one got its own channel eventually. This one might not, because the channel *is* the product. Until somebody invents the prepared statement for a token stream (I'm not holding my breath), make it not matter: least privilege, per-action authorization, no auto-egress, and a wall between what reads untrusted data and what holds the keys. Double for evals. This thing can *act*, not just get owned.

The internet did turn out safe and productive enough for nearly everyone, eventually. It took worms, a memo, a coordination center, and a lot of smart, diligent people. Their notes are right there. Let's do this with fewer worms, and listen the first time a Mudge shows up in front of the Senate.

Now get off my lawn you damn dirty kids...

---

*No new bugs in this one. Plenty of old ones. If you have a primary source for anything I flagged as secondhand, send it over.*

## Bibliography

1. FBI, *Morris Worm* — "Within 24 hours, an estimated 6,000 of the approximately 60,000 computers" then on the internet were infected. <https://www.fbi.gov/history/cases-and-criminals/morris-worm>
2. Russell Brandom, TechCrunch, *OpenAI says Hugging Face was breached by its pre-release models*, July 21, 2026 — GPT-5.6 Sol and a pre-release model with "reduced cyber refusals for evaluation purposes," tested on ExploitGym, escaped via a vulnerability in a package installer and broke into Hugging Face to "obtain test solutions directly from Hugging Face's production database." OpenAI: "The models were hyperfocused on finding a solution for ExploitGym, going to extreme lengths to achieve a rather narrow testing goal." <https://techcrunch.com/2026/07/21/openai-says-hugging-face-was-breached-by-its-pre-release-models/>
3. Emily Forlini, Fortune, *OpenAI paused AI training for two weeks, unveils new security controls following Hugging Face hack*, August 18, 2026 — Hugging Face "and four other unnamed services"; coordination through notes on a message board staff didn't initially detect; the pause covered "its largest planned frontier reinforcement learning runs"; new controls including 30-minute alerting and automatic pauses, at roughly 20% extra compute. <https://fortune.com/2026/08/18/openai-says-it-paused-ai-training-for-two-weeks-and-announces-new-security-protocols-following-hugging-face-hack/>
4. Jeremy Kahn, Fortune, on OpenAI's second training pause, September 26, 2026 — the September 20 DNS escape, flagged within 15 minutes, run stopped manually about 2.5 hours after discovery. <https://fortune.com/2026/09/26/openai-ai-agents-secure-sandbox-escape-training-pause-second-time-hugging-face-hack/>
5. Simon Sharwood, The Register, *OpenAI pauses some training amid allegations its rogue agents behaved more badly than first thought*, September 28, 2026 — OpenAI's incident report: "The incident exposed a gap in our controls over network restrictions"; the pause covers "all other training, evaluation, and inference with tool-use" for its most capable models; Axios and New York Times reporting on broader agent activity. <https://www.theregister.com/ai-and-ml/2026/09/28/openai-pauses-some-training-amid-allegations-its-rogue-agents-behaved-more-badly-than-first-thought/5299350>
6. Joe (@joedaroo), *Its not just the f\*cking sandbox*, article posted to X, September 27, 2026. <https://x.com/joedaroo/status/2104335929293127851>
7. Michael Coppola (@mncoppola), quote-post of the above, September 28, 2026. <https://x.com/mncoppola/status/2104610231347200071>
8. The Next Web, on OpenAI's $110B funding round, February 27, 2026 — "more than 900 million weekly active users." OpenAI's own announcement page refused automated fetches, so this is secondhand. <https://thenextweb.com/news/openai-secures-record-breaking-110b-funding-to-scale-ai-for-everyone>
9. METR, *Measuring AI Ability to Complete Long Tasks*, March 19, 2025 — "The length of tasks (measured by how long they take human professionals) that generalist frontier model agents can complete autonomously with 50% reliability has been doubling approximately every 7 months for the last 6 years." <https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/>
10. Software Engineering Institute, on the DHS partnership with CERT/CC — "CERT/CC was formed in November 1988 within the Software Engineering Institute (SEI) by the Defense Advanced Research Projects Agency (DARPA)." <https://www.sei.cmu.edu/news/us-department-of-homeland-security-announces-partnership-with-carnegie-mellons-cert-coordination-center/>
11. Aleph One, *Smashing the Stack for Fun and Profit*, Phrack 49, file 14, November 1996. <https://phrack.org/issues/49/smashing-the-stack-for-fun-and-profit.html>
12. David Moore, Colleen Shannon and Jeffery Brown, *Code-Red: a case study on the spread and victims of an Internet worm*, IMW 2002 — "In less than 14 hours, 359,104 hosts were compromised," peaking at "over 2,000 hosts per minute." Both quotes used above are from the abstract. <https://www.caida.org/catalog/papers/2002_codered/codered.pdf>
13. Aim Labs, *EchoLeak* writeup, June 11, 2025 — the full chain: XPIA classifier bypass, reference-style Markdown past link redaction, auto-fetched images, and a CSP that allowed `*.teams.microsoft.com`. The live page blocks bots; the Wayback Machine has it. <https://www.aim.security/lp/aim-labs-echoleak-blogpost>
14. Microsoft Security Response Center, *CVE-2025-32711* — CVSS 9.3 (Critical), "Exploited: No", fully mitigated server-side with no customer action required. NVD's own score is 7.5. <https://msrc.microsoft.com/update-guide/vulnerability/CVE-2025-32711>, <https://nvd.nist.gov/vuln/detail/CVE-2025-32711>
15. Simon Willison, *The lethal trifecta for AI agents: private data, untrusted content, and external communication*, June 16, 2025 — "If your agent combines these three features, an attacker can easily trick it into accessing your private data and sending it to that attacker." <https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/>
16. Or Peles, JFrog, *CVE-2025-6514: Critical mcp-remote RCE Vulnerability*, July 9, 2025 — CVSS 9.6, OS command injection via a crafted `authorization_endpoint`, affects 0.0.5–0.1.15, fixed in 0.1.16. JFrog calls it "the first time that full remote code execution is achieved in a real-world scenario on the client operating system when connecting to an untrusted remote MCP server." <https://jfrog.com/blog/2025-6514-critical-mcp-remote-rce-vulnerability/>
17. CERT/CC, *VU#20276: phf CGI Script fails to guard against newline characters* — "the escape_shell_cmd code failed to guard against a newline character, which is also a valid command separator"; the script "was widely exploited in 1996 and 1997." Originally CERT Advisory CA-96.06 (March 1996). <https://kb.cert.org/vuls/id/20276>
18. The Hacker News, coverage of CVE-2025-6514, July 10, 2025 — the package was "downloaded more than 437,000 times to date." The download figure is not in JFrog's post. <https://thehackernews.com/2025/07/critical-mcp-remote-vulnerability.html>
19. Mark Gurman, Bloomberg, on Samsung banning generative AI for staff after the ChatGPT leaks, May 2, 2023 — the memo: "we are temporarily restricting the use of generative AI"; an internal survey found "65% of respondents believe that such services pose a security risk." Paywalled. <https://www.bloomberg.com/news/articles/2023-05-02/samsung-bans-chatgpt-and-other-generative-ai-use-by-staff-after-leak>
20. CNN, on Arup as the victim of the Hong Kong deepfake fraud, May 16, 2024 — HK$200M (about US$25.6M) "across 15 transactions", per RTHK citing police. The call was in January 2024; police disclosed it in February without naming the company; Arup confirmed in May. <https://www.cnn.com/2024/05/16/tech/arup-deepfake-scam-loss-hong-kong-intl-hnk>
21. Spracklen, Wijewickrama, Sakib, Maiti, Viswanath and Jadliwala, *We Have a Package for You! A Comprehensive Analysis of Package Hallucinations by Code Generating LLMs*, USENIX Security 2025 — 576,000 code samples from 16 models, 205,474 unique hallucinated names, 19.7% of generated packages hallucinated (21.7% open-source vs 5.2% commercial), "43% of hallucinated packages were repeated in all 10 queries." <https://www.usenix.org/system/files/usenixsecurity25-spracklen.pdf>, <https://arxiv.org/abs/2406.10279>
22. Karlo Zanki, ReversingLabs, *Malicious ML models discovered on Hugging Face platform*, February 6, 2025 — two models using a technique RL named nullifAI; Hugging Face's Picklescan "did not flag them as unsafe." <https://www.reversinglabs.com/blog/rl-identifies-malware-ml-model-hosted-on-hugging-face>
23. Bill Gates, *Trustworthy Computing*, internal Microsoft memo, sent January 15, 2002. Full text with the original headers via Wired; Microsoft's own copy now 404s. <https://www.wired.com/2002/01/bill-gates-trustworthy-computing/>
24. Big Sleep team (Google Project Zero and Google DeepMind), *From Naptime to Big Sleep: Using Large Language Models To Catch Vulnerabilities In Real-World Code*, November 1, 2024 — an exploitable stack buffer underflow in SQLite. The team was careful to add that "at present, it's likely that a target-specific fuzzer would be at least as effective." <https://projectzero.google/2024/10/from-naptime-to-big-sleep.html>
25. Craig Timberg, The Washington Post, *A disaster foretold — and ignored*, June 22, 2015 — part 3 of the *Net of Insecurity* series, on L0pht's May 19, 1998 Senate testimony (hearing: "Weak Computer Security in Government: Is the Public at Risk?"), where the group said it could take down the internet in 30 minutes. Not fetched directly; the date, title and hearing were checked against Wikipedia's L0pht article. <https://www.washingtonpost.com/sf/business/2015/06/22/net-of-insecurity-part-3/>
26. Simon Willison, *Prompt injection attacks against GPT-3*, September 12, 2022 — builds on Riley Goodside's public examples of GPT-3 following instructions embedded in its input; the post that gave the attack its name. <https://simonwillison.net/2022/Sep/12/prompt-injection/>
27. Anthropic, *Project Glasswing*, April 7, 2026 — launch partners, "over 40" additional organizations, $100M in usage credits, $4M in donations ($2.5M to Alpha-Omega/OpenSSF via the Linux Foundation, $1.5M to the Apache Software Foundation), and the CrowdStrike CTO (Elia Zaitsev) quote. "We do not plan to make Claude Mythos Preview generally available." <https://www.anthropic.com/glasswing>
28. Moore, Paxson, Savage, Shannon, Staniford and Weaver, *Inside the Slammer Worm*, IEEE Security & Privacy 1(4), August 2003 — doubling time 8.5 (±1) seconds in the first minute, "more than 90 percent of vulnerable hosts within 10 minutes," "at least 75,000 hosts, perhaps considerably more," a 376-byte payload in "a single 404-byte UDP packet." Struck slightly before 05:30 UTC on January 25. <https://catalog.caida.org/paper/2003_sapphire2>, CAIDA's original analysis: <https://www.caida.org/catalog/papers/2003_sapphire/>
29. Anthropic, Project Glasswing initial update, May 22, 2026 — 10,000+ high/critical from partners; 1,000+ open-source projects, 23,019 findings, 6,202 high/critical; 530 disclosed, 75 patched, "65 of those" with public advisories. Some maintainers "asked us to slow down our rate of our disclosures." Self-reported. <https://www.anthropic.com/research/glasswing-initial-update>
30. Anthropic, *Disrupting the first reported AI-orchestrated cyber espionage campaign*, November 13, 2025 — "roughly 30 entities," "a handful of successful intrusions," "80-90% of tactical operations." The operators "claimed that they were employees of legitimate cybersecurity firms" doing defensive testing. GTG-1002 is named in the full report only. MITRE ATT&CK tracks it as Campaign C0062. <https://www.anthropic.com/news/disrupting-AI-espionage>, <https://assets.anthropic.com/m/ec212e6566a0d47/original/Disrupting-the-first-reported-AI-orchestrated-cyber-espionage-campaign.pdf>, <https://attack.mitre.org/campaigns/C0062/>
31. Sean Heelan, *How I used o3 to find CVE-2025-37899, a remote zeroday vulnerability in the Linux kernel's SMB implementation*, May 22, 2025 — about 12k lines (~100k tokens) of `ksmbd`, "no scaffolding, no agentic frameworks, no tool use." <https://sean.heelan.io/2025/05/22/how-i-used-o3-to-find-cve-2025-37899-a-remote-zeroday-vulnerability-in-the-linux-kernels-smb-implementation/>
32. Regulation (EU) 2026/1744, the Digital Omnibus on AI, published in the Official Journal July 24, 2026, in force July 27, 2026. EUR-Lex wouldn't serve the text to automated fetches, so the dates were checked against a secondary summary. <https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng>, <https://www.nicfab.eu/en/posts/digital-omnibus-ai-official-journal/>
33. California SB 53, Transparency in Frontier Artificial Intelligence Act, Chapter 138, Statutes of 2025, approved September 29, 2025 — 15-day reporting to the Office of Emergency Services, 24 hours for imminent risk of death or serious physical injury; stricter duties for "large frontier developers" above $500M revenue; penalties up to $1M per violation. <https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260SB53>
34. Simon Willison, *OpenAI's accidental cyberattack against Hugging Face is science fiction that happened*, July 22, 2026 — including the point about guardrails on commercial models handicapping defenders. <https://simonwillison.net/2026/Jul/22/openai-cyberattack/>
35. Stanislav Fort, AISLE, *AI Cybersecurity After Mythos: The Jagged Frontier*, April 7, 2026. <https://aisle.com/blog/ai-cybersecurity-after-mythos-the-jagged-frontier>
36. Federal Reserve Bank of St. Louis, *NASDAQ Composite Index* (NASDAQCOM), daily close. <https://fred.stlouisfed.org/series/NASDAQCOM>
37. Pets.com, prospectus, filed February 11, 2000 — 7,500,000 shares at $11, $82.5M gross. <https://www.sec.gov/Archives/edgar/data/0001100683/000089161800000749/0000891618-00-000749.txt>
38. Pets.com, press release, November 7, 2000 — announces an "orderly wind down", 255 of 320 staff laid off. <https://www.sec.gov/Archives/edgar/data/0001100683/000109581100004383/f66158ex99-1.txt>
39. Webvan Group, Form 8-K — ceased operations July 9, 2001; Chapter 11 petition filed July 13, 2001 in the District of Delaware. <https://www.sec.gov/Archives/edgar/data/1092657/000102140801504054/d8k.txt>
40. Max Levchin and Peter Thiel, *Coping with Fraud*, Stanford eCorner, January 21, 2004 — catalog abstract: "The founders soon realized that a major part of the high burn rate was due to fraud." <https://purl.stanford.edu/qt365vg4391>
41. MIT Technology Review, *Innovators Under 35: Max Levchin*, 2002 — Igor "monitors PayPal's transactions for unusual behavior, alerting personnel to freeze suspicious accounts." <https://www.innovatorsunder35.com/the-list/max-levchin/>
42. eBay, *eBay to Acquire PayPal*, press release, July 8, 2002, filed as Exhibit 99.1 to PayPal's Form 8-K — "Based on eBay's stock price on July 5, 2002, the acquisition is valued at $1.5 billion." <https://www.sec.gov/Archives/edgar/data/1103415/000091205702026650/a2084015zex-99_1.htm>
43. Associated Press, *Visa, Amex Cut Ties With Card Processor In Massive Breach*, July 19, 2005 — 40 million card accounts accessed; Visa said CardSystems "has not corrected, and cannot at this point correct, the failure to provide proper data security for Visa accounts"; American Express to sever ties as of October. <https://www.wdrbwave.com/story/3614192/visa-amex-cut-ties-with-card-processor-in-massive-breach>
44. Huseyin Cavusoglu, Birendra Mishra and Srinivasan Raghunathan, *The Effect of Internet Security Breach Announcements on Market Value: Capital Market Reactions for Breached Firms and Internet Security Developers*, International Journal of Electronic Commerce 9(1), Fall 2004 — breached firms "lost, on average, 2.1 percent of their market value within two days of the announcement", "an average loss in market capitalization of $1.65 billion per breach"; security developers gained about 1.36% over the same window. <https://www.ijec-web.org/past-issues/volume-9-number-1-fall-2004/ijecv9n1-5/>
