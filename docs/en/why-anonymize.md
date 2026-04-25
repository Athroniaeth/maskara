---
icon: lucide/shield-alert
---

# Why anonymize?

This page is meant to explain, for a broad audience (technical or not), why it is preferable to anonymize personal data before sending it to an LLM, **independently of `piighost`**. The goal is not to sell you this library, but to lay out a case you can present to a decision-maker or a skeptical interlocutor.

!!! abstract "Summary"
    When you send text to an LLM hosted by a third-party provider, you no longer control who reads it, how long it is retained, or under which jurisdiction it falls. That data can be used against users by being collected and aggregated with other sources for mass surveillance, political profiling, or advertising targeting. Anonymization **before sending** is a protection that depends neither on the provider, nor on a promise, nor on the security of their infrastructure, nor on a future political decision.

The argument builds in three steps. First, **how a cloud LLM works technically** and **why a provider's contractual promise is not enough**. Next, **the legal framework** that applies to these services, and its grey areas. Finally, **what anonymization concretely changes**, its mandatory uses and its limits.

---

## How a cloud LLM works

An LLM such as ChatGPT, Claude or Mistral Le Chat is not a piece of software running on your computer. It is a remote service. Your question leaves your machine, travels across the Internet, reaches the provider's servers, is processed there, and a response comes back.

!!! warning "The interface can be local, the model is not"
    Even if you use a desktop app, a browser extension, or an IDE plugin, the model is not executed on your machine. Only the interface is. The computation happens in the provider's cloud. The term "local LLM" refers exclusively to inference on your own hardware, via tools like `Ollama` or `llama.cpp`.

This path has several often underestimated consequences:

- The message is **received in cleartext** by the provider's infrastructure. TLS encryption protects the transit; it does not protect reading on the server side.
- It is generally **logged** for billing, abuse detection, debugging, and model improvement.
- It may be **retained for weeks, months or years**, depending on the provider's policy and any legal obligations that bind it.

Talking to a cloud LLM is, from a confidentiality standpoint, no more private than sending an email through Gmail. The provider has full technical access to the content. Everything that prevents that access is **contractual**, not technical.

---

## The limits of a contractual promise

Let us start from the most favourable assumption: the major providers (OpenAI, Anthropic, Google, Mistral and others) sincerely want to protect their users' data. Their privacy policies formalise commitments ("we do not train on your API data", "we delete after 30 days", "we reject abusive requests"), and these commitments are generally honoured.

That is not enough, because a contractual commitment can fall for three different reasons, none of which stems from bad faith on the provider's part.

### A technical incident, a bug, or an attack

No policy protects against an engineering mistake or a successful intrusion. Two cases are enough to illustrate the point.

On **March 20, 2023**, a bug in the Redis library used by OpenAI exposed ChatGPT conversation titles to other users for roughly nine hours. For about 1.2% of ChatGPT Plus subscribers active during that window, partial payment information (name, email, last four digits of the card, expiration date) was also visible to third-party accounts. OpenAI published a public post-mortem acknowledging the incident.

In **January 2025**, researchers at `Wiz Research` discovered that a DeepSeek ClickHouse database was reachable on the Internet without authentication. More than a million log lines were exposed, including conversation histories, API keys and internal infrastructure metadata.

In both cases, the data leaked without a lawsuit, without an order, and without any malicious intent from the company. A bug, a missing configuration, and the contractual perimeter loses its meaning.

### Your data being used for training

"If it's free, you're the product." The old adage of commercial web applies to LLMs too.

Running inference on a large model is expensive: each response ties up GPUs in real time and the provider pays that bill on every request. Yet OpenAI, Google and others offer very generous free tiers. Standard commercial reasons (user acquisition, de-facto standard effects) only account for part of this business model. These free tiers also fuel **training data collection**.

On consumer-grade free tiers, your conversations may be used to improve the model in several ways: explicit feedback (👍/👎, rewording, regeneration) serves as a reinforcement learning signal, exchanges can be reviewed by human annotators to identify failure modes, and the full conversation corpus can serve as raw material to build the datasets for subsequent iterations.

Paid offerings (API, ChatGPT Enterprise, Claude Team, etc.) generally exclude your data from training by default. On free tiers, by contrast, opt-out is often buried in the settings, sometimes disabled by default, and the policy can shift over time.

### A judicial order

Even when the provider *wants* to delete your data, a court can prevent it.

On **May 13, 2025**, as part of its lawsuit against OpenAI, the `New York Times` obtained from *Magistrate Judge* Ona T. Wang a **preservation order**: OpenAI was required to retain every ChatGPT conversation and API call from its customers, including those the company would normally have deleted under its own policy. OpenAI opposed the order publicly by filing a motion for reconsideration, rejected initially, then by appealing to *District Judge* Sidney Stein, who denied the appeal in June 2025. The order was ultimately lifted on **September 26, 2025** (formal termination on October 9), with users from the EEA, Switzerland and the United Kingdom having been exempted from the measure.

The matter did not end there. On **November 7, 2025**, the same *Magistrate Judge* ordered OpenAI to hand over **20 million de-identified ChatGPT logs** to the `New York Times` as evidence. OpenAI filed for reconsideration, which was denied, and then appealed. On **January 5, 2026**, *District Judge* Stein affirmed the ruling, sealing the delivery obligation.

This episode has two practical consequences. First, a provider's privacy policy is **never final**: a court decision to which you are not a party can rewrite it, force retention, or compel the massive delivery of conversations to a third party. Second, the exposure window of your data to a future leak or attack grows mechanically, and with it the probability that a public authority (American or, via international rogatory commission, foreign) will gain access to it.

---

## Legal: the law is not enough either

The instinctive response to this technical picture is to turn to the law: pick a "GDPR-compliant" provider, check the certifications, demand contractual clauses. This approach is useful but incomplete, for two reasons: US law provides legal access paths to the data, and European law has not yet produced a tested safeguard applied to LLMs.

### The US framework: CLOUD Act, FISA 702, Executive Order 12333

Three texts structure US access to provider data, and none of them is the Patriot Act.

!!! info "Why not the Patriot Act?"
    The Patriot Act (2001) often comes up in this debate, but it is no longer the right text to cite. Its best-known surveillance provision, `Section 215` (bulk collection of telephone metadata revealed by Snowden), was restricted by the `USA FREEDOM Act` in 2015, then **allowed to expire by Congress in March 2020**. It is no longer in force. Furthermore, the Patriot Act targeted counterterrorism investigations, not the question at hand ("can a US provider be compelled to hand over data stored in Europe?"). The CJEU rulings that structure today's debate do not cite the Patriot Act: they cite FISA 702 and Executive Order 12333.

- **The CLOUD Act (2018)** obliges any provider under US jurisdiction to hand over data it controls, **regardless of where that data is physically stored**. A datacenter in Ireland or France does not put the data out of reach as soon as the company is American.
- **FISA Section 702** is the legal basis for mass-surveillance programs like `PRISM`, revealed in 2013 by Edward Snowden. It allows the collection of communications via major US providers of electronic communication services.
- **Executive Order 12333** is the broader framework for surveillance by the US executive branch, without direct judicial supervision.

These three texts stack, providing legal, discreet (no prior notice to the people concerned), and non-US-citizen-applicable access paths.

### Schrems II: the CJEU rules

In **July 2020**, the Court of Justice of the European Union invalidated the `Privacy Shield`, the agreement that framed data transfers between the EU and the United States. Its reasoning, in short: FISA 702 and Executive Order 12333 are too permissive to comply with the GDPR and offer no effective judicial remedy to European citizens.

More than 5,300 companies relied on the `Privacy Shield` for their transatlantic transfers. A second agreement, the `Data Privacy Framework` (2023), replaced it, but it rests on the same US legal foundations and its durability is contested. Several complaints (notably those brought by Max Schrems' noyb association) explicitly target a third invalidation.

### Microsoft Ireland: jurisdiction beats geography

Between 2013 and 2018, US authorities demanded that Microsoft, via a warrant issued under the `Stored Communications Act`, hand over a customer's data stored on its servers in Ireland. Microsoft resisted all the way to the Supreme Court. The proceeding was never decided on the merits, because Congress passed the `CLOUD Act` in March 2018 to clarify the answer: yes, US companies must produce data wherever it is stored. The case was declared moot.

Direct consequence: **European hosting by a US provider offers no legal watertightness against the United States**. The "your data stays in Europe" marketing masks this asymmetry.

!!! note "An honest nuance on scope"
    The CLOUD Act does not apply to any company with a mere link to the United States. The entity must be **under US jurisdiction** (incorporated in the US, or controlled by a US entity) **and** hold "possession, custody, or control" of the data. A European provider with a simple US commercial subsidiary is not automatically captive: a case-by-case analysis is required.

### The European framework: a GDPR that has not yet held up on LLMs

The GDPR remains a solid tool on paper, but its application to LLMs is in its infancy. The most emblematic case illustrates this.

The `Garante`, Italy's data-protection authority (equivalent to the French `CNIL`), opened an investigation against OpenAI as early as **March 2023**. In **December 2024**, it imposed a **€15 million** fine on OpenAI for processing without a legal basis, transparency failings, and the absence of an age-verification mechanism. But in **March 2026**, the Rome tribunal annulled that decision in its entirety; the detailed grounds had not yet been made public at the time of writing. To date, no European authority has secured a final-instance sanction against a major LLM for a GDPR violation relating to the training-collection phase.

The GDPR remains powerful, but relying solely on it to protect sensitive data sent to an LLM means betting on a rampart that has yet to demonstrate its ability to hold up on appeal.

---

## Secondary uses: what collected data enables

The preceding sections explain how the data leaves your perimeter. What remains is to specify what it enables once collected. Three uses, unevenly documented, deserve to be distinguished so as not to conflate a structural risk with a proven practice.

### Mass surveillance

An LLM conversation technically resembles an email or chat: timestamped text, attached to an identifiable account. It falls within the same collection perimeter as other electronic communications covered by `FISA 702`, renewed for two years in April 2024 by `RISAA`, and whose renewal is again under debate in Congress in April 2026. Declassified `PCLOB` reports document several hundred thousand **selectors** (target identifiers) active each year, and the "about" collection (suspended in 2017, later re-authorized) mechanically broadens the perimeter to communications that are neither sent to nor by the target, but that mention it.

Whether this capability is today applied to LLM conversations or not, the legal framework and the technical architecture are in place.

### Profiling and political targeting

The concern is not speculative; it rests on documented cases of targeted surveillance in other layers of the Internet.

- **Angela Merkel, October 2013**: the Snowden revelations document NSA surveillance of the German chancellor's mobile phone, listed as a target since 2002. German sources (Süddeutsche Zeitung, NDR) indicate that Gerhard Schröder, Merkel's predecessor, had also been monitored from 2002 onwards, because of his opposition to the intervention in Iraq. Obama implicitly confirmed the surveillance by promising over the phone that it had ended; the German government publicly protested.
- **Associated Press, 2012-2013**: the `Department of Justice` secretly seized in April-May 2012 the records of more than twenty AP telephone lines, as part of a leak investigation. The agency learned of it only in May 2013, through notification *after the fact*.
- **Pegasus / NSO, 2021**: the `Forbidden Stories` coalition documents the use of the Pegasus spyware against about 180 targeted journalists, as well as activists, lawyers, diplomats and heads of state in more than 20 countries, including France, via several NSO client states.

None of these cases concerns an LLM specifically. But they establish three facts: states regularly surveil the communications of journalists, lawyers and political figures; the legal and technical tools to do so already exist; and an LLM that sees a law firm's conversations, an investigative newsroom's work, or an activist movement's messages becomes, by construction, a concentration point for high-value information.

### Commercial targeting and data brokers

The risk is different from the previous two: it requires neither a judge nor a warrant. It rests on the commercial ecosystem surrounding the providers, and unfolds in three steps.

**First, an incentive structure.** Several major LLM players have adjacent interests in targeted advertising: Google makes it its core business, Microsoft (a major OpenAI shareholder) operates `Bing Ads`, Meta pushes its own generative-AI ecosystem inside a group whose near-total revenue comes from advertising targeting. Privacy policies alone do not neutralize that incentive; they can evolve when economic pressure rises.

**Next, the current state of evidence.** There is no proof today that any provider has resold LLM conversations to data brokers. The argument therefore rests not on a proven practice but on a structural risk: data that enters a system, held by an actor who has an economic interest in exploiting it, can later leave through channels that are not those initially advertised.

**Finally, the documented porosity between the advertising ecosystem and surveillance.** A report from the `Office of the Director of National Intelligence` dated **January 2022 and declassified in June 2023** acknowledges that US intelligence agencies **regularly buy commercial data from data brokers**, notably location and browsing data. What is collected to sell advertising can therefore be bought back to surveil, without a warrant or notification.

In this context, the question is not "will LLM conversations one day be monetized or resold" but "what is left of that risk if the data leaving your perimeter no longer contains identifying PII?". Upstream anonymization strips these data of their commercial and strategic utility before they even enter the provider's ecosystem.

### Why anonymization breaks this graph

A PII sent in cleartext becomes a node in a potential graph: it can be crossed with social networks, prior breaches, public registries or commercial databases, to re-identify, enrich or target. A `<<PERSON:1>>` placeholder has no aggregation value. Anonymizing before sending cuts the common root of every secondary-use chain described above.

---

## Where to place yourself on the provider spectrum?

The choice is not binary between "US cloud" and "nothing". There is a continuum, from the most exposed to the most isolated, and each step changes both the legal risk and the responsibility that falls on you.

| Option                         | CLOUD Act / FISA 702                  | GDPR                                       | Provider technical access       | Training on your data                                                 | Examples                                        |
|--------------------------------|---------------------------------------|--------------------------------------------|---------------------------------|-----------------------------------------------------------------------|-------------------------------------------------|
| US provider, US servers        | Yes, directly                         | Indirect (via DPF, fragile)                | Yes                             | Variable (free: often buried opt-out; paid: excluded by default)      | OpenAI, Anthropic, Google                       |
| US provider, EU servers        | Yes (cf. Microsoft Ireland)           | Applies, but preempted by the US order     | Yes                             | Excluded by default on enterprise tiers                               | Azure OpenAI EU, AWS Bedrock EU                 |
| EU provider                    | No (unless US-controlled subsidiary)  | Applies fully                              | Yes                             | Excluded by default on paid tiers                                     | Mistral, OVHcloud AI, Scaleway                  |
| Local model (self-hosted)      | No                                    | You are responsible for processing         | **No: you are the provider**    | **No: you control it**                                                | `llama.cpp`, `Ollama`, `vLLM` on private infra  |

At one end of the spectrum, a **US provider hosted in the United States** piles up the three risks above: CLOUD Act, FISA 702 and Executive Order 12333 apply unfiltered, transfers from the EU rely on the contested `Data Privacy Framework`, and a US judge's order can force indefinite retention of conversations. That is the most exposed scenario.

Moving the servers physically to Europe changes almost nothing legally. As soon as the operating entity is under US jurisdiction, the CLOUD Act applies regardless of where the hard drives sit. This option does bring real benefits on other axes (lower latency, operational guarantees, sometimes partial `SecNumCloud` certification via joint-venture), but no watertightness against the United States.

Switching jurisdiction by moving to a **European provider** (Mistral, OVHcloud AI, Scaleway, Aleph Alpha, etc.) drops the CLOUD Act risk by default, unless the provider has a controlled US subsidiary. The GDPR applies fully and European authorities can sanction. This does not make the provider blind to the content: it retains full technical access, protection remains contractual and state-based, and a French or German rogatory commission remains possible. A European provider may also, for practical reasons, host its infrastructure on AWS or Azure, which reintroduces a link to a third jurisdiction. Verify case by case.

!!! note "The `on-premise` case"
    Some European providers, such as Mistral, offer `on-premise` deployment: their customers host the model in their own datacenter. This is an attractive option for benefiting from European expertise while keeping control of the infrastructure, but it remains rare and expensive.

Finally, **running the model locally** on your own infrastructure (`Ollama`, `vLLM`, `llama.cpp` or equivalent) removes the third party entirely: no provider has technical access to the content, by construction. It is the maximum protection on the confidentiality front. The trade-off is that all responsibility shifts onto you: physical and logical security, encryption at rest, access management, updates, logging. Open models that can be run locally (Llama, Mistral, Qwen, DeepSeek, etc.) may still lag behind the best proprietary models on some complex tasks, though the gap is closing quickly.

The choice of provider still matters for many things: latency, cost, model quality, overall GDPR compliance, integration ecosystem. But **for the specific risk of PII leakage, anonymization neutralizes that choice**. If only placeholders like `<<PERSON:1>>` leave your infrastructure, a US provider receives nothing exploitable about your sensitive data. From that specific angle, it becomes equivalent to a locally executed model.

---

## Sectoral obligations and choices already made

### When it is a legal obligation

In several professions, sending personal data to a non-sovereign LLM is not a matter of convenience; it is a regulatory impossibility.

- **Finance**: MiFID II, banking secrecy, client-confidentiality obligations.
- **Lawyers**: absolute professional secrecy (article 66-5 of the French law of 31 December 1971). A client consultation sent raw and identifiable to a US LLM can amount to a deontological fault; recent `CNB` guidelines require at minimum anonymization, client consent, and an appropriate provider.
- **Medicine**: medical secrecy (article L.1110-4 of the French Public Health Code), HIPAA in the United States. A patient record cannot transit through a third-party service without heavy technical guarantees (`HDS`-certified hosting, `DPO`, etc.).
- **Defense and strategic sectors**: specific regimes (classification, `CUI` (*Controlled Unclassified Information*) in the US, `Diffusion Restreinte` in France). The potential intersection of US government legal access and strategic interests (energy, defense, technology) makes this risk non-theoretical.

In these sectors, anonymization before sending is not a best practice; it is a compliance prerequisite.

### What large companies have already decided

In the absence of available technical protection in 2023, several large groups simply banned their employees from using cloud LLMs.

- **Samsung, April 2023**: several internal incidents where engineers pasted source code and meeting notes into ChatGPT. Samsung publicly noted that data shared this way was impossible to retrieve, since it was now on OpenAI servers. In May 2023, the company banned the use of generative LLMs on professional devices.
- **US banking sector, spring 2023**: JPMorgan Chase, Bank of America, Citigroup, Goldman Sachs, Deutsche Bank and Wells Fargo blocked or restricted ChatGPT use for their employees. Verizon, Amazon and Walmart issued internal warnings.

These decisions come from legal departments and CISOs who made the calculation: **structural risk outweighs the productivity gain**, as long as no technical barrier guarantees that PII does not leave the company. Anonymization opens precisely that third path, between outright bans and cleartext sending.

---

## Legal protection vs technical protection

All the protections mobilized so far rest on **legal** instruments: privacy policies, standard contractual clauses, international agreements, administrative fines. They share a common flaw: they are **revocable**, by a political or judicial decision over which you have no leverage.

| Type of protection             | Example                                       | Why it is fragile                                          |
|--------------------------------|-----------------------------------------------|------------------------------------------------------------|
| Contractual promise            | "We do not read your data"                    | Overridable by an order (NYT vs OpenAI)                    |
| Standard contractual clauses   | EU-to-US transfers                            | Already weakened by `Schrems II`                           |
| International agreement        | `Privacy Shield`, `Data Privacy Framework`    | The first was invalidated, the second is contested         |
| Regional regulation            | GDPR                                          | Slow to produce sanctions actually applied to LLMs         |
| Regional hosting               | "Datacenters in Europe"                       | Neutralized by the CLOUD Act if the provider is American   |

Technical protection works differently. If the personal data never leaves your infrastructure, and only a placeholder (for example `<<PERSON:1>>`) is sent to the LLM:

- no order can compel a third party to disclose what it does not hold,
- no change to an international agreement affects you,
- no provider retention policy is in play,
- the provider can be hacked, acquired, or disappear: your data was not there.

It is the difference between **"we promise not to look"** and **"we are technically unable to look"**. The second is always more robust than the first.

---

## What anonymization does not solve

Anonymization is a layer in a defense-in-depth posture, not a silver bullet.

- It does not make an LLM compliant with every regulatory regime. Some data (identifiably linkable health data, defense-classified material) must not leave the infrastructure, even in anonymized form.
- It depends on detector quality. A PII that is not detected passes through in cleartext. This is an engineering concern, not a conceptual flaw.
- It does not replace other good practices: encryption at rest, audited logging, access management, team training.

---

## Further reading

Cited sources and useful reading:

- **CJEU, `Schrems II` ruling** (C-311/18, 16 July 2020): [curia.europa.eu](https://curia.europa.eu/)
- **CLOUD Act** (H.R. 4943, 2018): official text on [congress.gov](https://www.congress.gov/)
- **PCLOB reports on FISA 702** (Privacy and Civil Liberties Oversight Board): [pclob.gov](https://www.pclob.gov/)
- **Italian Garante, decision against OpenAI** (December 2024, annulled by the Rome tribunal in March 2026): [garanteprivacy.it](https://www.garanteprivacy.it/)
- **NYT vs OpenAI, preservation order and 20-million-log delivery** (US District Court SDNY, May 2025 to January 2026 with District Judge Stein's affirmation)
- **OpenAI, Redis incident post-mortem** (20 March 2023): [openai.com/blog](https://openai.com/)
- **Wiz Research, DeepSeek exposure** (January 2025): [wiz.io](https://www.wiz.io/)
- **Samsung, internal LLM policy** (May 2023, `Bloomberg` coverage)
- **NSA surveillance of Angela Merkel's phone** (Snowden revelations, October 2013, coverage in `Der Spiegel`, `Süddeutsche Zeitung`, `NDR`)
- **DOJ seizure of AP records** (seizure April-May 2012, disclosed May 2013, Associated Press public statement)
- **Pegasus Project / Forbidden Stories** (July 2021): [forbiddenstories.org](https://forbiddenstories.org/)
- **ODNI, `Report on Commercially Available Information`** (January 2022, declassified June 2023): [dni.gov](https://www.dni.gov/)
- **SecNumCloud** (ANSSI): [cyber.gouv.fr](https://cyber.gouv.fr/)

For a critical and balanced perspective, see also publications from the French `CNIL` on generative AI, the `EDPB` on international transfers, and `ENISA` on digital sovereignty.
