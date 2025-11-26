An extension release tracking task for this extension has been opened at
{{ task_link }}. @{{ username }} please update it to reflect the current state of
this extension merge request and request review, if applicable. (Sub-tasks have
been added automatically, and more will be added as it moves through the
process. You are welcome to add your own sub-tasks for your own usage.)

You should also update the [OpenXR Extensions Workboard][board] according to
the status of your extension: most likely this means moving it to 'NeedsReview'
once you complete the self-review steps in the checklist
{%- if not review_required %} if you choose to request spec editor/support review
{%- endif -%}.

{% if not review_required -%}

Spec editor/support review is optional but recommended for this extension. To
opt-in to review, go to the task, choose "Edit Task", and add the "Editor Review
Requested" tag. Otherwise, moving the task to the "Needs Review" column is
taken as a signal that you want it reviewed, and the tag will be added
automatically.

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