# Ops Bot Design

<!--
Copyright 2026, Collabora, Ltd.

SPDX-License-Identifier: CC-BY-4.0

Author: Rylie Pavlik <rylie.pavlik@collabora.com>
-->

Unlike most of the "bots" in this repo, `openxr_ops/kb_ops/commands.toml`
defines the behavior of a bot that WG members actually are intended to interact
with. (The engine is mostly in `openxr_ops/kb_ops/commands.py`.) Its primary
goal is to facilitate tracking extensions through the extension development and
review pipeline.

In most cases, all an extension champion has to do is assign the MR to the bot
to indicate it's ready to move to the next stage in the pipeline.

The spec editor (and support contractor, if relevant) may use a few additional
manual commands. Their use will look something like `@botname support-comments`
in a note. The bot reacts to the note with :+1: to avoid processing it twice,
which is a common practice with bots on GitHub. A note will not be considered to
invoke a command if it already has such a react.


## Data Structure and Design

### Commands

The interactions and pipeline are coded in a TOML format data file at
`openxr_ops/kb_ops/commands.toml` so that future changes in workflow are easy to
adapt to.

Most of the file is a dictionary under `command`, defining named commands. The
command name comes from the section name. In many cases the command name is not
really used except for logging, since assignment of an MR triggers it.

Commands take as their parameter an MR, which is typically implied by how the
command is invoked. For now, all MRs that trigger commands will already have a
matching operations task in KanBoard that can be looked up with the existing
mechanisms in `openxr_ops.kb_ops`.

Each individual command block has a `description` string for human-readable
purposes. (built-in help dump?)

It may also have `auto_on_assign = true` which considers the command triggered
on an MR if the MR is assigned to the bot user **and** one of the conditions
blocks under `condition_on_assign` is all true, or if no `condition_on_assign`
blocks exist. (That is, `command.cmdname.condition_on_assign[]` expresses a
formula in [disjunctive normal form][DNF] - an OR of ANDs - and a fully empty
expression (no blocks) is replaced by the constant `true`.) Parsing the config
file should allow constructing instances of interfaces and generic objects to
perform condition testing easily. See "Predicates and Conditions" for details.

When a command is triggered, the bot performs several actions expressed in the
array of `action`. An action is again an interface, and parsing the file should
allow constructing an array of implementations, one from each of those `action`
blocks. The `type` key in the block indicates which type of implementation to
instantiate. Other parameters differ by action type. See "Actions".

There is one implicit action performed before the explicit ones from the config
file to avoid repetition: comments/notes that manually invoke a command are
acknowledged with a thumbs-up react.

**Note**: Commands triggered by assignment (`auto_on_assign = true`) **must**
include an explicit action of `type = "assign"`, preferably as the first action,
to avoid repeated triggering of the command. A warning (and override to
`auto_on_assign = false`), or even an error on parse, is appropriate if an
assign-triggered command contains no such action.


[DNF]: https://en.wikipedia.org/w/index.php?title=Disjunctive_normal_form&oldid=1379018365

### Interface: Predicates and Conditions

There are conditions that are a collection of implementations of a generic
predicate interface (on the task and MR data).

Within a "condition" dictionary, each key-value pair instantiates a predicate,
and the entire corresponding condition object is true only if all predicates are
true. (Conjunction/AND)

Predicates:

- Match task column: eg `column = "In Review"`
- Discussions resolved: eg `blocking_discussions = false` 