# LibraryIQ

A librarian-assisting agent: staff ask for an article in Teams, it tells them whether the library already has access and gives them the link, and only if not, sends a request that the librarian approves.

## The problem

Clinicians and researchers constantly need specific articles. Today a request goes to the librarian, who checks whether the library already subscribes, finds the link, or orders a copy. Most requests are the same few steps, repeated by hand, while the librarian's time is better spent on judgement calls.

LibraryIQ takes the routine part. Staff ask in a chat; the agent answers instantly when the library already has access, and only when it doesn't, passes a ready-made request to the librarian, who stays in charge of every order.

## What it covers

| Part | What it does | Stage |
|---|---|---|
| Article finding | From a DOI, a PubMed ID or a typed citation: identify the article, check access, return the link or raise a request | First |
| Literature search | Find and summarise relevant papers, with citations | Next |
| Subscription use and renewals | Answer questions such as which subscriptions renew soon and are barely used | Next |

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
  R -->|"An article"| A1["Article finding flow above"]
  R -->|"A topic"| L1["Search PubMed and summarise the best matches, with citations"]
  R -->|"Subscriptions"| S1["Run a fixed, read-only query on subscription and usage data"]
  L1 --> L2["Offer to find or request any article from the results"]
  S1 --> S2["Answer with a table and its data source"]
```

## Architecture

```mermaid
flowchart TB
  U["Staff<br/>Microsoft Teams"] --> AG["Agent<br/>Agent Framework, Python<br/>hosted in Microsoft Foundry"]
  AG --> MODEL["Language model<br/>Foundry"]
  AG --> PUB["Public lookups<br/>Crossref, PubMed, Unpaywall"]
  AG --> LR["Library link resolver<br/>access check"]
  AG --> DB[("Database<br/>requests, decisions, audit")]
  AG --> MAIL["Email notification<br/>alerts and outcomes"]
  AG --> SUB[("Subscription and usage data<br/>next stage")]
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
  MW --> T1["find_article<br/>identify, then check access"]
  MW --> T2["request_article<br/>create a pending request"]
  MW --> T3["search_literature<br/>PubMed search with citations<br/>next stage"]
  MW --> T4["subscription_insights<br/>fixed, read-only queries<br/>next stage"]
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

## Status

Early build. A private, end-to-end environment is defined in [infra/private/](infra/private/) and development happens on a jump VM inside it; the agent code is next. A Get Started guide will follow once there is something to run.

## Principles

- A human approves anything consequential, such as an external order.
- No patient data, and no clinical advice.
- Every answer shows where it came from.
- Every step is logged.
- Plain code for rules; the language model only where it adds value.
