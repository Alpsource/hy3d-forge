# Commercial licensing

hy3dforge is released under the [PolyForm Small Business License 1.0.0](LICENSE). Most
people who will ever run it never need to read further than this paragraph: if your company
has **fewer than 100 people** and made **less than $1,000,000** in its last tax year, you
already have a licence, for anything you want to build, including games you sell. Nothing to
buy, nobody to email.

Above either threshold, you need a commercial licence. That is the whole business model.

## Why this split

Hobbyists and small studios are the people who try a new tool, file the issues and tell
other developers about it. Charging them $0 is not charity, it is how the project gets good
enough to be worth money to anyone else. Studios past the threshold have a procurement
process and a budget line for tooling, and they would rather pay for something supported than
explain an unlicensed dependency to their legal team.

The thresholds are PolyForm's, not invented here, and that is deliberate. A custom licence
with a custom revenue number means every buyer's lawyers read it from scratch. A published,
professionally drafted one that other companies already use gets waved through.

## What a commercial licence costs

| | Free | Studio | Perpetual |
|---|---|---|---|
| Who | under 100 people **and** under $1M revenue | everyone else | everyone else |
| Price | — | $1,200 / year | $3,000 once |
| Seats | unlimited | unlimited, one company | unlimited, one company |
| Updates | all | all, while subscribed | the version you bought, plus 12 months |
| Support | public issue tracker | email, 2 business days | email, 12 months |

Per *company*, not per seat or per machine — the thing being licensed is the right to use it
commercially, and metering seats on self-hosted software is a tax on honest customers.

There is no licence key, no activation and no phone-home. The software behaves identically
either way. This is an honour system backed by a written threshold, which is what every
source-available licence in this category relies on.

## Buying one

Email **demirel@ee.hacettepe.edu.tr** with your company name and rough headcount. You get an
invoice and a countersigned licence document naming your company.

Payment in USD or EUR by bank transfer; Turkish companies can be invoiced in TRY.

## What you are licensing, and what you are not

A commercial licence covers **this repository**: the router, the workers, the CLI and the
Unity package.

It does **not** cover the model backends. They are separate projects with their own terms,
cloned from their own upstreams by `hy3dforge setup`, which shows you each licence and makes
you accept it before it downloads anything. Whoever runs the backend is that licence's
licensee, directly. Two consequences matter commercially, and you should read
[the README section on this](README.md#the-backends-licences-are-not-this-projects-to-grant)
before building a business on it:

- Tencent's Community License, which both Hunyuan3D backends use, **does not extend to the
  EU, the UK or South Korea**, and the exclusion covers generated output, not just the
  weights.
- Above 1 million monthly active users, Tencent requires a separate licence.

Buying a commercial licence to hy3dforge does not change either of those, because they are
not mine to change. What it buys is the orchestration layer around them, which is the part
this repository actually wrote.

## Questions people ask first

**Can I ship games made with it?** Yes, under either licence. The output is yours; the
licence is about running the software, not about what it generates. Check the backend's terms
for its own view on output - Tencent's is in the README.

**Can I host it for my own team?** Yes. Internal use across a company is use by that company.

**Can I host it as a paid service for other people?** Under the free tier, only while you are
under the thresholds. Past them, a commercial licence covers it - but read the backend's
territory restriction first, because that will bite before this licence does.

**Can I modify it?** Yes, both tiers, including forks and private patches. PolyForm grants
changes and new works. You may redistribute it, but you must pass on the same licence and the
`Required Notice:` line.

**We are over the threshold but only evaluating.** Evaluate freely and talk to me when you
decide. Nobody has ever been sued into becoming a customer.
