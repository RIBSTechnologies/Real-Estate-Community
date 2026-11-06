# Property Management Dashboard

A modern, colourful analytics dashboard for the `rental_management` property
suite — built with **OWL + Chart.js for Odoo 18**. It mirrors the look and
theme system of the Advanced Accounting Dashboard, applied to property data.

## What it shows

**KPI cards** (all clickable → open the underlying list):
Total Properties · Available · On Rent · Sold · Buildings · Active Tenancies ·
Tenants · Occupancy % · Rent Invoiced · Outstanding.

**Charts** (segments clickable → drill down):
- Properties by Status (draft / available / booking / on-rent / sale / sold)
- Properties by Type (land / residential / commercial / industrial)
- Rent Invoiced — monthly trend
- Properties by Sub-Type (villa / apartment / …)
- Contracts by Status
- Top Buildings by Units

**Tables:** Recent tenancy contracts · Top outstanding invoices.

**Filters:** Property type · Sale/Rent · Region · Building · Sub-Type · Year · Month.

**Themes:** Purple, Ocean, Light, Dark, Comet (remembered per browser).

## Install

1. Copy `property_dashboard/` into your Odoo 18 addons path (next to
   `rental_management`).
2. *Apps → Update Apps List*.
3. Install **Property Management Dashboard**.
4. Open the new top-level **Property Dashboard** menu.

Depends on: `web`, `rental_management`.

## How it's wired

- `models/dashboard.py` — an `AbstractModel` (`property.dashboard`) exposing
  `get_filter_data()` and `get_dashboard_data(...)`. It reads
  `property.details`, `property.project`, `tenancy.details`, `property.vendor`,
  `rent.invoice` and `res.partner`. Every query is defensive: a missing model
  or field degrades that block to zero/empty instead of breaking the page.
- `static/src/js/property_dashboard.js` — the OWL client-action component
  (themes, Chart.js rendering, filters, click-through via the action service).
- `static/src/xml/property_dashboard.xml` — the OWL template (reuses the
  `.ad-*` classes so styling matches the accounting dashboard).
- `static/src/css/dashboard.css` — the reference stylesheet (5 themes) plus a
  small supplemental block at the end for this dashboard's helpers.

## Customising

- **Currency:** taken automatically from the active company's currency symbol.
- **"Rent Invoiced"/"Outstanding"** are derived from `rent.invoice` records
  linked to posted `account.move` invoices. If your invoicing flow differs,
  adjust `_rent_invoice_moves()` / `_get_invoice_stats()` in `dashboard.py`.
- **Occupancy** = (on-rent + sold) / total. Change the formula in
  `get_dashboard_data()` if you define occupancy differently.
- To add a KPI or chart: add the value in the model's return dict, a card/canvas
  in the template, and (for charts) one line in `renderCharts()`.

## Note on the source dashboard

The sample `accounting_dashboard` targets **Odoo 15** (legacy
`odoo.define` / `AbstractAction` / `web.assets_qweb`), which Odoo 17+ removed.
This module keeps the identical visual design but is implemented with the
current OWL framework so it loads on your Odoo 18 database.
