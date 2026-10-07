# WP5.1 tier picker screenshots (owner checkpoint)

Settings > Plan Features with the tier picker (WP5.1), on the frozen sample plan (`tests/fixtures/sample_plan_frozen`, no tier row, so it opens as "Expert (customized)").

| File | What it shows |
|---|---|
| `wp5_desktop_1_tier_picker_default_expert.png`, `wp5_mobile_1_...` | The picker as the plan opens: four cards with page counts, Expert highlighted, "Expert (customized)", the reset action and the "no tier picked yet" note |
| `wp5_desktop_2_standard_preview_confirm.png`, `wp5_mobile_2_...` | The confirm dialog after clicking Standard: what turns off, "Off · N rows entered", the engine-ignored warnings |
| `wp5_desktop_3_customized_with_reset.png`, `wp5_mobile_3_...` | Standard applied, then one switch overridden: "Standard (customized)" and "Reset to Standard preset" |
| `wp5_desktop_4_customized_row_badge.png`, `wp5_mobile_4_...` | The overridden switch's "Differs from Standard preset" badge |

Desktop is 1280x900, mobile 390x844.

## Rerun

From the repo root (Node, `npm install` done, Python deps installed):

```
node tools/capture_wp5_screens.mjs                 # writes here
node tools/capture_wp5_screens.mjs /tmp/screens    # or elsewhere
```

The script starts `tools/e2e_server.py` (a throwaway workspace per viewport, port 5990 and up, `WP5_SCREENS_PORT` to change), drives Chromium (`CHROMIUM_PATH`, else `/opt/pw-browsers/chromium` when present, else Playwright's own browser) and, when Pillow is installed, saves the PNGs with a 256-colour palette to keep them small.
