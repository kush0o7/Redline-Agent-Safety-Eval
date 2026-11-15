# Security policy

Redline is a safety-testing tool, so we take vulnerabilities in it seriously.

## Reporting a vulnerability

**Please don't open a public issue for a security problem.**

Report it privately through GitHub: go to the repository's **Security** tab → **Report a vulnerability**. Only the maintainers can see the report.

Please include:
- what the problem is and what an attacker could do with it,
- steps to reproduce (a request, a config, or a failing test is ideal),
- the commit or version you tested.

What to expect:
- an acknowledgement within **3 working days**,
- a first assessment within **7 days**,
- a fix or a mitigation plan as soon as we can, and credit in the release notes if you'd like it.

## Supported versions

Redline is pre-1.0. Security fixes go to the `main` branch only.

## In scope

- Bypassing auth: the admin key, invite tokens, per-run stream tokens.
- The SSRF guard for agent endpoints (including DNS rebinding and metadata addresses).
- Leaking stored agent keys, or full (unredacted) model outputs without `X-Admin-Key`.
- Injection into the HTML reports (they should escape all model output and load nothing external).
- Anything that lets a test case or a model's answer run code or reach the network from the harness. Injection tools are stubs and must stay that way.

## Out of scope

- A model under test producing harmful text. That's what Redline measures, not a bug in Redline.
- The public demo instance (`REDLINE_ENV=demo`) being open: that's intended. Report anything that escapes the demo's limits.
- Rate-limit or denial-of-service findings that need a large volume of traffic.
- Missing hardening headers with no concrete attack.

## Safe testing

Test against your own install. Don't send real customer data, personal data or real secrets to the public demo.
