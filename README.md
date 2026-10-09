# LibraryIQ

A librarian-assisting agent: staff ask for an article in Teams, it tells them whether the library already has access and gives them the link, and only if not, sends a request that the librarian approves.

## The problem

Clinicians and researchers constantly need specific articles. Today a request goes to the librarian, who checks whether the library already subscribes, finds the link, or orders a copy. Most requests are the same few steps, repeated by hand, while the librarian's time is better spent on judgement calls.

LibraryIQ takes the routine part. Staff ask in a chat; the agent answers instantly when the library already has access, and only when it doesn't, passes a ready-made request to the librarian, who stays in charge of every order.

## What it covers

| Part | What it does | Stage |
|---|---|---|
| 1. Article finding | From a DOI, a PubMed ID or a typed citation: identify the article, check access, return the link or raise a request | First |
| 2. Literature search | Find and summarise relevant papers, with citations | Next |
| 3. Subscription use and renewals | Answer questions such as which subscriptions renew soon and are barely used | Next |

## User flow

```mermaid
flowchart TD
  A["Staff member asks for an article<br/>DOI, PubMed ID or typed citation"] --> B["Agent identifies the article"]
  B --> C{"Does the library<br/>have access?"}
  C -->|Yes| D["Reply with the link and its source"]
  C -->|No| E{"Free legal<br/>copy found?"}
  E -->|Yes| D
  E -->|No| F["Request saved, librarian emailed a link"]
  F --> G{"Librarian approves<br/>on the approval page?"}
  G -->|Yes| H["Order sent, requester emailed"]
  G -->|No| I["Requester emailed with the reason"]
```

The requester can also ask the agent for the status of a request at any time.

The other two parts (next) start from the same chat:

```mermaid
flowchart TD
  Q["Question in chat"] --> R{"What is it about?"}
  R -->|"An article"| A1["Part 1: article finding flow above"]
  R -->|"A topic"| L1["Part 2: search PubMed and Europe PMC, summarise the best matches, with citations"]
  R -->|"Subscriptions"| S1["Part 3: run a fixed, read-only query on subscription and usage data"]
  L1 --> L2["Offer to find or request any article from the results"]
  S1 --> S2["Answer with a table and its data source"]
```

## Architecture

```mermaid
flowchart TB
  U["Staff<br/>Microsoft Teams"] --> AG["Agent<br/>Agent Framework, Python<br/>hosted in Microsoft Foundry"]
  AG --> MODEL["Language model<br/>Foundry"]
  AG --> PUB["Public lookups<br/>Crossref, PubMed, Unpaywall<br/>Part 1"]
  AG --> LR["EBSCO Full Text Finder<br/>LinkIQ API: access check<br/>Part 1"]
  AG --> LIT["Literature sources<br/>PubMed, Europe PMC<br/>Part 2, next"]
  AG --> DB[("Azure SQL<br/>requests, decisions, audit")]
  AG --> MAIL["Email notifier<br/>alerts and outcomes"]
  AG --> SUB[("Subscription and usage data<br/>COUNTER reports, renewal dates<br/>Part 3, next")]
  AG -.-> OBS["Application Insights<br/>traces and logs"]
  LIBN["Librarian"] --> LIB["Librarian approval page<br/>web app, Entra sign-in"]
  LIB --> DB
  LIB --> MAIL
```

Inside the agent, the language model only reads the request and chooses a tool. The rules live in plain code.

```mermaid
flowchart TB
  H["Agent host"] --> AG["Agent<br/>instructions and model client"]
  AG --> MW["Audit middleware<br/>logs every tool call"]
  MW --> T1["find_article - Part 1<br/>identify, then check access"]
  MW --> T2["request_article - Part 1<br/>create a pending request"]
  MW --> T3["search_literature - Part 2<br/>search with citations<br/>next stage"]
  MW --> T4["subscription_insights - Part 3<br/>fixed, read-only queries<br/>next stage"]
  T1 --> CORE["Plain Python core<br/>parsing, lookups, access check, search"]
  T3 --> CORE
  T2 --> STORE["Request store and approval rules"]
  STORE --> NOTIFY["Notifier<br/>email the librarian"]
  T4 --> QUERIES["Fixed queries on subscription data"]
```

## Built with

| Layer | Choice |
|---|---|
| Language | Python |
| Agent framework | [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/) |
| Runtime and model | Microsoft Foundry (hosted agent, model deployment) |
| Data | Azure SQL; SQLite for local development |
| Observability | OpenTelemetry to Application Insights |
| Infrastructure | Bicep ([infra/](infra/)) |

## Demo vs real

The demo runs against free public services and synthetic data. Systems that need a customer's own licence or credentials are replaced by a stand-in behind the same interface, so the real client drops in without changing the tools or the agent.

| Part | System | Real agent | Demo agent | Demo vs real | Findings |
|---|---|---|---|---|---|
| **1. Article finding** | Crossref, PubMed, Unpaywall | Live calls | Live calls | **Same** | Free public APIs, so the demo behaves exactly like the real agent. |
| **1. Article finding** | EBSCO Full Text Finder (LinkIQ API) | Real subscription check | Mock with the same response shape and synthetic journals | **Similar contract, fake data** | Documented REST API: `GET /{profile}/openurl`, with `id=doi:…` or `pmid:…`. The response has `targetLinks` with categories such as `FullText` and `ILL`. A customer profile (`customerid.groupid.profileid`) is required and no public profile exists. EBSCO has a developer registration and credentials request process; sandbox access was not confirmed. A second route, the Entitlement API, also needs a registered client app. No MCP server was found for either. **Real results are not possible without the customer or EBSCO.** |
| **2. Literature search** | PubMed | Scheduled ingest into Azure AI Search | Live search against PubMed and Europe PMC | **Similar** (live versus indexed) | Both are free public APIs. The demo skips the ingest and index step. |
| **2. Literature search** | CINAHL | Ingest, if the licence allows | Not in the demo | **Not possible** | EBSCO licensed database with no free access. The demo substitutes PubMed and Europe PMC. |
| **3. Subscription use and renewals** | Renewal spreadsheets and usage reports | The customer's own files | Synthetic COUNTER-shaped data | **Similar format, fake data** | COUNTER is the standard usage format, and a public COUNTER R5.1 API test server exists (not yet tried). The customer's real contract and cost data is **not possible**. |
| **3. Subscription use and renewals** | Publisher APIs (EBSCO, Elsevier, Wolters Kluwer, Springer) | Publisher credentials from the customer, later | A usage-report client built against the public test server | **Same code, no real publisher data** | Providers must support the COUNTER API standard, so one harvester fits all, but each publisher still needs the customer's credentials. **Real publisher data is not possible.** |

## Status

Part 1 (article finding) works end to end on a local model, with a stand-in for the library access check. A private, end-to-end Azure environment is defined in [infra/private/](infra/private/); deploying the agent there is next.

## Run locally

Needs Python 3.13, [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com) with a tool-calling model.

```bash
ollama pull qwen2.5:7b
cp .env.example .env          # set LIBRARYIQ_CONTACT_EMAIL; it is sent to Crossref, PubMed and Unpaywall
uv sync
uv run python -m libraryiq.cli    # chat in the terminal
uv run python -m libraryiq.main   # host it on http://localhost:8088 (Responses API)
uv run pytest
```

```bash
curl -s localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Find 10.1056/NEJMoa2034577 for me"}'
```

The access check, email and request store are stand-ins (a sample journal list, a simulated notifier, SQLite). Crossref, PubMed and Unpaywall are called live.

## Principles

- A human approves anything consequential, such as an external order.
- No patient data, and no clinical advice.
- Every answer shows where it came from.
- Every step is logged.
- Plain code for rules; the language model only where it adds value.
