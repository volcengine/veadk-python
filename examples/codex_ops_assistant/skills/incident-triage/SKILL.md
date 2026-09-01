---
name: incident-triage
description: The on-call triage procedure for checkout-api. Use whenever you are asked to investigate elevated errors, elevated latency, or a suspected regression.
---

Follow this procedure. It exists because the obvious answer is usually wrong.

## 1. Pull everything first

Fetch logs, metrics **and** deploy history for the whole window before you
analyze any of them. A conclusion drawn from one source is a guess.

## 2. Characterize signatures, do not rank them

Never conclude from "which error is most frequent". High-volume errors are
usually chronic noise that was there yesterday too.

For every distinct error signature, compute its count **per hour** across the
window. You are looking for a signature whose *rate changed* — ideally one that
was zero and then was not. A signature that is flat across the whole window is
background, however loud it is.

## 3. Locate the change point

For each signature that changed, find the timestamp of its first occurrence
after the change. That timestamp, not the start of the window, is the moment
you are explaining.

## 4. Correlate with deploys

Normalize every timestamp to UTC epoch seconds before comparing sources; they
do not all use the same format or the same clock. A deploy is a candidate only
if it precedes the change point by minutes, not hours. Where two deploys are
close together, the one that lines up is the one that lines up — check both.

## 5. Confirm in the metrics

The metric series is long format: one row per metric per minute. Aggregate it
per metric before drawing conclusions.

- A cause produces a **sustained** change beginning at the change point. A
  spike that recovers on its own is not your incident.
- Check request volume too. If traffic did not change, the incident is not
  load-driven and you should stop looking for one.
- A resource metric sitting exactly at its configured limit is worth more than
  any latency graph.

## 6. Explain the mechanism

Tie the candidate deploy's change list to what the metrics show. If you cannot
explain *how* that change produces *these* numbers, you have a correlation, not
a root cause — and you should say that in the ticket.

## 7. File one ticket

Exactly one, at the end. Every claim in `evidence` must be a number you
actually computed, with its timestamp. Rule out the hypotheses you rejected,
and say why.

## Working notes

Keep your analysis scripts in the workspace under `analysis/` with names that
say what they do. You will be asked to re-run them over a different window.

Take the input file path as a command-line argument (`sys.argv[1]`). Never
hardcode it — a script with a filename baked in is not reusable, and renaming
data files to fit an old script wastes far more time than adding one argument.
