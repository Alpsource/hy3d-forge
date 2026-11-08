# Licensing and what costs money

Two pieces, licensed differently.

**The backend** - this repository, the thing that actually generates meshes - is under the
[PolyForm Small Business License 1.0.0](LICENSE). If your company has **fewer than 100
people** and made **less than $1,000,000** in its last tax year, you already have a licence
for anything you want to build, including games you sell. Nothing to buy, nobody to email.

**The Unity Editor client** is sold on the Unity Asset Store for **$4.99**. It is the only
part with a price tag for most people, and it is optional: the HTTP API is documented and
anyone can write their own client, or drive it with `curl`.

## Why the paid part is the small part

An honour-system licence on a self-hosted backend collects almost nothing. Nobody fills in a
revenue declaration for software they already have working, and chasing them would cost more
than it raised. Putting the price on the editor client instead means Unity handles payment,
VAT and refunds, and the amount is small enough that nobody has to think about it.

So the backend is free to the people most likely to try it, and the client is cheap enough to
buy on impulse. Neither decision is generosity; it is the only arrangement where money
actually arrives.

## The Unity client

Asset Store listing: *(pending review)*

$4.99, under Unity's standard Asset Store EULA. Available to any company of any size - the
PolyForm thresholds do not apply to it, because it is not distributed under PolyForm.

It needs this backend running on a machine you control, with an NVIDIA GPU. 8 GB of VRAM for
the smaller model, 24 GB for the PBR one. Nothing is uploaded anywhere and there is no
per-asset fee.

## Backend commercial licence

Over 100 people or over $1M revenue, you need one. **This is separate from the Asset Store
purchase** - buying the $4.99 client does not license the backend, and a large studio needs
both. Worth saying plainly because the split is easy to miss.

| | Free | Studio | Perpetual |
|---|---|---|---|
| Who | under 100 people **and** under $1M revenue | everyone else | everyone else |
| Price | — | $1,200 / year | $3,000 once |
| Seats | unlimited | unlimited, one company | unlimited, one company |
| Updates | all | all, while subscribed | the version you bought, plus 12 months |
| Support | public issue tracker | email, 2 business days | email, 12 months |

Per *company*, not per seat or per machine - the thing being licensed is the right to use it
commercially, and metering seats on self-hosted software is a tax on honest customers.

There is no licence key, no activation and no phone-home. The software behaves identically
either way.

### Buying one

Email **binarybrainofficial@gmail.com** with your company name and rough headcount. You get
an invoice and a countersigned licence document naming your company.

Payment in USD or EUR by bank transfer; Turkish companies can be invoiced in TRY.

## What you are licensing, and what you are not

Either licence covers **this repository**: the router, the workers and the CLI.

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

No licence sold here changes either of those, because they are not mine to change. What is
being sold is the orchestration layer around them, which is the part this repository wrote.

## Questions people ask first

**Can I ship games made with it?** Yes, under either licence. The output is yours; the
licence is about running the software, not about what it generates. Check the backend's terms
for its own view on output - Tencent's is in the README.

**Do I have to buy the Unity client?** No. It is a convenience. The API is documented above
and the service speaks ordinary HTTP.

**Can I host it for my own team?** Yes. Internal use across a company is use by that company.

**Can I host it as a paid service for other people?** Under the free tier, only while you are
under the thresholds. Past them, a commercial licence covers it - but read the backend's
territory restriction first, because that will bite before this licence does.

**Can I modify it?** Yes, both tiers, including forks and private patches. PolyForm grants
changes and new works. You may redistribute it, but you must pass on the same licence and the
`Required Notice:` line.

**We are over the threshold but only evaluating.** Evaluate freely and talk to me when you
decide. Nobody has ever been sued into becoming a customer.

---

Copyright 2026 Alp Demirel (Binary Brain), Ankara. <https://binarybrain.tech>
