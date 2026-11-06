{%- if WecomLogin and WecomConnectorOff -%}
  {%- include "prompt-common/fragments/wecom-unified-connector-off.md" -%}
{%- elif WecomLogin -%}
  {%- if WecomAgentAvailable -%}
    {%- include "prompt-common/fragments/wecom-routing.md" -%}
  {%- else -%}
    {%- include "prompt-common/fragments/wecom-chat-unavailable.md" -%}
  {%- endif -%}
{%- elif WecomCliSkills -%}
  {%- include "prompt-common/fragments/wecom-cli-routing.md" -%}
{%- endif %}
