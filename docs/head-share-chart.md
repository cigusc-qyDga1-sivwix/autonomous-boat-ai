# Saved six-boat head-share pie

The race-detail page shows the displayed snapshot's `head_course_shares`
immediately above the primary ticket block. It does not rerun a model, infer
shares from selected tickets, use results, or change any forecast or budget.

The heading is **1着奪取の相対評価**, not a claim of calibrated win probability.
Six boats share 100% of that model's relative head score. A baseline is clearly
marked provisional; exhibition phase is labeled as reflected without declaring
it a calibrated probability. The formal-ticket gate remains independent.

Require a saved snapshot SHA, six unique lanes/courses, exact lane-to-course
agreement with saved racer rows, finite numeric shares in [0,1], and a total
within 0.001 of 1 (six four-decimal saved shares can have rounding error).
Missing/invalid inputs display an unavailable message, never equal invented
shares or a score from a different model. Zero shares remain in the legend.

Normalize only the small saved rounding error, then use largest remainders to
display one decimal percentages that total 100.0%. The SVG geometry follows
normalized original shares; the boat number, player name and percentage remain
available in an accessible legend, including small slices. Use the standard
white/black/red/blue/yellow/green boat colors and preserve actual entry mapping.

Validation covers immutability, no ticket-based reconstruction, six-way totals,
zero/full-circle rendering, source rounding, invalid/partial data, entry swaps,
HTML escaping, all current saved races and placement above the ticket block.
