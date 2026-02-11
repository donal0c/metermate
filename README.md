# Steve - Energy Audit Data Platform

**Status**: Research & Discovery Phase
**Last Updated**: February 2026
**Client**: Energy Consultancy (Steve)

## The Problem

Energy consultants preparing audit reports face a frustrating workflow:

1. Ask client for electricity bills
2. Receive half the bills with missing data
3. Re-request bills
4. Receive a jumbled mess of documents
5. Manually extract kWh/cost data into Excel
6. Create usage infographics for audit reports

Meanwhile, ESB Networks holds **30-minute interval data** on all smart meter customers — data that could reveal far more than monthly bill summaries ever could.

## The Opportunity

Build a tool that:
- Ingests smart meter data (HDF files from ESB Networks)
- Automatically generates professional visualisations
- Identifies consumption anomalies (e.g., high night-time usage)
- Produces audit-ready infographics and reports

## Key Findings

| Question | Answer |
|----------|--------|
| Is 15-min data available? | Only for commercial QH meters. Residential = 30-min |
| Data format? | CSV (Harmonised Downloadable Files) |
| How much history? | Up to 2 years |
| Is there an API? | No public API. Manual download only |
| Can third parties access? | Not yet. CRU Data Access Code in implementation |
| Existing tools? | Consumer-focused (EnergyPal, Kilowatt). Nothing for auditors |

## Verdict

**Yes, there's a viable product here.**

The gap is real:
- Consumers have EnergyPal/Kilowatt for tariff switching
- Enterprises have ESB's Energy Management Hub
- **Energy consultants have nothing purpose-built**

See [docs/](./docs/) for detailed research.

## Documentation

- [Research Summary](./docs/01-research-summary.md) - Full findings from discovery
- [ESB Data Access](./docs/02-esb-data-access.md) - Technical details on HDF files
- [Regulatory Framework](./docs/03-regulatory-framework.md) - CRU Smart Meter Data Access Code
- [Existing Tools](./docs/04-existing-tools.md) - Competitive landscape
- [Product Vision](./docs/05-product-vision.md) - What to build and how

## Quick Links

- [ESB Networks Smart Data Portal](https://www.esbnetworks.ie/services/manage-my-meter/view-my-smart-meter-usage)
- [CRU Smart Meter Data Access Code (PDF)](https://cruie-live-96ca64acab2247eca8a850a7e54b-5b34f62.divio-media.com/documents/CRU202516_-_Decision_on_the_Smart_Meter_Data_Access_Code.pdf)
- [HDF Parser (Python)](https://github.com/dresdner353/energyutils/blob/main/ESB_HDF_READER.md)
- [SEAI Energy Audit Handbook](https://www.seai.ie/sites/default/files/publications/SEAI-Energy-Audit-Handbook.pdf)

## Sample Data

The `download.pdf` in this folder is an example Electric Ireland bill showing:
- Day/Night/Peak tariff structure
- Export credits (solar)
- MPRN reference
