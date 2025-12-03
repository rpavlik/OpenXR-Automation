# OpenXR Automation

<!--
Copyright 2022, Collabora, Ltd.
Copyright 2025, The Khronos Group Inc.

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
and thus why I described it in an such an awkward way.) An important feature of
Nullboard, besides its quick setup (clone and open HTML file in a browser) and
minimal environment, is that it has robust JSON import/export support, so we can
easily create/modify/parse the data of each board.

Gradually things are being migrated to [Kanboard][] for easier collaboration and more flexibility and features.

[Kanboard]: https://kanboard.org/

## Files

By now there are far more tools in here than just the below.

- CTS Contractor Kanboard project:
  - `python3 -m openxr_ops.kb_cts.update` to run an update of the CTS Contractor
    Kanboard project. Takes about a minute and a half. `--help` and `--dry-run`
    available. Try running in CI!
  - `python3 -m openxr_ops.kb_cts.create` to automatically create/update most of
    the structure for the CTS Contractor board. Idempotent. `--help` and
    `--dry-run` available.
  - `./cts-workboard-import.py` to import the old "Nullboard" export json into a
    Kanboard project.
- OpenXRExtensions (Operations) Kanboard project:
  - `python3 -m openxr_ops.kb_ops.create` to automatically create most of the
    structure for the OpenXRExtensions board. Idempotent. `--help` available.
    Requires the following plugins for Kanboard:
    - https://github.com/rpavlik/kanboard-plugin-auto-tag - developed for this
      project.
    - https://github.com/rpavlik/AutoSubtasks - forked and improved for this
      project.
  - `./kb_create_extension_task.py 4113` to create a task for an extension in
    GitLab MR 4113 (for example). `--help` available.
  - `./kb_ops_migrate.py` to perform automatic migration from the GitLab
    operations project to kanboard. Mostly idempotent, though if your board
    isn't read-only, you will want to turn off some of the options (in the
    code). `--help` and `--dry-run` available.
- `work_item_and_collection.py` is a somewhat-generic (though GitLab-based)
  group of data structures
- `nullboard_gitlab.py` has some shared utilities for Nullboard export (`.nbx`)
  and GitLab interaction, building on the above

## Usage

I recommend using a virtual environment to get the dependencies for this repo,
something like the following:

```sh
python3 -m venv venv   # Only needed once to create venv
. venv/bin/activate    # or . venv/bin/activate.fish
                       # or . venv/Scripts/Activate.ps1
                       # or... depending on platform and shell

# Only needed at creation or when deps change
python3 -m pip install -r requirements.txt
```

You will also need to provide a GitLab token either in your environment or in a
`.env` file (recommended, mentioned by gitignore to avoid accidental commit).

Set at least the following:

- GitLab access credentials:
  - `GL_USERNAME`
  - `GL_ACCESS_TOKEN`
  - `GL_URL` (probably `GL_URL=https://gitlab.khronos.org` for direct usage by
    Khronos members)
- Kanboard access credentials:
  - `KANBOARD_URL`
  - `KANBOARD_USERNAME`
  - `KANBOARD_API_TOKEN`

Further documentation is in the source files, basically.

## License

In general, the scripts in this repo are all BSL-1.0 licensed. Thanks to my
employer, [Collabora, Ltd.](https://collabora.com), for their "Open First"
philosophy allowing me to publish these easily.

I strive for all my repos to follow the [REUSE](https://reuse.software)
specification, with copyright and license data in each file in a
machine-parsable and human-readable way. See each file for the final word on
license for it. The full, original text for all licenses used by files in this
repo are provided in the `LICENSES` directory.
