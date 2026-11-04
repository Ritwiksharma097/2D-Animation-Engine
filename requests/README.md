# Art requests for the next art round

Ranked by how much each blocks the two-screen sandbox (`sandbox/run.html?level=two_a`). Each folder has the identity
references, the spec, a checklist, a prompt template and the exact intake command. Made by `python workbench/art_requests.py`.

NOTE: the brief points to the old sprite_rework README's prompt section, 'summarised in the handoff'. That text is not in this repository: assets/reference/GPT_HANDOFF.md summarises what went wrong, not the prompt wording. This template is built from the handoff's lessons and the owner's feedback in assets/manifest.json. If you have the original prompt, paste its wording into the [ORIGINAL PROMPT] slot and keep the IDENTITY and LAYOUT blocks.

| rank | request | now | what it blocks |
| --- | --- | --- | --- |
| 1 | [guard_walk](guard_walk/README.md) `guard/walk` | rejected | He patrols on every screen. His walk is rejected, walks in place, and at the placeholder speed (annotations/_settings.json) his feet slide; the HUD shows it in red. |
| 2 | [guard_idle](guard_idle/README.md) `guard/idle` | rejected | Plays at both ends of every patrol (1.5 s each) and while he is suspicious. Rejected: much too fast, about 4-5 distinct drawings repeated. |
| 3 | [ren_walk_inbetweens](ren_walk_inbetweens/README.md) `ren/walk_keypose` | approved | Ren's walk is approved but has 4 drawings, so every walk in the sandbox looks choppy whatever the travel. It is the most-seen animation. |
| 4 | [ren_reactions](ren_reactions/README.md) `ren/caught_game_over` | unreviewed | caught_game_over plays on every catch; its sleeves and tunic are recoloured (REPORT.md, Phase 5). happy (bigger, rounder head) and hurt_stumble (recoloured face and sleeves) are not used by the sandbox yet but will be by any story beat. |
| 5 | [ren_idle](ren_idle/README.md) `ren/idle` | approved | Ren stands still between clicks; the approved idle is one still drawing (it 'does nothing'). Not wrong, just lifeless. |
| 6 | [guard_ladder](guard_ladder/README.md) `guard/ladder_up` | rejected | Not used by the sandbox (the guard AI never climbs). Rejected; the current cycle keeps his feet at one height, so it cannot land on rungs. |
