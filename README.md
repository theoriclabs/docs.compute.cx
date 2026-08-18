# docs.compute.cx

Customer manual for [Compute](https://compute.cx). Hosted by [Mintlify](https://mintlify.com) at `https://docs.compute.cx`.

This repository is **docs only**. It is not the product monorepo.

## Preview

```bash
npx mintlify dev
```

## What belongs here

Honest CLI / SDK pages that match live behavior: install via `curl|sh`, `compute setup`, prepaid credits, `run` / logs / cancel, H100-SXM + MI300X, billing rules without inventing a fee percentage.

Do not add internal design docs, OpenAPI playgrounds, or unshipped surfaces (PyPI, persistent disks, extra SKUs).

## Connect Mintlify

1. Create a Mintlify project and install the GitHub App on **this** repo only (`theoriclabs/docs.compute.cx`).
2. `mint add-domain docs.compute.cx` and add the printed CNAME with the `namecheap` CLI (see `docs/infra/dns.md` in the product repo).
3. Product marketing already links to `https://docs.compute.cx`.
