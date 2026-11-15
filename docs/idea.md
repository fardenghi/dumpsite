# The idea: what the radar never sees asleep

**Challenge:** Dancing with the SARs (NISAR), NASA Space Apps 2026.

## The problem
Argentina has an estimated 5,000 open-air dump sites. The figure comes from the Ministry of Environment and isn't based on a formal survey. In Buenos Aires Province, 81 of 135 municipalities were using dump sites according to the 2023 report. Closures get announced, but there's no open, georeferenced inventory to check whether a "closed" dump site is still receiving waste.

## What it does
NISAR passes over the same place every 12 days. Comparing two passes, it measures how similar they look (the **coherence**). A field loses coherence with the seasons (harvest, rain) and a city almost never does. An active dump site, on the other hand, loses it in every pair, because it gets moved around every day.

Dumpsite looks for the places that are **never seen asleep**:

1. It computes a per-pixel **insomnia index**: the fraction of pairs in which the coherence falls well below that of its surroundings (`indice-insomnio.md`).
2. It builds **candidate blobs** and discards water, roads and smooth surfaces.
3. It **crosses** the blobs with a catalog of 66,981 dump sites around the world and with 64,986 negatives (what the radar confuses with a dump site: airfields, quarries, container yards).
4. It gives a **verdict per site** against the official registry: "active, already known", "closed but awake", "closed and quiet" or "the radar can't tell".
5. With an **open-versus-closed model** trained on the EPA registry, it ranks the sites by how compatible they are with an open dump site (`modelo.md`).

It all shows up on a website with the index map, a card per site and the model panel.

## The Luján case
The Luján dump site stopped receiving waste on **1 July 2026**, after about 52 years. NISAR has about 3.5 months of pairs after the closure.

- **Luján gets an insomnia of 0.00 in all 15 pairs** (two orbits, from 25 June to 12 October 2026). In no pair did the site's coherence drop relative to its ring. The verdict is "closed and quiet".
- **Norte III (CEAMSE)**, the landfill that takes most of the AMBA's waste, gets 0.86, and González Catán gets 1.00. The city (Palermo) gets 0.00.
- The open-versus-closed model, trained only with US data, gives Luján 0.16 and the Norte III complex 0.99.

Limit: the first pair of each orbit spans 1 July, so there's no NISAR "before" the closure.

## Who it's for
Provincial and municipal environmental authorities, journalists and NGOs that audit closures. The output is a list that can be checked site by site, with the source of every number.

## What it doesn't say
- **It doesn't accuse anyone.** It talks about a "signal compatible with activity" and "quiet according to the radar".
- **It doesn't separate everything.** The grass of an airfield, a wetland or a container yard also lose coherence. That's why it's crossed with the negatives.
- **It doesn't see small sites.** Below 10 ha, about 16 pixels of 80 m, the verdict is "the radar can't tell".
- **The series is short.** Public NISAR data starts in mid-2026: the AMBA has four months of pairs and the US up to a year.

## Why it isn't obvious
The usual approach in this challenge is comparing before and after an event: a flood, deforestation or subsidence. This idea doesn't look for a change, it looks for the time signature of what changes **all the time**. It uses the lost coherence that others throw away and crosses it with an official registry.
