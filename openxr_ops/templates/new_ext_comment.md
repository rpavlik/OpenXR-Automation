An extension release tracking task for this extension has been opened at
{{ task_link }}. @{{ username }} please update it to reflect the current state of
this extension merge request and request review, if applicable. (Sub-tasks have
been added automatically, and more will be added as it moves through the
process. You are welcome to add sub-tasks for your own usage as well.)
You can change the overall stage either through "Move Position" on the task
detail, or by dragging the corresponding card on the full
[OpenXR Extensions Workboard][board].

For most extensions, complete the self-review steps listed as subtasks and on
the wiki, then move it to "Awaiting Review"
{%- if not review_required %} if you choose to request spec editor/support review
{%- endif -%}.
By default, your extension has been placed in the optional "Design Review
phase", in the "In Preparation" step.

{% if not review_required -%}

**Note**: Spec editor/support review is **optional but recommended** for this
extension. **To opt-in to review**, go to the task, choose "Edit Task", and add
the "Editor Review Requested" tag. Alternately, moving the task to the "Awaiting
Review" column is also taken as a signal that you want it reviewed, and the tag
will be added automatically.

{%- endif %}

See the [OpenXR Extensions Board Overview][overview] for the flowchart showing
the extension workboard process, and hover over the 'Info' 🛈 icons on the board
for specific details.

You {%- if outside_ipr_policy %} may also want to {% else %} must also {% endif -%}
request feedback from other WG members through our chat at <https://chat.khronos.org>
{%- if not outside_ipr_policy %} as well as discussion in weekly calls{% endif %}.

[board]: https://openxr-boards.khronos.org/board/29
[overview]: https://openxr-boards.khronos.org/project/29/overview

<!-- task-created-comment -->