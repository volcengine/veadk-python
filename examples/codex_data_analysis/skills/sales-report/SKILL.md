---
name: sales-report
description: The house format for a quarterly sales review. Use whenever you are asked to produce a sales, revenue or bookings report.
---

A sales review is one Markdown file with exactly these sections, in this order.

```markdown
# <Quarter> Sales Review

## Headline

- **Total revenue**: CNY <total, thousands-separated, 2 decimals>
- **Total units**: <integer>
- **Top region**: <region> (CNY <revenue>)

## By region

| Region | Revenue (CNY) | Units | Share |
| --- | ---: | ---: | ---: |
| ... | ... | ... | ... |

Sorted by revenue, highest first. Share is a percentage of total revenue with
one decimal. The last row is a **Total** row.

## Trend

![Revenue by month](chart.svg)

One sentence naming the strongest and weakest month. Unless the request says
otherwise, the chart is revenue by month.

## Data notes

- One bullet per data-quality problem you had to correct, naming the affected
  column, how many rows it hit, and what you did about it.
- `- none` if there were none.
```

## Chart rules

No plotting library is available, so write the SVG by hand:

- at most 640×320, with `viewBox`, and no external fonts, images or CSS;
- one axis line, every bar or point labelled with its value;
- a single accent colour plus a grey axis — no gradients;
- round numbers on the axis, not raw maxima.

## Rules

- Every figure in the report comes from the extract. Never carry a number over
  from a previous draft — recompute it.
- Money is CNY, two decimals, thousands-separated. Units are integers.
- Keep the whole report under 60 lines.
