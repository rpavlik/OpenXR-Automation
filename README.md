# OpenXR Automation

<!--
Copyright 2022, Collabora, Ltd.
SPDX-License-Identifier: CC-BY-4.0
-->

This is a collection of small scripts I've written over time to simplify my
OpenXR related work.

Right now, many of them involve connecting GitLab to a lightweight, no-charge,
source-available, local-only Kanban-type board app,
[nullboard](https://nullboard.io) . I would recommend using whatever the latest
I've pushed to
[my fork's integration branch](https://github.com/rpavlik/nullboard/tree/integration).
(Nullboard is licensed under
[BSD-2-Clause plus the Commons Clause](https://github.com/rpavlik/nullboard/blob/master/LICENSE),
the latter of which makes it not meet the text of the Open Source Definition,
and thus why I described it in an such an awkward way.)

An important feature of Nullboard, besides its quick setup (clone and open HTML
file in a browser) and minimal environment, is that it has robust JSON
import/export support, so we can easily create/modify/parse the data of each
board. `nullboard_gitlab.py` has some shared utilities for this interaction,
while `cts_workboard_update.py` and `openxr_release_checklist_update.py` are the
top-level scripts for doing the update for two boards I maintain.
`work_item_and_collection.py` is a somewhat-more-generic (though GitLab-based)
group of data structures used in the above files.

## License

In general, the scripts in this repo are all BSL-1.0 licensed. Thanks to my
employer, [Collabora, Ltd.](https://collabora.com), for their "Open First"
philosophy allowing me to publish these easily.

I strive for all my repos to follow the [REUSE](https://reuse.software)
specification, with copyright and license data in each file in a
machine-parsable and human-readable way. See each file for the final word on
license for it. The full, original text for all licenses used by files in this
repo are provided in the `LICENSES` directory.
